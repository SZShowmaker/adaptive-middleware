#include <amw/log/log.hpp>
#include <amw/time/time.hpp>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <vector>
#ifdef _WIN32
#include <io.h>
#define test_dup _dup
#define test_dup2 _dup2
#define test_close _close
#define test_fileno _fileno
#else
#include <unistd.h>
#define test_dup dup
#define test_dup2 dup2
#define test_close close
#define test_fileno fileno
#endif
// stderr is captured by these tests, so report assertion failures on stdout.
#undef assert
#define assert(condition) do { if (!(condition)) { std::cout << "assertion failed at " << __LINE__ << ": " << #condition << std::endl; std::abort(); } } while (false)
using namespace amw;

struct Capture {
    FILE* file = std::tmpfile();
    int old = -1;
    Capture() {
        assert(file); std::fflush(stderr);
        old = test_dup(test_fileno(stderr)); assert(old >= 0);
        assert(test_dup2(test_fileno(file), test_fileno(stderr)) >= 0);
    }
    std::string read() {
        std::fflush(stderr); std::rewind(file);
        std::string data; char bytes[4096];
        for (size_t n; (n = std::fread(bytes, 1, sizeof(bytes), file));) data.append(bytes, n);
        return data;
    }
    ~Capture() {
        std::fflush(stderr); test_dup2(old, test_fileno(stderr)); test_close(old); std::fclose(file);
    }
};
void save(const std::string& path, const std::string& xml) {
    std::ofstream out(std::filesystem::u8path(path), std::ios::binary); out << xml; assert(out.good());
}
const std::string prefix = "<logging version=\"1\"><defaultLevel>INFO</defaultLevel>";
const std::string suffix = "</logging>";
int main(int argc, char** argv) {
    assert(argc >= 2);
    const bool broken = std::string(argv[1]) == "--broken-pipe";
    const bool pressure = broken || std::string(argv[1]) == "--backpressure";
    assert(!pressure || argc >= 3);
    const std::string path = pressure ? argv[2] : argv[1];
    if (pressure) {
        save(path, prefix + "<queue capacity=\"1\" maxMessageBytes=\"4096\"/>" + suffix);
        assert(log::initialize({"pressure", path}));
        const std::string payload(4096, 'x');
        for (int i = 0; i < 10000; ++i) log::write("pressure", log::Level::info, payload);
        auto m = log::metrics();
        std::cout << "READY " << m.dropped << std::endl;
        log::shutdown();
        if (broken) {
            const auto errors = log::metrics();
            assert(errors.output_errors > 0 && errors.written + errors.output_errors == errors.accepted);
            std::cout << "BROKEN_PIPE_PASS " << errors.output_errors << std::endl;
        } else assert(log::metrics().written == log::metrics().accepted);
        return 0;
    }
    assert(log::write("cm", log::Level::info, "before init") == log::Submit::not_initialized);
    assert(!log::initialize({"", path}));
    assert(!log::initialize({"test", ""}));
    assert(!log::initialize({"test", path + ".missing"}));
    const std::vector<std::string> bad = {
        "", "<logging>", "<logging version=\"2\"><defaultLevel>INFO</defaultLevel></logging>",
        "<logging version=\"1\"/>", "<logging version=\"1\"><defaultLevel>INF0</defaultLevel></logging>",
        prefix + "<defaultLevel>WARN</defaultLevel>" + suffix,
        prefix + "<moudles/>" + suffix,
        prefix + "<console enabled=\"yes\" color=\"auto\"/>" + suffix,
        prefix + "<console enabled=\"true\" colour=\"auto\"/>" + suffix,
        prefix + "<timestamp timezone=\"CST\" precision=\"milliseconds\"/>" + suffix,
        prefix + "<queue capacity=\"-1\" maxMessageBytes=\"4096\"/>" + suffix,
        prefix + "<queue capacity=\"1x\" maxMessageBytes=\"4096\"/>" + suffix,
        prefix + "<queue capacity=\"65536\" maxMessageBytes=\"65536\"/>" + suffix,
        prefix + "<modules><module name=\"cm\" level=\"INFO\"/><module name=\"cm\" level=\"WARN\"/></modules>" + suffix,
        prefix + "<modules><module name=\"cm..send\" level=\"INFO\"/></modules>" + suffix,
        prefix + "<modules><typo/></modules>" + suffix,
        prefix + "<console enabled=\"true\" color=\"auto\">junk</console>" + suffix,
        prefix + suffix + "<other/>",
        "<!DOCTYPE logging>" + prefix + suffix,
        prefix + std::string(1, '\0') + suffix,
        std::string(65537, 'x')
    };
    for (const auto& xml : bad) {
        save(path, xml); const auto r = log::initialize({"test", path});
        assert(!r); assert(!r.detail.empty()); assert(std::filesystem::path(r.config_path).is_absolute());
        assert(!log::enabled("cm", log::Level::info));
    }
    assert(time::format_timestamp(0, time::Zone::utc) == "1970-01-01T00:00:00.000Z");
    assert(time::format_timestamp(1700000000123456000LL, time::Zone::utc, time::Precision::microseconds)
           == "2023-11-14T22:13:20.123456Z");
    assert(std::regex_match(time::now_string(), std::regex(".*[+-][0-9]{2}:[0-9]{2}")));
    time::Stopwatch timer; const auto before = time::steady_now_ns();
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
    assert(time::steady_now_ns() >= before); assert(timer.elapsed_ms() >= 1); timer.reset();
    assert(timer.elapsed_ns() >= 0);
    Capture output;
    save(path, prefix + "<timestamp timezone=\"UTC\" precision=\"microseconds\"/>"
         "<console enabled=\"true\" color=\"auto\"/><queue capacity=\"8192\" maxMessageBytes=\"128\"/>"
         "<modules><module name=\"cm\" level=\"DEBUG\"/><module name=\"cm.secret\" level=\"OFF\"/></modules>" + suffix);
    const auto ready = log::initialize({"test", path}); assert(ready);
    assert(!log::initialize({"again", path}));
    assert(log::enabled("cm.send", log::Level::debug));
    assert(!log::enabled("cmd", log::Level::debug));
    assert(!log::enabled("cm.secret.send", log::Level::fatal));
    int evaluated = 0;
    if (true) AMW_LOG_DEBUG("app", ++evaluated); else assert(false);
    assert(evaluated == 0);
    assert(log::write("bad module", log::Level::info, "x") == log::Submit::invalid_argument);
    assert(log::write("cm", log::Level::off, "x") == log::Submit::invalid_argument);
    AMW_LOG_INFO("app", "escaped\nline\033[31m");
    AMW_LOG_INFO("app", std::string(1024, 'z'));
    assert(log::lazy("app", log::Level::info, [](std::ostream&) { throw std::runtime_error("format"); }) == log::Submit::failed);
    const auto capture_before = time::unix_now_ns();
    const std::string expected_stamp = time::format_timestamp(capture_before, time::Zone::utc, time::Precision::microseconds).substr(0, 10);
    AMW_LOG_INFO("app", "timestamp marker");
    std::vector<std::thread> workers;
    for (int t = 0; t < 6; ++t) workers.emplace_back([t] {
        for (int n = 0; n < 300; ++n) AMW_LOG_INFO("app", "record=" << t << ":" << n << ":END");
    });
    for (auto& worker : workers) worker.join();
    // Editing the XML has no effect on an active session.
    save(path, "<logging version=\"1\"><defaultLevel>OFF</defaultLevel></logging>");
    assert(log::enabled("app", log::Level::info));
    log::shutdown(); log::shutdown();
    const auto m = log::metrics();
    assert(m.accepted == 1803 && m.written == 1803 && m.dropped == 0 && m.output_errors == 0);
    assert(m.truncated == 1 && m.format_errors == 1 && m.queued == 0);
    const auto text = output.read();
    assert(text.find("\033") == text.npos); // auto disables color under redirection
    assert(text.find("escaped\\nline\\x1b[31m") != text.npos);
    assert(text.find("[truncated]") != text.npos);
    assert(text.find(expected_stamp) != text.npos);
    std::istringstream lines(text); std::string line; size_t records = 0;
    const std::regex pattern(".*\\[INFO\\] \\[test\\] \\[app\\] \\[tid=[0-9]+\\] record=[0-5]:[0-9]+:END");
    while (std::getline(lines, line)) if (line.find("record=") != line.npos) { assert(std::regex_match(line, pattern)); ++records; }
    assert(records == 1800);
    assert(log::write("cm", log::Level::info, "after shutdown") == log::Submit::not_initialized);
    assert(log::initialize({"test", path})); // new session now reads OFF
    assert(!log::enabled("app", log::Level::fatal));
    log::shutdown(); assert(log::metrics().accepted == 0);
    // Concurrent shutdown with producers: no use-after-free; all accepted records drain.
    save(path, prefix + "<queue capacity=\"8\" maxMessageBytes=\"128\"/>" + suffix);
    assert(log::initialize({"test", path}));
    std::atomic<bool> go{true};
    std::thread producer([&] { while (go) AMW_LOG_INFO("race", "stop race"); });
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
    log::shutdown(); go = false; producer.join();
    const auto last = log::metrics(); assert(last.written == last.accepted && last.queued == 0);
    std::filesystem::remove(std::filesystem::u8path(path));
    std::cout << "LOG_TIME_TEST_PASS\n";
}
