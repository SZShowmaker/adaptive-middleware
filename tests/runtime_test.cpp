#include <amw/cm/cm.hpp>
#include <amw/log/log.hpp>
#include <cassert>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <thread>
#include <stdexcept>
using namespace amw::cm;
struct TestWriter : Writer {
    std::atomic<int> sent{0};
    std::atomic<bool> fail{false};
    Result write(const void *) override {
        ++sent;
        return fail ? Result{Code::transport_error, "test"} : Result{};
    }
    int matches() const override {
        return 2;
    }
};
struct TestReader : Reader {
    int matches() const override {
        return 1;
    }
};
struct TestBinding : NetworkBinding {
    std::shared_ptr<TestWriter> w = std::make_shared<TestWriter>();
    Receive callback;
    std::shared_ptr<Writer> writer(const Event &) override {
        return w;
    }
    std::shared_ptr<Reader> reader(const Event &, Receive r) override {
        callback = std::move(r);
        return std::make_shared<TestReader>();
    }
};
Event event(std::string key) {
    Event e;
    e.key = std::move(key);
    e.policy.queue_samples = 2;
    e.policy.queue_bytes = 8;
    e.size = [](const void *) { return sizeof(int); };
    e.validate = [](const void *p) { return *static_cast<const int *>(p) >= 0; };
    return e;
}
template <class F> void until(F f) {
    for (int i = 0; i < 200 && !f(); ++i)
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    assert(f());
}
int main(int argc, char** argv) {
    TransportConfig defaults{37, false, "10.1.2.3", {"10.1.2.4"}};
    auto inherited = apply_network_options(defaults, {});
    assert(inherited.interface_address == defaults.interface_address && inherited.peers == defaults.peers);
    NetworkOptions network;
    network.interface_address = "127.0.0.1";
    network.peers = std::vector<std::string>{"127.0.0.2"};
    auto overridden = apply_network_options(defaults, network);
    assert(overridden.domain == 37 && !overridden.shared_memory);
    assert(overridden.interface_address == "127.0.0.1" && overridden.peers.front() == "127.0.0.2");
    assert(defaults.interface_address == "10.1.2.3" && defaults.peers.front() == "10.1.2.4");
    network.interface_address = "";
    network.peers = std::vector<std::string>{};
    auto automatic = apply_network_options(defaults, network);
    assert(automatic.interface_address.empty() && automatic.peers.empty());
    for (const auto &bad : {"256.1.2.3", "1.2.3", "1.2.3.4.5", "1.2..4", "1.2.3.",
                            "-1.2.3.4", "01.2.3.4", "localhost", "::1", " 1.2.3.4"}) {
        for (bool peer : {false, true}) {
            NetworkOptions invalid;
            if (peer) invalid.peers = std::vector<std::string>{bad};
            else invalid.interface_address = bad;
            bool rejected = false;
            try { apply_network_options(defaults, invalid); }
            catch (const std::invalid_argument &) { rejected = true; }
            assert(rejected);
        }
    }
    NetworkOptions empty_peer;
    empty_peer.peers = std::vector<std::string>{""};
    bool rejected = false;
    try { apply_network_options(defaults, empty_peer); }
    catch (const std::invalid_argument &) { rejected = true; }
    assert(rejected);
    struct LogScope {
        ~LogScope() { amw::log::shutdown(); }
    } logs;
    if (argc == 2) assert(amw::log::initialize({"cm-test", argv[1]}));
    auto binding = std::make_shared<TestBinding>();
    Runtime rt([binding] { return binding; });
    auto p = Publisher<int>(rt.add_publisher(event("out")));
    assert(p.try_publish(1).code == Code::not_running);
    assert(p.try_publish(-1).code == Code::invalid_sample);
    std::mutex m;
    std::condition_variable cv;
    bool release = false, entered = false;
    rt.add_subscription(event("in"), [&](Sample, SampleInfo) {
        std::unique_lock<std::mutex> l(m);
        entered = true;
        cv.notify_all();
        cv.wait(l, [&] { return release; });
    });
    assert(rt.start());
    assert(p.matches() == 2);
    assert(p.try_publish(1));
    until([&] { return p.metrics().sent == 1; });
    binding->w->fail = true;
    assert(p.try_publish(2));
    until([&] { return p.metrics().send_failed == 1; });
    binding->callback(std::make_shared<int>(1), {});
    {
        std::unique_lock<std::mutex> l(m);
        cv.wait(l, [&] { return entered; });
    }
    for (int i = 0; i < 10; ++i)
        binding->callback(std::make_shared<int>(i), {});
    assert(rt.metrics("in").replaced == 8);
    assert(rt.metrics("in").queued_bytes == 8);
    rt.request_stop();
    assert(p.try_publish(1).code == Code::not_running);
    {
        std::lock_guard<std::mutex> l(m);
        release = true;
        cv.notify_all();
    }
    assert(rt.stop());
    assert(rt.stop());
    assert(rt.start());
    assert(rt.stop());
    Runtime broken(
        []() -> std::shared_ptr<NetworkBinding> { throw std::runtime_error("injected startup failure"); });
    broken.add_publisher(event("out"));
    assert(!broken.start());
    assert(!broken.running());
    assert(broken.stop());
    auto b2 = std::make_shared<TestBinding>();
    Runtime self([b2] { return b2; });
    std::atomic<bool> requested{false};
    self.add_subscription(event("in"), [&](Sample, SampleInfo) {
        assert(self.stop().code == Code::would_deadlock);
        requested = true;
    });
    assert(self.start());
    b2->callback(std::make_shared<int>(1), {});
    until([&] { return requested.load(); });
    assert(self.stop());
    Runtime missing([binding] { return binding; });
    missing.expect_subscription("required");
    assert(!missing.start());
    assert(!missing.running());
    assert(missing.stop());
    struct NullBinding : TestBinding {
        std::shared_ptr<Writer> writer(const Event &) override {
            return {};
        }
    };
    Runtime null_endpoint([] { return std::make_shared<NullBinding>(); });
    null_endpoint.add_publisher(event("out"));
    assert(!null_endpoint.start());
    assert(!null_endpoint.running());
    struct RetainedBinding : TestBinding {
        std::shared_ptr<Reader> reader(const Event &e, Receive callback) override {
            callback(std::make_shared<int>(1), {});
            return TestBinding::reader(e, std::move(callback));
        }
    };
    for (int trial = 0; trial < 30; ++trial) {
        Runtime retained([] { return std::make_shared<RetainedBinding>(); });
        std::atomic<bool> stopped{false};
        retained.add_subscription(event("in"), [&](Sample, SampleInfo) {
            retained.request_stop();
            stopped = true;
        });
        for (int i = 0; i < 12; ++i)
            retained.add_publisher(event("out" + std::to_string(i)));
        assert(retained.start());
        until([&] { return stopped.load(); });
        assert(!retained.running());
        assert(retained.stop());
    }
    if (argc == 2) assert(amw::log::metrics().accepted > 0);
    std::cout << "runtime: overflow, errors, restart, rollback, callback stop passed\n";
}
