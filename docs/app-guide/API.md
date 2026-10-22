# CM 接口介绍与调用规则

本文适用于各 App 的生成接口。代码中的具体类型、成员和实例名是**固定示例**，实际名称以自己的 `apps.hpp`、`types.hpp` 和配置快照为准。文中的“端口”是服务端口名称，不是 UDP 数字端口。

## 1. 找到自己的接口

业务通常只需要：

```cpp
#include "apps.hpp"
```

生成的业务类型和 App 类位于 `amw_generated`，公共通信 API 位于 `amw::cm`。命名对应如下：

| 配置 | 生成接口举例 |
|---|---|
| App ID 为 producer | `amw_generated::producer` |
| producer 的部署实例为 camera_front | 构造时使用 `producer app("camera_front")` |
| 输出端口 perception，消息 frame | 发布成员 `app.perception_frame` |
| 输入端口 perception，消息 frame | 注册函数 `app.on_perception_frame(...)` |
| 类型 demo.Frame，版本 1.0.0 | `amw_generated::demo_Frame_v1_0_0` |
| 统计端点键 | `"perception.frame"`，不是成员名的下划线形式 |

App ID 和部署实例 ID 不同。一个 App 类可对应多个实例，实例决定实际路由来源；构造时不能传入别的 App 的实例。App 构造完成只建立本地端点配置，还需要调用 start。

`apps.hpp` 是精确接口声明；`metadata/model.resolved.json` 的 `deployment.instances` 用于查实例属于哪个 App；`metadata/routes.json` 顶层按实例列出端点及策略。当前不会读取这些 JSON 文件来动态创建端点，配置已固化到 `apps.cpp` 及私有 `qos.hpp`；完整有效值见 `metadata/qos.effective.json` 和 [QoS 说明](QOS.md)。

### 启动时选择本机网络

构造 App 时可传入 `amw::cm::NetworkOptions`。下面是需放在业务函数中的片段；完整可编译示例见 `examples/publisher.cpp`。

```cpp
amw::cm::NetworkOptions network;
network.interface_address = "192.168.10.2"; // 本机已配置的 IPv4 地址
network.peers = std::vector<std::string>{"192.168.10.1"}; // 发现对端
amw_generated::producer app("camera_front", network);
```

未设置的字段继承生成工程；显式设置空字符串表示使用所有网卡，空 vector 清除生成的初始对端列表。地址必须是四段十进制 IPv4，不支持主机名、IPv6、端口或前导零。格式错误会在 `runtime.start()` 返回失败，详情见 `Result.detail`；地址格式正确不代表该网卡实际存在或对端可达。

构造时复制这些选项，后续修改原变量不影响 App；切换网卡需停止并重建 App。`amw_generated::domain_id` 提供只读的生成 Domain，Domain、Topic、类型、路由与 QoS 均保持生成工程中的值。对端列表用于发现，并非访问控制白名单；该功能不会改写交付包或运行时读取工程 JSON。

## 2. 消息类型怎样使用

`types.hpp` 中是普通 C++ 结构体和枚举，不是 DDS 实体。字段用点号访问，不使用 wire 类型的 getter/setter。

| 定义形式 | 业务侧 C++ 类型 / 约定 |
|---|---|
| bool、定宽整数 | bool、int8_t/uint8_t 等；位宽以类型为准。 |
| float32 / float64 | float / double；发送时要求有限值，NaN/Inf 不合法。 |
| 有界字符串 | std::string；最大长度按字节限制，不按汉字个数。 |
| 固定数组 | std::array<T, N>；元素个数固定。 |
| 有界列表 | std::vector<T>；可以为空，元素数不可超过配置上限。 |
| 自定义结构体 | 直接嵌套对应生成类型。 |
| 枚举 | enum class，底层 int32_t；当前从 0 按定义顺序编号，不应随意强制转换整数。 |

字段会值初始化，但全零或空值是否有业务意义由契约决定。字段 `id` 是协议字段编号，不等于某条消息中的目标编号。单位和描述查模型快照，未写明时不能猜测。

以固定 demo 为例：

```cpp
amw_generated::demo_Frame_v1_0_0 frame{};
frame.frame_id = 1;
frame.speed = 12.5f;
frame.objects.push_back({7, 3.0f});
```

类型边界保留在模型中，vector/string 本身不会阻止你构造超限消息。生成的 `valid(message)` 可检查类型约束，真正发布还要受队列字节预算限制；`bytes(message)` 是中间件内存估算，不是线上序列化长度。程序不会直接发送结构体内存布局，当前 DTO 与 DDS 内部类型之间有转换和复制。

## 3. App 与 Runtime 的生命周期

推荐调用顺序：

```text
准备回调依赖的业务资源 → 构造 App → 注册全部输入回调
        → start 并检查结果 → 发布 / 接收 → 外部线程 stop
        → 释放 App 和业务资源
```

