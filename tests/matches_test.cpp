#include <amw/cm/cm.hpp>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <future>
#include <iostream>
#include <mutex>
#include <thread>
using namespace amw::cm;
using namespace std::chrono_literals;

namespace {
struct State {
    std::mutex native_mutex, coordination;
    std::condition_variable changed;
    bool native_locked = false, query_entered = false, release_query = false;
    bool pause_query = false;
    Receive receive;
    int matches() {
        {
            std::unique_lock<std::mutex> lock(coordination);
            query_entered = true;
            changed.notify_all();
            if (pause_query)
                assert(changed.wait_for(lock, 3s, [&] { return release_query; }));
        }
        std::lock_guard<std::mutex> lock(native_mutex);
        return 1;
    }
    void wait_for(bool State::*flag) {
        std::unique_lock<std::mutex> lock(coordination);
        assert(changed.wait_for(lock, 3s, [&] { return this->*flag; }));
    }
};
struct ReaderImpl : Reader {
    std::shared_ptr<State> state;
    explicit ReaderImpl(std::shared_ptr<State> s) : state(std::move(s)) {}
    int matches() const override { return state->matches(); }
};
struct WriterImpl : Writer {
    std::shared_ptr<State> state;
    explicit WriterImpl(std::shared_ptr<State> s) : state(std::move(s)) {}
    Result write(const void*) override { return {}; }
    int matches() const override { return state->matches(); }
};
struct Binding : NetworkBinding {
    std::shared_ptr<State> state = std::make_shared<State>();
    std::weak_ptr<Reader> reader_ref;
    std::weak_ptr<Writer> writer_ref;
    std::shared_ptr<Reader> reader(const Event&, Receive callback) override {
        state->receive = std::move(callback);
        auto r = std::make_shared<ReaderImpl>(state);
        reader_ref = r;
        return r;
    }
    std::shared_ptr<Writer> writer(const Event&) override {
        auto w = std::make_shared<WriterImpl>(state);
        writer_ref = w;
        return w;
    }
};
Event event() {
    Event e;
    e.key = "sample";
    e.policy.queue_samples = 4;
    e.policy.queue_bytes = 64;
    e.validate = [](const void* p) { return p != nullptr; };
    e.size = [](const void*) { return sizeof(int); };
    return e;
}
void concurrent_receive_and_matches() {
    auto b = std::make_shared<Binding>();
    Runtime rt([b] { return b; });
    std::promise<void> delivered;
    auto completion = delivered.get_future();
    rt.add_subscription(event(), [&](Sample, SampleInfo) { delivered.set_value(); });
    assert(rt.start());
    // Model DDS: its receive thread holds the reader lock while entering CM.
    std::thread receive([&] {
        std::lock_guard<std::mutex> native(b->state->native_mutex);
        {
            std::lock_guard<std::mutex> lock(b->state->coordination);
            b->state->native_locked = true;
            b->state->changed.notify_all();
        }
        b->state->wait_for(&State::query_entered);
        b->state->receive(std::make_shared<int>(42), {});
    });
    b->state->wait_for(&State::native_locked);
    auto query = std::async(std::launch::async, [&] { return rt.matches("sample"); });
    // Old implementation holds CM's queue lock while waiting for native_mutex.
    assert(completion.wait_for(3s) == std::future_status::ready);
    assert(query.wait_for(3s) == std::future_status::ready);
    assert(query.get() == 1);
    receive.join();
    assert(rt.stop());
}
void query_survives_stop(bool publication) {
    auto b = std::make_shared<Binding>();
    b->state->pause_query = true;
    Runtime rt([b] { return b; });
    if (publication) rt.add_publisher(event());
    else rt.add_subscription(event(), [](Sample, SampleInfo) {});
    assert(rt.start());
    auto query = std::async(std::launch::async, [&] { return rt.matches("sample"); });
    b->state->wait_for(&State::query_entered);
    auto stop = std::async(std::launch::async, [&] { return rt.stop(); });
    assert(stop.wait_for(3s) == std::future_status::ready);
    assert(stop.get());
    assert(rt.matches("sample") == 0);
    // The in-flight query must retain the native endpoint after Runtime detaches it.
    assert(publication ? !b->writer_ref.expired() : !b->reader_ref.expired());
    {
        std::lock_guard<std::mutex> lock(b->state->coordination);
        b->state->release_query = true;
        b->state->changed.notify_all();
    }
    assert(query.wait_for(3s) == std::future_status::ready);
    assert(query.get() == 1);
    assert(publication ? b->writer_ref.expired() : b->reader_ref.expired());
}
}
int main() {
    concurrent_receive_and_matches();
    query_survives_stop(false);
    query_survives_stop(true);
    std::cout << "matches: concurrent receive and endpoint lifetime across stop passed\n";
}
