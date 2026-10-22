#pragma once
#include <chrono>
#include <cstdint>
#include <string>

namespace amw::time {
enum class Zone { local, utc };
enum class Precision { milliseconds, microseconds };
// Wall-clock time is for correlation, steady time is for elapsed durations.
int64_t unix_now_ns() noexcept;
int64_t steady_now_ns() noexcept;
std::string format_timestamp(int64_t unix_ns, Zone zone = Zone::local,
                             Precision precision = Precision::milliseconds);
std::string now_string(Zone zone = Zone::local,
                       Precision precision = Precision::milliseconds);
class Stopwatch {
  public:
    Stopwatch() noexcept : start_(std::chrono::steady_clock::now()) {}
    void reset() noexcept { start_ = std::chrono::steady_clock::now(); }
    int64_t elapsed_ns() const noexcept {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
                   std::chrono::steady_clock::now() - start_).count();
    }
    double elapsed_ms() const noexcept { return static_cast<double>(elapsed_ns()) / 1000000.0; }
  private:
    std::chrono::steady_clock::time_point start_;
};
} // namespace amw::time
