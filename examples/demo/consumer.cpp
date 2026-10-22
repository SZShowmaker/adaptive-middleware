#include "apps.hpp"
#include <atomic>
#include <chrono>
#include <iostream>
#include <thread>
int main(int argc, char **argv) {
    amw_generated::consumer app(argc > 1 ? argv[1] : "monitor");
    std::atomic<int> frames{0}, health{0};
    std::atomic<bool> bad{false};
    app.on_perception_frame([&](auto f, auto) {
        if (f->objects.size() != 1 || f->objects[0].object_id != 7 || f->objects[0].distance != 12.5f)
            bad = true;
        ++frames;
    });
    app.on_perception_health([&](auto h, auto) {
        if (!h->healthy || h->code != 0)
            bad = true;
        ++health;
    });
    auto result = app.runtime.start();
    if (!result) {
        std::cerr << result.detail << '\n';
        return 2;
    }
    int seconds = argc > 2 ? std::stoi(argv[2]) : 7;
    std::this_thread::sleep_for(std::chrono::seconds(seconds));
    app.runtime.stop();
    std::cout << "frames=" << frames << " health=" << health << " invalid=" << bad << '\n';
    return frames > 0 && health > 0 && !bad ? 0 : 3;
}
