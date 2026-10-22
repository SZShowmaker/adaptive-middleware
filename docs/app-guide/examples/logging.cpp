#include <amw/log/log.hpp>
#include <amw/time/time.hpp>
#include <exception>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc != 3 || std::string(argv[1]) != "--log-config") {
        std::cerr << "usage: amw_log_example --log-config /path/to/logging.xml\n";
        return 1;
    }
    try {
        const auto result = amw::log::initialize({"camera_front", argv[2]});
        if (!result) {
            std::cerr << "log initialization failed: " << result.config_path << ": " << result.detail << '\n';
            return 2;
        }
        std::cout << "Log XML: " << result.config_path << '\n';
        amw::time::Stopwatch timer;
        AMW_LOG_INFO("perception", "application started");
        AMW_LOG_DEBUG("perception", "this payload is filtered by the example XML");
        AMW_LOG_WARN("cm.demo", "demonstration warning, frame_id=" << 42);
        AMW_LOG_INFO("perception", "elapsed_ms=" << timer.elapsed_ms());
        // In a real App: stop CM and join business threads before this call.
        amw::log::shutdown();
        const auto stats = amw::log::metrics();
        std::cout << "written=" << stats.written << " dropped=" << stats.dropped
                  << " output_errors=" << stats.output_errors << '\n';
        return stats.output_errors ? 3 : 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        amw::log::shutdown();
        return 4;
    }
}