| API | 返回值和作用 | 调用约定 |
|---|---|---|
| `App(const std::string& instance, NetworkOptions network = {})` | 构造生成 App；实例不属于此 App 时抛 std::invalid_argument。 | 一个对象选一个实例；构造可能还有分配等异常。 |
| `runtime.start()` | 返回 Result；创建绑定/端点、启动工作线程。 | 第一次调用前完成所有配置，控制线程调用。 |
| `runtime.running()` | 返回 bool，本地运行标志。 | 不代表远端在线；false 也不保证工作线程已退出。 |
| `runtime.request_stop()` | void；停止接纳并丢弃待处理队列，提出退出请求。 | 可以在回调中调用；不等待工作线程完成。 |
| `runtime.stop()` | 返回 Result；等待已进入的工作结束，释放端点/绑定。 | 在外部控制线程完成；不是发送队列 flush。 |

首次 start 会冻结端点配置，**即使这次启动失败也已冻结**。已正确配置的对象可 stop 后再 start；若失败原因是漏注册回调，需要重新构造对象后补齐配置，不能在冻结对象上补注册。重复 start 在已经运行时返回成功，重复 stop 可用。

启动失败时会回滚本次已创建资源，详情放在 `Result.detail`。当前 start 对捕获的配置/资源异常统一返回 transport_error，因此应看 detail，不能只按错误码猜原因。

接收回调可能在 start 返回前就被调用，尤其是存在历史样本时。回调访问的对象必须先准备好。App/Runtime 不提供复制能力；不要在自己的回调里销毁 App，当前实现会终止进程。

## 4. 发布接口

每个生成的输出成员都是 `amw::cm::Publisher<T>`，主要接口为：

```cpp
amw::cm::Result try_publish(T value);
amw::cm::Metrics metrics() const;
int matches() const;
```

示意调用如下，需置于已经构造并启动 App 的业务函数中：

```cpp
auto result = app.perception_frame.try_publish(std::move(frame));
if (!result) {
    // 根据 result.code 决定是否丢弃、稍后提交新样本或报告异常。
    // result.detail 提供端点或错误说明。
}
```

消息按值传入。传左值会复制，std::move 可转移容器等资源；即使提交失败，传入的原对象也可能已被移动，不能假设还能用原 frame 重试。需要重试相同内容时，应在移动前保存业务所需数据或重新构造消息。

调用成功只表示本地队列接纳了消息。发送线程稍后调用 DDS write，底层失败记到 send_failed，不会异步修改已经返回的 Result。sent 增加也不表示对方业务已处理；需要业务确认时，应定义额外的应用协议。

队列满时按配置处理：reject 策略返回 queue_full；discard_oldest 策略丢弃旧样本并接纳新样本，返回成功，replaced 增加。try_publish 内仍有对象分配、校验和锁操作，不保证硬实时、零分配或无异常。

## 5. 订阅与回调

每个输入消息有一个生成注册函数，形式为：

```cpp
void on_<端口>_<消息>(
    std::function<void(std::shared_ptr<const T>, amw::cm::SampleInfo)> callback);
```

上面是命名说明，不是可直接编译的 C++ 声明。以下是固定 demo 的实际注册形式：

```cpp
app.on_perception_frame([](
    std::shared_ptr<const amw_generated::demo_Frame_v1_0_0> sample,
    amw::cm::SampleInfo info) {
    // sample->frame_id、sample->objects 等可在此读取。
    // info 是通信时间信息，不自动等于传感器采集时间。
});
```

- 必须在第一次 start 前给所有已配置输入注册回调。demo consumer 还有 health 输入，不能只注册 frame。
- 每个输入只注册一次。重复注册会抛 `std::invalid_argument`（duplicate endpoint key），传空回调也会抛异常；start 后注册会因配置冻结抛 `std::logic_error`。
- 同一个输入端点依次调用回调，不同输入端点有不同工作线程，可能同时调用。不要假设同一个 App 的回调天然串行。
- 收到的 shared_ptr 拥有消息对象，可以复制并保存以延后处理；不要只保存裸指针或引用。不要修改只读消息。长期保留样本的内存不受内部队列上限约束。
- 回调应尽快完成，耗时任务可交给业务自己的有界工作队列。业务状态被多个线程访问时自行同步。
- 回调抛异常会计入 callback_failed，工作线程继续处理后续消息；当前不保存异常文本，业务应自行记录。

没有单独的取消订阅/更换回调 API。当前以整个 App 的端点集合一起启停，不能通过修改回调或 JSON 来热切换输入。

## 6. 正确退出与线程安全

构造、注册回调、start、stop、销毁应由一个控制线程管理，不要并发修改端点配置。运行期间可以提交消息、读取指标、提出 request_stop，但必须保证 App 和发布句柄仍有效；不要让业务线程在对象销毁后继续调用它们。

stop 会丢弃尚在队列中的消息，等待已开始的发送/回调结束，再释放 DDS 端点。request_stop 不完成等待；`running()==false` 不能代替 stop。若回调长期阻塞，外部 stop 也会等待它，业务需要可结束的任务和等待条件。

在本 App 回调中调用 stop，会提出停止请求并返回 would_deadlock，仍需外部拥有者调用 stop 完成清理。回调里更明确的写法是 request_stop；不要调用 start，也不要销毁 App。中间件锁和容器不提供异步信号处理器安全保证，POSIX 信号处理器应只通知控制线程去执行停止。

