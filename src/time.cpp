#include <amw/time/time.hpp>
#include <cstdio>
#include <ctime>
#include <stdexcept>

namespace amw::time {
int64_t unix_now_ns() noexcept {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count();
}
int64_t steady_now_ns() noexcept {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
std::string format_timestamp(int64_t ns, Zone zone, Precision precision) {
    int64_t seconds = ns / 1000000000;
    int64_t fraction = ns % 1000000000;
    if (fraction < 0) { --seconds; fraction += 1000000000; }
    const auto stamp = static_cast<std::time_t>(seconds);
    std::tm calendar{};
#ifdef _WIN32
    const auto error = zone == Zone::utc ? gmtime_s(&calendar, &stamp) : localtime_s(&calendar, &stamp);
    if (error) throw std::runtime_error("timestamp outside supported calendar range");
#else
    const auto result = zone == Zone::utc ? gmtime_r(&stamp, &calendar) : localtime_r(&stamp, &calendar);
    if (!result) throw std::runtime_error("timestamp outside supported calendar range");
#endif
    char date[40]{};
    if (!std::strftime(date, sizeof(date), "%Y-%m-%dT%H:%M:%S", &calendar))
        throw std::runtime_error("cannot format timestamp");
    std::string suffix = "Z";
    if (zone == Zone::local) {
        char offset[16]{};
        if (!std::strftime(offset, sizeof(offset), "%z", &calendar))
            throw std::runtime_error("cannot format time zone offset");
        suffix = offset;
        if (suffix.size() != 5) throw std::runtime_error("unsupported time zone offset");
        suffix.insert(3, ":");
    }
    char subsecond[16]{};
    if (precision == Precision::microseconds)
        std::snprintf(subsecond, sizeof(subsecond), ".%06d", static_cast<int>(fraction / 1000));
    else
        std::snprintf(subsecond, sizeof(subsecond), ".%03d", static_cast<int>(fraction / 1000000));
    return std::string(date) + subsecond + suffix;
}
std::string now_string(Zone zone, Precision precision) {
    return format_timestamp(unix_now_ns(), zone, precision);
}
} // namespace amw::time
