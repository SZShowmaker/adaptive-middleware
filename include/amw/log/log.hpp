#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <ostream>
#include <string>
#include <string_view>
#include <utility>

namespace amw::log {
enum class Level { trace, debug, info, warn, error, fatal, off };
struct Options {
    std::string app_name;
    std::string config_path; // Required UTF-8 path; relative to initialization's working directory.
};
struct Result {
    bool ok{false};
    std::string detail;
    std::string config_path; // Absolute path, including on parsing errors when resolvable.
    explicit operator bool() const noexcept { return ok; }
};
struct Metrics {
    uint64_t accepted{}, written{}, dropped{}, output_errors{}, format_errors{}, truncated{};
    size_t queued{}, queue_high_water{};
};
enum class Submit { accepted, filtered, not_initialized, queue_full, invalid_argument, failed };
// One process-wide session. Initialize once on the control thread, before CM/worker startup.
Result initialize(const Options& options);
// Drain accepted records; terminal writes can block. Stop producers/CM first.
void shutdown();
Metrics metrics() noexcept; // Retained after shutdown, reset after successful initialization.
bool enabled(std::string_view module, Level level) noexcept;
Submit write(std::string_view module, Level level, std::string_view message) noexcept;
namespace detail {
Submit write_lazy(std::string_view module, Level level,
                  const std::function<void(std::ostream&)>& formatter) noexcept;
void format_failed() noexcept;
}
// The formatter runs synchronously in the caller, only for an enabled level.
// Do not initialize/shutdown or recursively log inside a formatter.
template<class Formatter>
Submit lazy(std::string_view module, Level level, Formatter&& formatter) noexcept {
    try {
        if (!enabled(module, level)) return Submit::filtered;
        return detail::write_lazy(module, level,
            std::function<void(std::ostream&)>(std::forward<Formatter>(formatter)));
    } catch (...) {
        detail::format_failed();
        return Submit::failed;
    }
}
} // namespace amw::log

// A single expression: safe in if/else, without endl; disabled messages do not evaluate payloads.
#define AMW_LOG(level, module, expression) \
    ::amw::log::lazy((module), (level), [&](std::ostream& amw_log_stream_) { amw_log_stream_ << expression; })
#define AMW_LOG_TRACE(module, expression) AMW_LOG(::amw::log::Level::trace, module, expression)
#define AMW_LOG_DEBUG(module, expression) AMW_LOG(::amw::log::Level::debug, module, expression)
#define AMW_LOG_INFO(module, expression)  AMW_LOG(::amw::log::Level::info, module, expression)
#define AMW_LOG_WARN(module, expression)  AMW_LOG(::amw::log::Level::warn, module, expression)
#define AMW_LOG_ERROR(module, expression) AMW_LOG(::amw::log::Level::error, module, expression)
#define AMW_LOG_FATAL(module, expression) AMW_LOG(::amw::log::Level::fatal, module, expression)
