#pragma once
// Only generated backend glue and the Fast DDS binding include this header.
#include <amw/cm/cm.hpp>
#include <fastdds/dds/topic/TypeSupport.hpp>
#include <fastdds/dds/domain/qos/DomainParticipantQos.hpp>
#include <fastdds/dds/publisher/qos/PublisherQos.hpp>
#include <fastdds/dds/subscriber/qos/SubscriberQos.hpp>
#include <fastdds/dds/topic/qos/TopicQos.hpp>
#include <fastdds/dds/publisher/qos/DataWriterQos.hpp>
#include <fastdds/dds/subscriber/qos/DataReaderQos.hpp>
#include <unordered_map>
namespace amw::cm::fastdds {
struct TypeRegistration {
    eprosima::fastdds::dds::TypeSupport support;
    std::function<std::shared_ptr<void>(const void *)> encode;
    std::function<Sample(const void *)> decode;
};
using TypeRegistry = std::unordered_map<std::string, TypeRegistration>;
// Private backend configuration; these DDS types never appear in apps.hpp or cm.hpp.
struct QosConfig {
    eprosima::fastdds::dds::DomainParticipantQos participant;
    eprosima::fastdds::dds::PublisherQos publisher;
    eprosima::fastdds::dds::SubscriberQos subscriber;
    std::unordered_map<std::string, eprosima::fastdds::dds::TopicQos> topics;
    std::unordered_map<std::string, eprosima::fastdds::dds::DataWriterQos> writers;
    std::unordered_map<std::string, eprosima::fastdds::dds::DataReaderQos> readers;
};
std::shared_ptr<NetworkBinding> create(TransportConfig, TypeRegistry);
std::shared_ptr<NetworkBinding> create(TransportConfig, TypeRegistry, QosConfig);
} // namespace amw::cm::fastdds
