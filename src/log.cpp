#include <amw/log/log.hpp>
#include <amw/time/time.hpp>
#include "tinyxml2.h"
#include <algorithm>
#include <atomic>
#include <charconv>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <thread>
#ifdef _WIN32
#include <io.h>
#include <windows.h>
#else
#include <unistd.h>
#include <signal.h>
#include <pthread.h>
#endif

namespace amw::log {
namespace {
using amw_log_xml::XMLElement;
struct Config {
    Level threshold{Level::info};
    std::map<std::string, Level, std::less<>> modules;
    amw::time::Zone zone{amw::time::Zone::local};
    amw::time::Precision precision{amw::time::Precision::milliseconds};
    bool console{true};
    std::string color{"auto"};
    size_t capacity{1024}, message_bytes{4096};
};
bool identifier(std::string_view name) {
    if (name.empty() || name.size() > 128) return false;
    for (unsigned char c : name)
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.')) return false;
    return name.front() != '.' && name.back() != '.' && name.find("..") == name.npos;
}
std::string trim(std::string s) {
    const auto first = s.find_first_not_of(" \r\n\t");
    return first == s.npos ? "" : s.substr(first, s.find_last_not_of(" \r\n\t") - first + 1);
}
Level parse_level(const std::string& value) {
    const char* names[] = {"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL", "OFF"};
    for (int i = 0; i < 7; ++i) if (value == names[i]) return static_cast<Level>(i);
    throw std::runtime_error("invalid log level: " + value);
}
const char* level_name(Level level) {
    const char* names[] = {"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL", "OFF"};
    return names[static_cast<int>(level)];
}
void attributes(const XMLElement* node, std::initializer_list<std::string_view> allowed) {
    for (auto a = node->FirstAttribute(); a; a = a->Next())
        if (std::find(allowed.begin(), allowed.end(), a->Name()) == allowed.end())
            throw std::runtime_error(std::string("unknown attribute: ") + node->Name() + "." + a->Name());
}
std::string required(const XMLElement* node, const char* name) {
    const auto value = node->Attribute(name);
    if (!value || !*value) throw std::runtime_error(std::string("missing attribute: ") + node->Name() + "." + name);
    return value;
}
void content(const amw_log_xml::XMLNode* node, bool elements, bool text = false) {
    for (auto child = node->FirstChild(); child; child = child->NextSibling()) {
        if (child->ToComment()) continue;
        if (child->ToElement() && elements) continue;
        if (child->ToText() && (text || trim(child->Value()).empty())) continue;
        throw std::runtime_error(std::string("unexpected XML content in ") + node->Value());
    }
}
size_t positive(const std::string& value, size_t maximum) {
    size_t n{};
    const auto parsed = std::from_chars(value.data(), value.data() + value.size(), n);
    if (parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() || !n || n > maximum)
        throw std::runtime_error("integer outside allowed range: " + value);
    return n;
}
Config read_config(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open XML file");
    std::string bytes(65537, '\0');
    input.read(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    bytes.resize(static_cast<size_t>(input.gcount()));
    if (input.bad()) throw std::runtime_error("cannot read XML file");
    if (bytes.size() > 65536 || bytes.find('\0') != bytes.npos)
        throw std::runtime_error("XML must be at most 64 KiB and contain no NUL bytes");
    amw_log_xml::XMLDocument doc;
    if (doc.Parse(bytes.data(), bytes.size()) != amw_log_xml::XML_SUCCESS)
        throw std::runtime_error(std::string("invalid XML: ") + doc.ErrorStr());
    const auto root = doc.RootElement();
    if (!root || std::string(root->Name()) != "logging") throw std::runtime_error("expected <logging> root");
    for (auto n = doc.FirstChild(); n; n = n->NextSibling())
        if (n != root && !n->ToComment() && !n->ToDeclaration())
            throw std::runtime_error("multiple roots or unsupported XML declaration/DTD");
    attributes(root, {"version"});
    if (required(root, "version") != "1") throw std::runtime_error("logging version must be 1");
    content(root, true);
    Config config;
    std::set<std::string> seen;
    for (auto node = root->FirstChildElement(); node; node = node->NextSiblingElement()) {
        const std::string name = node->Name();
        if (!seen.insert(name).second) throw std::runtime_error("duplicate element: " + name);
        if (name == "defaultLevel") {
            attributes(node, {}); content(node, false, true);
            std::string value;
            for (auto t = node->FirstChild(); t; t = t->NextSibling()) if (t->ToText()) value += t->Value();
            config.threshold = parse_level(trim(value));
        } else if (name == "timestamp") {
            attributes(node, {"timezone", "precision"}); content(node, false);
            const auto zone = required(node, "timezone");
            const auto precision = required(node, "precision");
            if (zone != "UTC" && zone != "local") throw std::runtime_error("timezone must be UTC or local");
            if (precision != "milliseconds" && precision != "microseconds")
                throw std::runtime_error("precision must be milliseconds or microseconds");
            config.zone = zone == "UTC" ? amw::time::Zone::utc : amw::time::Zone::local;
            config.precision = precision == "microseconds" ? amw::time::Precision::microseconds : amw::time::Precision::milliseconds;
        } else if (name == "console") {
            attributes(node, {"enabled", "color"}); content(node, false);
            const auto enabled = required(node, "enabled");
            if (enabled != "true" && enabled != "false") throw std::runtime_error("console.enabled must be true or false");
            config.console = enabled == "true";
            config.color = required(node, "color");
            if (config.color != "auto" && config.color != "always" && config.color != "never")
                throw std::runtime_error("console.color must be auto, always or never");
        } else if (name == "queue") {
            attributes(node, {"capacity", "maxMessageBytes"}); content(node, false);
            config.capacity = positive(required(node, "capacity"), 65536);
            config.message_bytes = positive(required(node, "maxMessageBytes"), 65536);
            if (config.capacity * config.message_bytes > 64 * 1024 * 1024)
                throw std::runtime_error("capacity * maxMessageBytes must not exceed 64 MiB");
        } else if (name == "modules") {
            attributes(node, {}); content(node, true);
            for (auto m = node->FirstChildElement(); m; m = m->NextSiblingElement()) {
                if (std::string(m->Name()) != "module") throw std::runtime_error("expected <module>");
                attributes(m, {"name", "level"}); content(m, false);
                const auto id = required(m, "name");
                if (!identifier(id)) throw std::runtime_error("invalid module name: " + id);
                if (!config.modules.emplace(id, parse_level(required(m, "level"))).second)
                    throw std::runtime_error("duplicate module: " + id);
            }
        } else throw std::runtime_error("unknown element: " + name);
    }
    if (!seen.count("defaultLevel")) throw std::runtime_error("missing <defaultLevel>");
    return config;
}
bool color_auto() {
#ifdef _WIN32
    DWORD mode{};
    const auto handle = GetStdHandle(STD_ERROR_HANDLE);
    return _isatty(_fileno(stderr)) && GetConsoleMode(handle, &mode) && (mode & ENABLE_VIRTUAL_TERMINAL_PROCESSING);
#else
    return isatty(fileno(stderr)) != 0;
#endif
}
// Keep each record on one line; terminal control bytes in messages cannot change the prefix/color.
std::string escaped(std::string_view input) {
    std::string result;
    for (unsigned char c : input) {
        if (c == '\n') result += "\\n";
        else if (c == '\r') result += "\\r";
        else if (c == '\t') result += "\\t";
        else if (c < 32 || c == 127) {
            const char hex[] = "0123456789abcdef";
            result += "\\x"; result += hex[c >> 4]; result += hex[c & 15];
        } else result += static_cast<char>(c);
    }
    return result;
}
class Buffer : public std::streambuf {
  public:
    explicit Buffer(size_t limit) : limit_(limit) { data.reserve(std::min(limit, size_t{256})); }
    std::string data;
    bool truncated{false};
  protected:
    std::streamsize xsputn(const char* s, std::streamsize n) override {
        if (n <= 0) return 0;
        const size_t take = std::min(static_cast<size_t>(n), limit_ - data.size());
        data.append(s, take); truncated |= take < static_cast<size_t>(n); return n;
    }
    int_type overflow(int_type c) override {
        if (!traits_type::eq_int_type(c, traits_type::eof())) {
            const char value = traits_type::to_char_type(c); xsputn(&value, 1);
        }
        return traits_type::not_eof(c);
    }
  private:
    size_t limit_;
};
struct Record {
    Level level;
    int64_t timestamp;
    std::thread::id thread;
    std::string module, message;
    bool truncated{};
};
struct State {
    Config config;
    std::string app;
    std::atomic<bool> accepting{true};
    std::mutex mutex;
    std::condition_variable changed;
    std::deque<Record> queue;
    Metrics counts;
    std::thread worker;
    bool color{};
    ~State() { stop(); }
    void stop() {
        { std::lock_guard<std::mutex> lock(mutex); accepting = false; }
        changed.notify_all();
        if (worker.joinable()) worker.join();
    }
    bool permits(std::string_view module, Level level) const {
        if (!accepting || !config.console || level < Level::trace || level >= Level::off || !identifier(module)) return false;
        auto threshold = config.threshold;
        auto prefix = module;
        for (;;) {
            const auto found = config.modules.find(prefix);
            if (found != config.modules.end()) { threshold = found->second; break; }
            const auto dot = prefix.rfind('.');
            if (dot == prefix.npos) break;
            prefix = prefix.substr(0, dot);
        }
        return level >= threshold;
    }
    Submit enqueue(Record record) {
        std::lock_guard<std::mutex> lock(mutex);
        if (!accepting) return Submit::not_initialized;
        if (queue.size() >= config.capacity) { ++counts.dropped; return Submit::queue_full; }
        queue.push_back(std::move(record));
        ++counts.accepted;
        if (queue.back().truncated) ++counts.truncated;
        counts.queue_high_water = std::max(counts.queue_high_water, queue.size());
        changed.notify_one();
        return Submit::accepted;
    }
    void work() noexcept {
#ifndef _WIN32
        // A closed stderr pipe must be reported as an output error, not kill the App.
        // Block SIGPIPE only on this worker; leave the application's signal policy alone.
        sigset_t signals;
        sigemptyset(&signals);
        sigaddset(&signals, SIGPIPE);
        pthread_sigmask(SIG_BLOCK, &signals, nullptr);
#endif
        for (;;) {
            Record record;
            {
                std::unique_lock<std::mutex> lock(mutex);
                changed.wait(lock, [&] { return !accepting || !queue.empty(); });
                if (queue.empty()) break;
                record = std::move(queue.front()); queue.pop_front();
            }
            bool ok = false;
            try {
                std::ostringstream line;
                line << amw::time::format_timestamp(record.timestamp, config.zone, config.precision)
                     << " [" << level_name(record.level) << "] [" << app << "] [" << record.module
                     << "] [tid=" << record.thread << "] " << escaped(record.message);
                if (record.truncated) line << " [truncated]";
                line << '\n';
                auto text = line.str();
                if (color) {
                    const char* ansi = record.level >= Level::error ? "\033[31m" :
                                       record.level == Level::warn ? "\033[33m" : "\033[0m";
                    text = std::string(ansi) + text + "\033[0m";
                }
                ok = std::fwrite(text.data(), 1, text.size(), stderr) == text.size();
                if (std::fflush(stderr) != 0) ok = false;
            } catch (...) { ok = false; }
            std::lock_guard<std::mutex> lock(mutex);
            if (ok) ++counts.written; else ++counts.output_errors;
        }
    }
};
struct Manager {
    std::mutex lifecycle;
    std::shared_ptr<State> state;
    ~Manager() { if (state) state->stop(); }
};
Manager& manager() { static Manager instance; return instance; }
std::shared_ptr<State> current() { return std::atomic_load(&manager().state); }
Submit preflight(const std::shared_ptr<State>& state, std::string_view module, Level level) {
    if (!state || !state->accepting) return Submit::not_initialized;
    if (!identifier(module) || level < Level::trace || level >= Level::off) return Submit::invalid_argument;
    return state->permits(module, level) ? Submit::accepted : Submit::filtered;
}
void failed(const std::shared_ptr<State>& state) noexcept {
    if (state) { std::lock_guard<std::mutex> lock(state->mutex); ++state->counts.format_errors; }
}
} // namespace
Result initialize(const Options& options) {
    auto& m = manager();
    std::lock_guard<std::mutex> lock(m.lifecycle);
    if (const auto old = current(); old && old->accepting)
        return {false, "logging already initialized; restart to change configuration", {}};
    std::string path;
    try {
        if (!identifier(options.app_name)) throw std::runtime_error("app_name must be 1..128 ASCII letters, digits, dots, underscores or hyphens");
        if (options.config_path.empty()) throw std::runtime_error("config_path is required");
        path = std::filesystem::absolute(std::filesystem::u8path(options.config_path)).lexically_normal().u8string();
        auto state = std::make_shared<State>();
        state->config = read_config(std::filesystem::u8path(path));
        state->app = options.app_name;
        state->color = state->config.color == "always" || (state->config.color == "auto" && color_auto());
        // Prepare the return value before publishing the running session.
        Result result{true, "logging initialized", path};
        state->worker = std::thread([p = state.get()] { p->work(); });
        std::atomic_store(&m.state, std::move(state));
        return result;
    } catch (const std::exception& error) { return {false, error.what(), path}; }
}
void shutdown() {
    auto& m = manager();
    std::lock_guard<std::mutex> lock(m.lifecycle);
    if (auto state = current()) state->stop();
}
Metrics metrics() noexcept {
    if (auto state = current()) {
        std::lock_guard<std::mutex> lock(state->mutex);
        auto result = state->counts; result.queued = state->queue.size(); return result;
    }
    return {};
}
bool enabled(std::string_view module, Level level) noexcept {
    if (auto state = current()) return state->permits(module, level);
    return false;
}
Submit write(std::string_view module, Level level, std::string_view message) noexcept {
    auto state = current();
    const auto check = preflight(state, module, level);
    if (check != Submit::accepted) return check;
    try {
        const auto stamp = amw::time::unix_now_ns();
        return state->enqueue({level, stamp, std::this_thread::get_id(), std::string(module),
            std::string(message.substr(0, state->config.message_bytes)), message.size() > state->config.message_bytes});
    } catch (...) { failed(state); return Submit::failed; }
}
namespace detail {
Submit write_lazy(std::string_view module, Level level, const std::function<void(std::ostream&)>& formatter) noexcept {
    auto state = current();
    const auto check = preflight(state, module, level);
    if (check != Submit::accepted) return check;
    try {
        const auto stamp = amw::time::unix_now_ns();
        Buffer buffer(state->config.message_bytes);
        std::ostream stream(&buffer);
        stream.exceptions(std::ios::badbit | std::ios::failbit);
        formatter(stream);
        return state->enqueue({level, stamp, std::this_thread::get_id(), std::string(module),
                              std::move(buffer.data), buffer.truncated});
    } catch (...) { failed(state); return Submit::failed; }
}
void format_failed() noexcept { failed(current()); }
} // namespace detail
} // namespace amw::log
