#pragma once
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace amw::cm {
enum class Code {
    ok,
    not_running,
    queue_full,
    invalid_sample,
    transport_error,
    would_deadlock,
    invalid_configuration
};
struct Result {
    Code code{Code::ok};
    std::string detail;
    explicit operator bool() const {
        return code == Code::ok;
    }
};
struct Metrics {
    uint64_t submitted{}, accepted{}, replaced{}, rejected{}, sent{}, send_failed{}, received{}, delivered{},
        callback_failed{}, queue_high_water{}, queued_bytes{};
};
struct SampleInfo {
    int64_t receive_steady_ns{};
    int64_t dds_source_unix_ns{};
    bool source_time_valid{};
};
struct Policy {
    size_t queue_samples{16}, queue_bytes{4 * 1024 * 1024};
    bool discard_oldest{true}, reliable{false}, transient_local{false};
    int history_depth{16};
    int max_blocking_ms{20};
};
struct Event {
    std::string key, topic, type_id;
    Policy policy;
    std::function<size_t(const void *)> size;
    std::function<bool(const void *)> validate;
};
struct TransportConfig {
    uint32_t domain{0};
    bool shared_memory{false};
    std::string interface_address;
    std::vector<std::string> peers;
};
// Per-process startup settings. Unset inherits the generated value; an explicit
// empty value selects all interfaces / clears the generated peer list.
// Domain, topics and QoS remain part of the generated contract.
struct NetworkOptions {
    std::optional<std::string> interface_address;
    std::optional<std::vector<std::string>> peers;
};
TransportConfig apply_network_options(TransportConfig, const NetworkOptions &);
using Sample = std::shared_ptr<const void>;
using Receive = std::function<void(Sample, SampleInfo)>;
class Writer {
  public:
    virtual ~Writer() = default;
    virtual Result write(const void *) = 0;
    virtual int matches() const = 0;
};
class Reader {
  public:
    virtual ~Reader() = default;
    virtual int matches() const = 0;
};
// Binding owns protocol details. Neither the CM API nor its DTOs require DDS headers.
class NetworkBinding {
  public:
    virtual ~NetworkBinding() = default;
    virtual std::shared_ptr<Writer> writer(const Event &) = 0;
    virtual std::shared_ptr<Reader> reader(const Event &, Receive) = 0;
};
using BindingFactory = std::function<std::shared_ptr<NetworkBinding>()>;
class Endpoint;
class PublisherBase {
  public:
    PublisherBase() = default;
    explicit PublisherBase(std::shared_ptr<Endpoint> state) : state_(std::move(state)) {}
    Result submit(Sample);
    Metrics metrics() const;
    int matches() const;

  private:
    std::shared_ptr<Endpoint> state_;
};
template <class T> class Publisher {
  public:
    Publisher() = default;
    explicit Publisher(PublisherBase p) : base_(std::move(p)) {}
    Result try_publish(T value) {
        return base_.submit(std::make_shared<const T>(std::move(value)));
    }
    Metrics metrics() const {
        return base_.metrics();
    }
    int matches() const {
        return base_.matches();
    }

  private:
    PublisherBase base_;
};
class Runtime {
  public:
    explicit Runtime(BindingFactory);
    ~Runtime();
    Runtime(const Runtime &) = delete;
    Runtime &operator=(const Runtime &) = delete;
    PublisherBase add_publisher(Event);
    void add_subscription(Event, Receive);
    void expect_subscription(std::string key);
    Result start();
    void request_stop();
    Result stop();
    Metrics metrics(const std::string &key) const;
    int matches(const std::string &key) const;
    bool running() const;

  private:
    class Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace amw::cm