回调捕获的对象要活到 stop 完成。例如计数器声明在 App 前面，或在作用域退出前显式 stop；不能先销毁被捕获对象，再等 App 析构触发停止。完整安全示例见 [subscriber.cpp](examples/subscriber.cpp)。

## 7. Result 与异常

Result 有 `code`、`detail`，显式 bool 转换仅在 code 为 ok 时为真。建议写 `if (!result)`；枚举未声明稳定的外部数字协议，不要把数值硬编码成业务协议。

| Code | 当前常见位置与含义 |
|---|---|
| ok | 本次操作成功，含义由操作决定；发布成功仅表示接纳。 |
| not_running | 发布端点未接纳消息，或使用空发布句柄。 |
| queue_full | reject 策略下队列样本数或估算字节数达到限制。 |
| invalid_sample | 类型校验失败、非法浮点/枚举/边界，或样本超过队列字节预算。 |
| transport_error | start 捕获的配置/资源异常，或后端写入失败；后者通常反映在 send_failed。 |
| would_deadlock | 本 Runtime 回调内调用 start/stop；stop 已发起停止请求但未完成等待。 |
| invalid_configuration | 已声明的枚举项；当前实现没有统一使用它返回所有配置错误。 |

构造 App、注册回调和底层内存分配仍可能抛 C++ 异常；不要把 Result 理解成所有接口都 noexcept。业务入口应捕获 std::exception 记录原因，并安排清理。start 失败后不要继续当作正常运行去发布。

## 8. 匹配数、指标与时间戳

发布成员可以直接调用 metrics()/matches()。订阅端点和统一查询使用：

```cpp
auto counts = app.runtime.metrics("perception.frame");
int matched = app.runtime.matches("perception.frame");
```

端点键从 routes.json 查找，点号和下划线不要混淆。不存在的键当前返回零值，不会抛错误；拼错键可能被误判为没流量。metrics 是各端点的快照，不是跨端点同一时刻的原子快照。统计在同一对象的 stop/start 间累计。

| Metrics 字段 | 含义 |
|---|---|
| submitted | 通过初始类型校验并进入队列提交逻辑的次数；早期非法样本不计入。 |
| accepted | 队列接纳次数；不等于网络送达。 |
| replaced | 为接纳新样本而丢弃的旧样本数。 |
| rejected | 拒绝接纳与停止时丢弃的待处理样本都会计入。 |
| sent / send_failed | 发送线程的 DDS write 成功/失败次数。 |
| received | 接收侧队列接纳次数，不等于所有到达网卡的数据量。 |
| delivered / callback_failed | 业务回调正常返回/抛异常的次数。 |
| queue_high_water | 队列历史最大样本数。 |
| queued_bytes | 当前排队消息的估算内存，不包含全部 DDS 缓存或业务持有样本。 |

matches 是当前端点 DDS 匹配数。匹配存在不代表对方算法正常，计数差异也不能直接当作网络丢包率。

匹配查询可以与接收并发执行；实现不会持有 CM 队列锁调用绑定的状态查询。
与 stop 重叠的查询会保留所查询端点的生命周期，可能返回停止前端点的匹配数，
所以不能用一次 matches 的结果判断 stop 是否完成。查询期间 App/Runtime 本身仍须有效。

| SampleInfo 字段 | 含义 |
|---|---|
| receive_steady_ns | 本进程接收侧记录的单调时钟时间，单位纳秒。适合本地时间间隔，不直接跨机器比较。 |
| dds_source_unix_ns | DDS 源时间换算的 Unix 纳秒时间。 |
| source_time_valid | 源时间是否有效；为 false 时不能使用上面的源时间。 |

这些时间不自动等于设备采集时间。需要传感器对齐和跨设备时延分析时，由协议携带明确的采集时间字段，并约定时钟同步方式。

## 9. 配置影响接口的哪些行为

| 配置 | 业务开发者需要知道什么 |
|---|---|
| queue_samples / queue_bytes | 分别限制样本数和估算内存；容器容量也影响估算。 |
| overflow | 选择丢旧样本或拒绝新样本，影响 try_publish 结果和计数。 |
| reliability | DDS 尽力或可靠传输，不能替代业务确认与业务消费能力设计。 |
| durability / history_depth | 控制 DDS 的历史行为，与 CM 工作队列是不同层次。 |
| max_blocking_ms | 底层可靠写入配置，不是 try_publish 的整体耗时保证。 |
| domain / interface_address / peers | 决定发现与网络条件；改变需要重新生成编译。 |
| shared_memory | 在 UDP 之外启用普通共享内存传输；实际路径取决于环境，不等于零拷贝。 |

公共头文件还暴露 Event、Policy、NetworkBinding、Writer、Reader，以及 Runtime 的 add_publisher/add_subscription/expect_subscription。这些用于生成实现或中间件扩展。使用本生成包时由工具配置它们，业务不需要手工增删端点；不要修改某个局部 Policy 对象并期望已运行 App 自动变更策略。

新增协议绑定、动态发现 API 或请求应答能力时，应由中间件层统一定义语义并更新手册，不能把现有发布成功当作请求已完成。
