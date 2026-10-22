#include "apps.hpp"
#include <chrono>
#include <iostream>
#include <thread>
int main(int argc, char **argv) {
    amw_generated::producer app(argc > 1 ? argv[1] : "camera_front");
    auto status = app.runtime.start();
    if (!status) {
        std::cerr << status.detail << '\n';
        return 2;
    }
    int rounds = argc > 2 ? std::stoi(argv[2]) : 500;
    for (int n = 0; n < rounds; ++n) {
        amw_generated::demo_Frame_v1_0_0 frame;
        frame.frame_id = n;
        frame.speed = static_cast<float>(n % 100);
        frame.objects.push_back({7, 12.5f});
        auto r = app.perception_frame.try_publish(std::move(frame));
        if (!r)
            return 3;
        app.perception_health.try_publish({true, 0});
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
    }
    auto m = app.perception_frame.metrics();
    std::cout << "sent=" << m.sent << " failures=" << m.send_failed
              << " matches=" << app.perception_frame.matches() << '\n';
    app.runtime.stop();
    return m.send_failed ? 4 : 0;
}
