// Consume examples/qos delivery. Checks DDS semantics through the public App API.
#include "apps.hpp"
#include "qos.hpp"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>

using namespace std::chrono_literals;
namespace amw_generated { amw::cm::fastdds::TypeRegistry registry(); }
static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
template<class Predicate> static void wait_for(Predicate predicate, const char* message) {
    const auto until=std::chrono::steady_clock::now()+8s;
    while (!predicate() && std::chrono::steady_clock::now()<until) std::this_thread::sleep_for(20ms);
    require(predicate(),message);
}
int main() {
    try {
        auto configured=amw_generated_qos::make("camera_front");
        namespace dds=eprosima::fastdds::dds;
        require(configured.writers.at("perception.frame").publish_mode().kind==dds::ASYNCHRONOUS_PUBLISH_MODE,"publish mode not generated");
        require(configured.writers.at("perception.frame").history().depth==3,"history depth not generated");
        require(configured.participant.flow_controllers().size()==1,"flow controller not generated");
        require(configured.participant.flow_controllers().front()->max_bytes_per_period==1048576,"flow limit not generated");
        require(configured.writers.at("perception.health").publish_mode().flow_controller_name==eprosima::fastdds::rtps::FASTDDS_FLOW_CONTROLLER_DEFAULT,"default flow controller must use SDK constant");

        amw_generated::producer writer("camera_front");
        auto started=writer.runtime.start();require(bool(started),started.detail.c_str());
        // Publish before ANY reader exists. Transient-local + depth 3 must retain
        // the final three samples, not all eight and not zero.
        for(int n=0;n<8;++n) {
            amw_generated::demo_Frame_v1_0_0 frame;frame.frame_id=n;
            require(bool(writer.perception_frame.try_publish(frame)),"publish failed");
            std::this_thread::sleep_for(30ms);
        }
        wait_for([&]{return writer.perception_frame.metrics().sent==8;},"writer did not drain");
        require(writer.perception_frame.metrics().send_failed==0,"DDS write failed");
        std::mutex mutex;std::vector<int> ids;
        amw_generated::consumer reader("monitor");
        reader.on_perception_frame([&](auto frame,auto){std::lock_guard<std::mutex> lock(mutex);ids.push_back(static_cast<int>(frame->frame_id));});
        reader.on_perception_health([](auto,auto){});
        started=reader.runtime.start();require(bool(started),started.detail.c_str());
        wait_for([&]{std::lock_guard<std::mutex> lock(mutex);return ids.size()>=3;},"late reader did not receive retained history");
        std::this_thread::sleep_for(200ms);
        reader.runtime.stop();
        std::sort(ids.begin(),ids.end());require(ids==std::vector<int>({5,6,7}),"wrong retained history depth/content");
        writer.runtime.stop();
        // Failed creation of a reader after participant/group creation must clean
        // up. A later fresh App must still start and discover normally.
        auto invalid=amw_generated_qos::make("monitor");
        invalid.readers.at("perception.frame").history().depth=0;
        amw::cm::TransportConfig transport;transport.domain=149;
        auto binding=amw::cm::fastdds::create(transport,amw_generated::registry(),std::move(invalid));
        amw::cm::Event event;event.key="perception.frame";event.type_id="demo.Frame@1.0.0";event.topic="amw/test/qos_failure";
        bool failed=false;
        try {binding->reader(event,[](auto,auto){});} catch(const std::exception& e) {failed=std::string(e.what()).find("DDS reader creation failed")!=std::string::npos;}
        require(failed,"invalid QoS was not rejected by DDS");binding.reset();
        started=writer.runtime.start();require(bool(started),started.detail.c_str());writer.runtime.stop();
        std::cout<<"PASS: emitted QoS matches SDK; late reader receives exactly retained samples 5,6,7; binding failure cleanup and restart\n";
        return 0;
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
