// Fixed example for the bundled demo contract; register every configured input.
#include "apps.hpp"
#include <atomic>
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <thread>

int main(int argc, char** argv) {
    try {
        const int seconds = argc > 2 ? std::stoi(argv[2]) : 20;
        if (seconds <= 0) throw std::invalid_argument("seconds must be positive");
        // Captured resources outlive App, including when an exception unwinds.
        std::atomic<unsigned> frames{0}, health{0};
        amw_generated::consumer app(argc > 1 ? argv[1] : "monitor");
        app.on_perception_frame([&](
                std::shared_ptr<const amw_generated::demo_Frame_v1_0_0> sample,
                amw::cm::SampleInfo info) {
            // Read sample->fields here; retain the shared_ptr for deferred work.
            // info.receive_steady_ns is a local reception time, not capture time.
            (void)sample;
            (void)info;
            ++frames;
        });
        app.on_perception_health([&](auto sample, amw::cm::SampleInfo info) {
            (void)sample;
            (void)info;
            ++health;
        });
        auto started = app.runtime.start();
        if (!started) {
            std::cerr << "start: " << started.detail << '\n';
            return 2;
        }
        // A real application would run its own control loop here.
        std::this_thread::sleep_for(std::chrono::seconds(seconds));
        const auto stopped = app.runtime.stop();
        std::cout << "frames=" << frames.load() << " health=" << health.load()
                  << " frame_callback_failures="
                  << app.runtime.metrics("perception.frame").callback_failed << '\n';
        return stopped && frames.load() && health.load() ? 0 : 3;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
