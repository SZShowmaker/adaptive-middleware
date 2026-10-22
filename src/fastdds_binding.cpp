#include <amw/cm/fastdds_binding.hpp>
#include <fastdds/dds/domain/DomainParticipant.hpp>
#include <fastdds/dds/domain/DomainParticipantFactory.hpp>
#include <fastdds/dds/publisher/DataWriter.hpp>
#include <fastdds/dds/publisher/Publisher.hpp>
#include <fastdds/dds/subscriber/DataReader.hpp>
#include <fastdds/dds/subscriber/DataReaderListener.hpp>
#include <fastdds/dds/subscriber/Subscriber.hpp>
#include <fastdds/dds/topic/Topic.hpp>
#include <fastdds/rtps/transport/UDPv4TransportDescriptor.hpp>
#include <fastdds/rtps/transport/shared_mem/SharedMemTransportDescriptor.hpp>
#include <fastdds/utils/IPLocator.hpp>
#include <mutex>
#include <stdexcept>
namespace amw::cm::fastdds {
namespace dds = eprosima::fastdds::dds;
namespace rtps = eprosima::fastdds::rtps;
class Binding;
class NativeWriter : public Writer {
  public:
    std::shared_ptr<Binding> owner;
    dds::DataWriter *value{};
    TypeRegistration type;
    ~NativeWriter() override;
    Result write(const void *data) override {
        auto wire = type.encode(data);
        auto result = value->write(wire.get());
        return result == dds::RETCODE_OK
                   ? Result{}
                   : Result{Code::transport_error,
                            "DDS write failed: " + std::to_string(static_cast<int>(result))};
    }
    int matches() const override {
        dds::PublicationMatchedStatus s;
        return value->get_publication_matched_status(s) == dds::RETCODE_OK ? s.current_count : 0;
    }
};
class NativeReader : public Reader, public dds::DataReaderListener {
  public:
    std::shared_ptr<Binding> owner;
    dds::DataReader *value{};
    TypeRegistration type;
    Receive receive;
    ~NativeReader() override;
    int matches() const override {
        dds::SubscriptionMatchedStatus s;
        return value->get_subscription_matched_status(s) == dds::RETCODE_OK ? s.current_count : 0;
    }
    void on_data_available(dds::DataReader *reader) override {
        // Listener does no user work; conversion creates an owned business DTO before queueing.
        void *data = type.support->create_data();
        if (!data)
            return;
        dds::SampleInfo info;
        try {
            while (reader->take_next_sample(data, &info) == dds::RETCODE_OK) {
                if (!info.valid_data)
                    continue;
                SampleInfo meta;
                meta.receive_steady_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                                             std::chrono::steady_clock::now().time_since_epoch())
                                             .count();
                meta.dds_source_unix_ns =
                    int64_t(info.source_timestamp.seconds()) * 1000000000LL + info.source_timestamp.nanosec();
                meta.source_time_valid = meta.dds_source_unix_ns > 0;
                receive(type.decode(data), meta);
            }
        } catch (...) { /* never unwind through middleware callback */
        }
        type.support->delete_data(data);
    }
};
class Binding : public NetworkBinding, public std::enable_shared_from_this<Binding> {
  public:
    dds::DomainParticipant *participant{};
    dds::Publisher *pub{};
    dds::Subscriber *sub{};
    TypeRegistry types;
    std::shared_ptr<const QosConfig> profiles;
    std::mutex mutex;
    std::unordered_map<std::string, dds::Topic *> topics;
    Binding(TransportConfig config, TypeRegistry registry, std::shared_ptr<const QosConfig> qos_profiles = {})
        : types(std::move(registry)), profiles(std::move(qos_profiles)) {
        try {
            dds::DomainParticipantQos qos = profiles ? profiles->participant : dds::DomainParticipantQos{};
            qos.transport().use_builtin_transports = false;
            auto udp = std::make_shared<rtps::UDPv4TransportDescriptor>();
            udp->sendBufferSize = profiles ? qos.transport().send_socket_buffer_size : 2 * 1024 * 1024;
            udp->receiveBufferSize = profiles ? qos.transport().listen_socket_buffer_size : 2 * 1024 * 1024;
            if (!config.interface_address.empty())
                udp->interfaceWhiteList.push_back(config.interface_address);
            qos.transport().user_transports.push_back(udp);
            if (config.shared_memory)
                qos.transport().user_transports.push_back(
                    std::make_shared<rtps::SharedMemTransportDescriptor>());
            for (auto &ip : config.peers) {
                rtps::Locator_t l;
                l.kind = LOCATOR_KIND_UDPv4;
                l.port = 0;
                if (!rtps::IPLocator::setIPv4(l, ip))
                    throw std::invalid_argument("invalid peer IPv4");
                qos.wire_protocol().builtin.initialPeersList.push_back(l);
            }
            if (!profiles) {
                qos.wire_protocol().builtin.discovery_config.leaseDuration = {6, 0};
                qos.wire_protocol().builtin.discovery_config.leaseDuration_announcementperiod = {2, 0};
            }
            participant =
                dds::DomainParticipantFactory::get_instance()->create_participant(config.domain, qos);
            if (!participant)
                throw std::runtime_error("DDS participant creation failed");
            for (auto &entry : types)
                if (entry.second.support.register_type(participant) != dds::RETCODE_OK)
                    throw std::runtime_error("DDS type registration failed: " + entry.first);
            pub = participant->create_publisher(profiles ? profiles->publisher : dds::PUBLISHER_QOS_DEFAULT);
            sub = participant->create_subscriber(profiles ? profiles->subscriber : dds::SUBSCRIBER_QOS_DEFAULT);
            if (!pub || !sub)
                throw std::runtime_error("DDS group creation failed");
        } catch (...) {
            cleanup();
            throw;
        }
    }
    ~Binding() override {
        cleanup();
    }
    void cleanup() {
        if (participant) {
            participant->delete_contained_entities();
            dds::DomainParticipantFactory::get_instance()->delete_participant(participant);
            participant = nullptr;
        }
    }
    dds::Topic *topic(const Event &e) {
        auto found = topics.find(e.topic);
        if (found != topics.end())
            return found->second;
        auto &type = types.at(e.type_id);
        auto *t = participant->create_topic(e.topic, type.support.get_type_name(),
                                           profiles ? profiles->topics.at(e.key) : dds::TOPIC_QOS_DEFAULT);
        if (!t)
            throw std::runtime_error("DDS topic creation failed: " + e.topic);
        topics[e.topic] = t;
        return t;
    }
    template <class Q> void policy(Q &q, const Policy &p) {
        q.reliability().kind = p.reliable ? dds::RELIABLE_RELIABILITY_QOS : dds::BEST_EFFORT_RELIABILITY_QOS;
        q.reliability().max_blocking_time = {p.max_blocking_ms / 1000,
                                             static_cast<uint32_t>((p.max_blocking_ms % 1000) * 1000000)};
        q.durability().kind =
            p.transient_local ? dds::TRANSIENT_LOCAL_DURABILITY_QOS : dds::VOLATILE_DURABILITY_QOS;
        q.history().kind = dds::KEEP_LAST_HISTORY_QOS;
        q.history().depth = p.history_depth;
        q.resource_limits().max_samples = p.history_depth;
        q.resource_limits().max_instances = 1;
        q.resource_limits().max_samples_per_instance = p.history_depth;
        q.resource_limits().allocated_samples = p.history_depth;
        q.endpoint().history_memory_policy = rtps::PREALLOCATED_WITH_REALLOC_MEMORY_MODE;
        q.data_sharing().off();
    }
    std::shared_ptr<Writer> writer(const Event &e) override {
        std::lock_guard<std::mutex> l(mutex);
        auto w = std::make_shared<NativeWriter>();
        w->owner = shared_from_this();
        w->type = types.at(e.type_id);
        dds::DataWriterQos q;
        if (profiles) q = profiles->writers.at(e.key);
        else policy(q, e.policy);
        w->value = pub->create_datawriter(topic(e), q);
        if (!w->value)
            throw std::runtime_error("DDS writer creation failed: " + e.key + " (check QoS and target resources)");
        return w;
    }
    std::shared_ptr<Reader> reader(const Event &e, Receive receive) override {
        std::lock_guard<std::mutex> l(mutex);
        auto r = std::make_shared<NativeReader>();
        r->owner = shared_from_this();
        r->type = types.at(e.type_id);
        r->receive = std::move(receive);
        dds::DataReaderQos q;
        if (profiles) q = profiles->readers.at(e.key);
        else policy(q, e.policy);
        r->value = sub->create_datareader(topic(e), q, r.get());
        if (!r->value)
            throw std::runtime_error("DDS reader creation failed: " + e.key + " (check QoS and target resources)");
        return r;
    }
};
NativeWriter::~NativeWriter() {
    if (value)
        owner->pub->delete_datawriter(value);
}
NativeReader::~NativeReader() {
    if (value)
        owner->sub->delete_datareader(value);
}
std::shared_ptr<NetworkBinding> create(TransportConfig c, TypeRegistry r) {
    return std::make_shared<Binding>(std::move(c), std::move(r));
}
std::shared_ptr<NetworkBinding> create(TransportConfig c, TypeRegistry r, QosConfig q) {
    return std::make_shared<Binding>(std::move(c), std::move(r), std::make_shared<const QosConfig>(std::move(q)));
}
} // namespace amw::cm::fastdds
