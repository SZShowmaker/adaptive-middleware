#include <amw/cm/cm.hpp>
#include <amw/log/log.hpp>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <utility>

namespace amw::cm {
namespace {
thread_local const void *active_runtime = nullptr;
bool ipv4(const std::string &address) {
    size_t begin = 0;
    for (int part = 0; part != 4; ++part) {
        const auto end = address.find('.', begin);
        const auto length = (end == std::string::npos ? address.size() : end) - begin;
        if (!length || length > 3 || (length > 1 && address[begin] == '0'))
            return false;
        unsigned value = 0;
        for (size_t i = begin; i != begin + length; ++i) {
            if (address[i] < '0' || address[i] > '9')
                return false;
            value = value * 10 + unsigned(address[i] - '0');
        }
        if (value > 255 || ((part == 3) != (end == std::string::npos)))
            return false;
        begin += length + 1;
    }
    return true;
}
}
TransportConfig apply_network_options(TransportConfig config, const NetworkOptions &options) {
    if (options.interface_address)
        config.interface_address = *options.interface_address;
    if (options.peers)
        config.peers = *options.peers;
    if (!config.interface_address.empty() && !ipv4(config.interface_address))
        throw std::invalid_argument("invalid network interface IPv4: " + config.interface_address);
    for (const auto &peer : config.peers)
        if (!ipv4(peer))
            throw std::invalid_argument("invalid network peer IPv4: " + peer);
    return config;
}
class Endpoint : public std::enable_shared_from_this<Endpoint> {
  public:
    struct Item {
        Sample sample;
        SampleInfo info;
        size_t bytes;
    };
    Event event;
    Receive receive;
    bool publication{false}, accepting{false}, finished{true};
    const void *owner{};
    mutable std::mutex mutex;
    std::condition_variable changed, exited;
    std::deque<Item> queue;
    Metrics count;
    std::shared_ptr<Writer> writer;
    std::shared_ptr<Reader> reader;
    Result enqueue(Sample sample, SampleInfo info = {}) {
        size_t bytes{};
        try {
            if (!sample || !event.validate(sample.get()))
                return {Code::invalid_sample, event.key};
            bytes = event.size(sample.get());
        } catch (...) {
            return {Code::invalid_sample, event.key};
        }
        std::lock_guard<std::mutex> lock(mutex);
        ++count.submitted;
        if (!accepting) {
            ++count.rejected;
            return {Code::not_running, event.key};
        }
        if (bytes > event.policy.queue_bytes) {
            ++count.rejected;
            return {Code::invalid_sample, "sample exceeds queue byte budget"};
        }
        auto full = [&] {
            return queue.size() >= event.policy.queue_samples ||
                   bytes > event.policy.queue_bytes - count.queued_bytes;
        };
        if (full() && !event.policy.discard_oldest) {
            ++count.rejected;
            return {Code::queue_full, event.key};
        }
        while (full() && !queue.empty()) {
            count.queued_bytes -= queue.front().bytes;
            queue.pop_front();
            ++count.replaced;
        }
        queue.push_back({std::move(sample), info, bytes});
        count.queued_bytes += bytes;
        ++count.accepted;
        if (!publication)
            ++count.received;
        count.queue_high_water = std::max<uint64_t>(count.queue_high_water, queue.size());
        changed.notify_one();
        return {};
    }
    void request_stop() {
        std::lock_guard<std::mutex> lock(mutex);
        accepting = false;
        count.rejected += queue.size();
        queue.clear();
        count.queued_bytes = 0;
        changed.notify_all();
    }
    void launch() {
        {
            std::lock_guard<std::mutex> lock(mutex);
            accepting = true;
            finished = false;
        }
        // The worker owns its state until exit. stop() waits on exited; no raw Runtime is accessed.
        try {
            std::thread([self = shared_from_this()] { self->work(); }).detach();
        } catch (...) {
            std::lock_guard<std::mutex> lock(mutex);
            accepting = false;
            finished = true;
            throw;
        }
    }
    void work() {
        active_runtime = owner;
        for (;;) {
            Item item;
            {
                std::unique_lock<std::mutex> lock(mutex);
                changed.wait(lock, [&] { return !accepting || !queue.empty(); });
                if (!accepting)
                    break;
                item = std::move(queue.front());
                queue.pop_front();
                count.queued_bytes -= item.bytes;
            }
            if (publication) {
                Result result;
                try {
                    result = writer->write(item.sample.get());
                } catch (...) {
                    result = {Code::transport_error, "binding threw"};
                }
                std::lock_guard<std::mutex> lock(mutex);
                if (result)
                    ++count.sent;
                else {
                    ++count.send_failed;
                    if (count.send_failed == 1 || (count.send_failed & (count.send_failed - 1)) == 0)
                        AMW_LOG_WARN("cm.send", "endpoint=" << event.key << " topic=" << event.topic
                            << " failures=" << count.send_failed << " detail=" << result.detail);
                }
            } else {
                bool ok = true;
                try {
                    receive(std::move(item.sample), item.info);
                } catch (...) {
                    ok = false;
                }
                std::lock_guard<std::mutex> lock(mutex);
                if (ok)
                    ++count.delivered;
                else {
                    ++count.callback_failed;
                    if (count.callback_failed == 1 || (count.callback_failed & (count.callback_failed - 1)) == 0)
                        AMW_LOG_ERROR("cm.receive", "callback threw: endpoint=" << event.key
                            << " topic=" << event.topic << " failures=" << count.callback_failed);
                }
            }
        }
        active_runtime = nullptr;
        {
            std::lock_guard<std::mutex> lock(mutex);
            finished = true;
            exited.notify_all();
        }
    }
    void wait() {
        std::unique_lock<std::mutex> lock(mutex);
        exited.wait(lock, [&] { return finished; });
    }
    Metrics snapshot() const {
        std::lock_guard<std::mutex> lock(mutex);
        return count;
    }
    int matches() const {
        std::shared_ptr<Writer> w;
        std::shared_ptr<Reader> r;
        {
            std::lock_guard<std::mutex> lock(mutex);
            w = writer;
            r = reader;
        }
        // A binding may hold its own reader lock while enqueueing a sample.
        // Never enter it with the queue mutex held. Keep the endpoint alive if
        // stop() detaches it while this status query is in flight.
        return w ? w->matches() : r ? r->matches() : 0;
    }
};
class Runtime::Impl {
  public:
    explicit Impl(BindingFactory f) : factory(std::move(f)) {}
    BindingFactory factory;
    std::shared_ptr<NetworkBinding> binding;
    std::vector<std::shared_ptr<Endpoint>> endpoints;
    mutable std::mutex lifecycle;
    std::mutex activation;
    std::atomic<bool> running{false};
    bool sealed{false};
    std::vector<std::string> required;
};
Runtime::Runtime(BindingFactory f) : impl_(new Impl(std::move(f))) {}
Runtime::~Runtime() {
    // Destruction inside a callback is a programming error; request_stop is the callback-safe operation.
    if (active_runtime == impl_.get())
        std::terminate();
    stop();
}
PublisherBase Runtime::add_publisher(Event event) {
    std::lock_guard<std::mutex> lock(impl_->lifecycle);
    if (impl_->sealed)
        throw std::logic_error("configure endpoints before first start");
    for (auto &e : impl_->endpoints)
        if (e->event.key == event.key)
            throw std::invalid_argument("duplicate endpoint key");
    auto e = std::make_shared<Endpoint>();
    e->event = std::move(event);
    e->publication = true;
    e->owner = impl_.get();
    impl_->endpoints.push_back(e);
    return PublisherBase(e);
}
void Runtime::add_subscription(Event event, Receive receive) {
    if (!receive)
        throw std::invalid_argument("empty receive handler");
    auto handle = add_publisher(std::move(event));
    auto e = impl_->endpoints.back();
    e->publication = false;
    e->receive = std::move(receive);
}
void Runtime::expect_subscription(std::string key) {
    if (impl_->sealed)
        throw std::logic_error("configure expectations before first start");
    impl_->required.push_back(std::move(key));
}
Result Runtime::start() {
    if (active_runtime == impl_.get())
        return {Code::would_deadlock, "start from callback"};
    std::lock_guard<std::mutex> lock(impl_->lifecycle);
    if (impl_->running)
        return {};
    impl_->sealed = true;
    try {
        for (const auto &key : impl_->required) {
            bool found = false;
            for (const auto &e : impl_->endpoints)
                if (!e->publication && e->event.key == key)
                    found = true;
            if (!found)
                throw std::invalid_argument("missing subscription handler: " + key);
        }
        for (auto &e : impl_->endpoints) {
            e->wait();
            if (!e->event.validate || !e->event.size || !e->event.policy.queue_samples ||
                !e->event.policy.queue_bytes)
                throw std::invalid_argument("invalid event policy");
        }
        impl_->binding = impl_->factory();
        if (!impl_->binding)
            throw std::runtime_error("null network binding");
        for (auto &e : impl_->endpoints) {
            if (e->publication) {
                auto w = impl_->binding->writer(e->event);
                if (!w)
                    throw std::runtime_error("null binding writer");
                std::lock_guard<std::mutex> el(e->mutex);
                e->writer = std::move(w);
            } else {
                {
                    std::lock_guard<std::mutex> el(e->mutex);
                    e->accepting = true;
                }
                std::weak_ptr<Endpoint> weak = e;
                auto r = impl_->binding->reader(e->event, [weak](Sample s, SampleInfo i) {
                    if (auto p = weak.lock())
                        p->enqueue(std::move(s), i);
                });
                if (!r)
                    throw std::runtime_error("null binding reader");
                std::lock_guard<std::mutex> el(e->mutex);
                e->reader = std::move(r);
            }
        }
        {
            // A retained sample may trigger a callback immediately on launch. Its
            // request_stop must not be overwritten by the remaining activation.
            std::lock_guard<std::mutex> activation(impl_->activation);
            for (auto &e : impl_->endpoints)
                e->launch();
            impl_->running = true;
        }
        AMW_LOG_DEBUG("cm.lifecycle", "runtime activated, endpoints=" << impl_->endpoints.size());
        return {};
    } catch (const std::exception &ex) {
        impl_->running = false;
        for (auto &e : impl_->endpoints)
            e->request_stop();
        for (auto &e : impl_->endpoints) {
            e->wait();
            std::shared_ptr<Reader> r;
            std::shared_ptr<Writer> w;
            {
                std::lock_guard<std::mutex> el(e->mutex);
                r = std::move(e->reader);
                w = std::move(e->writer);
            }
        }
        impl_->binding.reset();
        AMW_LOG_ERROR("cm.lifecycle", "runtime start failed: " << ex.what());
        return {Code::transport_error, ex.what()};
    }
}
void Runtime::request_stop() {
    std::lock_guard<std::mutex> activation(impl_->activation);
    impl_->running = false;
    for (auto &e : impl_->endpoints)
        e->request_stop();
}
Result Runtime::stop() {
    if (active_runtime == impl_.get()) {
        request_stop();
        return {Code::would_deadlock, "request accepted; owner must complete stop"};
    }
    std::lock_guard<std::mutex> lock(impl_->lifecycle);
    request_stop();
    for (auto &e : impl_->endpoints)
        e->wait();
    for (auto &e : impl_->endpoints) {
        std::shared_ptr<Reader> r;
        std::shared_ptr<Writer> w;
        {
            std::lock_guard<std::mutex> el(e->mutex);
            r = std::move(e->reader);
            w = std::move(e->writer);
        }
    }
    impl_->binding.reset();
    return {};
}
bool Runtime::running() const {
    return impl_->running;
}
Metrics Runtime::metrics(const std::string &key) const {
    for (auto &e : impl_->endpoints)
        if (e->event.key == key)
            return e->snapshot();
    return {};
}
int Runtime::matches(const std::string &key) const {
    for (auto &e : impl_->endpoints)
        if (e->event.key == key)
            return e->matches();
    return 0;
}
Result PublisherBase::submit(Sample s) {
    return state_ ? state_->enqueue(std::move(s)) : Result{Code::not_running, "empty publisher"};
}
Metrics PublisherBase::metrics() const {
    return state_ ? state_->snapshot() : Metrics{};
}
int PublisherBase::matches() const {
    return state_ ? state_->matches() : 0;
}
} // namespace amw::cm
