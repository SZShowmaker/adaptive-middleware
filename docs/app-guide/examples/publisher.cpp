// Fixed example for the bundled demo contract; adapt names for your own App.
#include "apps.hpp"
#include <chrono>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <utility>

int main(int argc, char** argv) {
    try {
        const int rounds = argc > 2 ? std::stoi(argv[2]) : 500;
        if (rounds <= 0) throw std::invalid_argument("rounds must be positive");
        amw::cm::NetworkOptions network;
        // Optional IPv4 interface at argv[3]; absent inherits the generated setting.
        if (argc > 3) network.interface_address = argv[3];
        amw_generated::producer app(argc > 1 ? argv[1] : "camera_front", network);
        auto started = app.runtime.start();
        if (!started) {
            std::cerr << "start: " << started.detail << '\n';
            return 2;
        }
        bool rejected = false;
        for (int n = 0; n < rounds; ++n) {
            amw_generated::demo_Frame_v1_0_0 frame{};
            frame.frame_id = n;
            frame.speed = static_cast<float>(n % 100);
            frame.objects.push_back({7, 12.5f});
            const auto sent_frame = app.perception_frame.try_publish(std::move(frame));
            const auto sent_health = app.perception_health.try_publish({true, 0});
            if (!sent_frame || !sent_health) {
                std::cerr << "submit: " << sent_frame.detail << ' ' << sent_health.detail << '\n';
                rejected = true;
                break;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
        }
        // Demonstration delay only. stop() does not flush the sending queue.
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
        const auto stopped = app.runtime.stop();
        const auto frame = app.perception_frame.metrics();
        const auto health = app.perception_health.metrics();
        std::cout << "frame_sent=" << frame.sent << " health_sent=" << health.sent
                  << " failures=" << frame.send_failed + health.send_failed << '\n';
        return !stopped || rejected || frame.send_failed || health.send_failed ? 3 : 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
