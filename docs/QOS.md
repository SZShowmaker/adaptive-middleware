# 在界面中配置 QoS 和默认策略

前提：已按 [环境准备](GETTING_STARTED.md) 配好 SDK 和生成器。下列命令均在仓库根目录执行。当前参数目录对应 Fast DDS 3.6.2；它区分 DDS 已实现、本中间件已接入，以及尚不可使用的选项。

## 1. 不修改 QoS，也可以直接生成

```bash
./amw gui
```

打开终端给出的网址，直接点击“校验”，再点击“生成 src-gen”。默认 demo 不需要填写任何新 QoS 字段，demo 工程的默认 GUI 交付目录是 `out/delivery/demo/src-gen/`，其他工程按工程 ID 分目录。

新建策略时，输入名称并点击“新建默认策略”，即可得到可使用的策略。无需把表单中的默认值逐个保存。每个开放字段都有默认值，界面显示当前值、继承值以及是否已自定义。“恢复继承”只清除该字段的覆盖；“整份策略恢复默认”清除该策略的队列和 DDS 覆盖，使用前应留意它可能被多个实例引用。

默认采用 best_effort、volatile、KEEP_LAST 深度 16；DDS 样本上限与初始分配为 16，可靠写入最大阻塞时间为 20 ms；CM 队列为 16 个样本、4 MiB，满时丢弃最旧样本。Deadline、Lifespan 和活性租约默认无限；DDS 发布为同步模式，Data-sharing 默认关闭。普通 SHM 由独立网络开关控制。

这些是 **AMW 的版本化默认值**，不应理解为所有 Fast DDS 原始默认值。旧工程的七个策略字段仍有效，其行为保持原基线。未配置的新字段会补齐默认值，不改写源 JSON。默认值目录版本会记录在生成清单和 `metadata/qos.effective.json` 中。

## 2. 修改输出消息的可靠性

1. 右侧点击“QoS / 默认策略 / 网络”。
2. 保持“消息策略模板”，选择要修改的策略，例如 demo 的 `state`。
3. 作用范围选择“输出 · DataWriter”，将“可靠性”从 `best_effort` 改为 `reliable`。
4. 点击“应用”。如有字段或组合错误，窗口会保留输入并显示错误，可直接修正重试。
5. 点击主界面的“校验”，检查整个工程的收发兼容性；通过后“保存草稿”，再“生成 src-gen”。
6. 交付完整 src-gen；应用工程师重新编译受影响的应用。

Reader 要求 reliable 而对应 Writer 是 best_effort 会被拒绝。修改共享模板影响所有引用它的实例或端点；只想修改某个消息时，先“复制当前策略”，再按下一节给目标端点选择新策略。

## 3. 实例、端点与分组参数

“实例与消息策略分配”中，先选择部署实例，再选择实例默认消息策略。选择具体输入或输出消息后，可用下拉框设置端点策略覆盖，或恢复继承。下面会显示该端点的完整有效值。“编辑所用策略”跳转到对应模板；它不会自动创建仅属于该端点的新模板。

模板中的 `Topic` 值作为对应 Reader/Writer 同名字段的默认值，Reader/Writer 显式覆盖优先。同一个 Runtime 共用 Participant、Publisher 和 Subscriber；这些参数在“项目网络与默认 QoS”中设置，也可以在具体实例中覆盖。实例覆盖以整个字段为单位，例如替换一份列表或资源分配结构。

生效顺序如下：

| 配置范围 | 优先顺序（右侧优先） |
|---|---|
| 选择消息模板 | 实例默认策略 → 单个消息端点策略 |
| 模板中的消息参数 | AMW 默认值 → 旧版公共字段 → Topic 同名字段 → Writer/Reader 显式字段 |
| 通信实例和分组 | AMW 默认值 → 项目 QoS → 实例 QoS |

界面提供枚举下拉框、布尔开关、带范围的数值输入、秒/纳秒时间、无限时间/容量选项，以及可增删的列表和嵌套表单。64 位线程亲和掩码使用十进制字符串保存，避免浏览器数值精度损失。十六进制数据每两个字符表示一个字节，例如 `414d57`。

此页面可编辑现有实例的 QoS 和策略分配；实例新增、删除及来源绑定的复杂调整仍使用“编辑完整模型”。App 新建时会建立默认实例。网络域、普通 SHM、网卡地址及发现对端已提供表单。

## 4. 当前开放范围和限制

| 参数组 | 已接入的配置 |
|---|---|
| 标准消息策略 | Reliability、Durability（volatile / transient_local）、History、ResourceLimits、Deadline、Lifespan、Liveliness（automatic）、Ownership、OwnershipStrength、TransportPriority |
| 标准实体附加信息 | UserData、TopicData、GroupData、Partition；EntityFactory 显示固定的自动启用值 |
| DDS 类型扩展 | XCDR1 / XCDR2 表示、Reader 类型一致性设置；仍要求本项目契约与版本一致 |
| 发布与数据共享 | 同步/异步发布、具名流量控制器及其调度/容量/周期/线程、Data-sharing off/auto/on、目录/域 ID/域数上限 |
| RTPS | Writer/Reader 可靠传输时序、关闭正向 ACK、心跳附带开关、历史内存分配策略、UDPv4 端点地址列表 |
| 资源和线程 | Participant/Writer/Reader 的已建模资源分配、发送缓冲区、发现数据限制、定时/内置发送/类型查找/Data-sharing 监听线程 |
| 发现和传输 | SIMPLE 发现租约与通告周期、默认 UDPv4 地址、套接字缓冲区、现有 Domain/网卡/peers/普通 SHM 设置 |
| 属性 | 可传播的自定义发现元数据；内置功能的保留属性名不能绕过专用配置与校验 |

界面“不支持的策略 / 选项”会列出具体原因：

- Fast DDS 3.6.2 官方文档标注未实现的 DestinationOrder、DurabilityService、LatencyBudget、Presentation、ReaderDataLifecycle、TimeBasedFilter、WriterDataLifecycle 不开放覆盖。
- transient/persistent 持久化服务、手动活性断言、延迟启用实体、内容过滤、安全插件等需要对应的 CM 接口或部署能力，当前尚未接入。
- Discovery Server/STATIC、自定义 GUID、外部地址映射、TCP/TLS/自定义传输、任意内置插件属性不属于已接入的配置。它们明确显示为不可用，不会保存一个看似有效但实际被忽略的值。

因此，本次提供标准与扩展的可视化配置框架和上述有效参数，**不声明每一个 Fast DDS API 成员都已接入**。准确范围以参数目录及本表为准。官方依据：[标准 QoS](https://fast-dds.docs.eprosima.com/en/v3.6.2/fastdds/dds_layer/core/policy/standardQosPolicies.html)、[Fast DDS 扩展](https://fast-dds.docs.eprosima.com/en/v3.6.2/fastdds/dds_layer/core/policy/eprosimaExtensions.html)。

## 5. 校验怎样帮助排错

表单“应用”检查部署字段及单个策略一致性；主界面“校验”和生成器还会检查完整工程。CLI 与 GUI 共用后端规则：

- 字段类型、枚举、数值/时间边界、未知字段与不可用选项。
- KEEP_LAST 深度与资源上限、初始分配、资源增长方式、发现和活性通告周期。
- Writer/Reader 的可靠性、持久性、Deadline、活性租约、所有权、数据表示、ACK 模式和分区匹配。
- 流量控制器引用及发布模式、Data-sharing 域数/内存分配条件、同一 Runtime 内相同 Topic 的 QoS 一致性。

错误包含实例、端点或策略字段路径，阻止生成。无限容量、无 key 类型的实例上限、线程平台依赖、Data-sharing 实际使用条件等会给出警告。校验通过不代表硬实时、业务处理确认或实际容量已验证。Deadline 不替业务周期发布；当前 CM 没有暴露 deadline/liveliness 状态回调。

如果应用启动失败，保留 `runtime.start()` 的 `Result.detail`，并核对目标机器的线程权限、内存、地址与共享目录。库会在创建 DDS 实体时做最终检查；失败后回滚。修改 `metadata/` 中的 JSON 不会改变运行行为，也不能绕过重新生成、编译。

## 6. 可直接运行的自定义策略示例

仓库提供完整工程 [examples/qos/project.cm.json](../examples/qos/project.cm.json)，复用 demo 的业务消息。它配置了 reliable、transient_local、历史深度 3、分区、异步发布和流量控制器，并为一个输出单独选择策略。示例用于验证配置，不是项目容量建议。

```bash
./amw validate --project examples/qos/project.cm.json
./amw build --demo --project examples/qos/project.cm.json \
  --output out/delivery/qos/src-gen --build-dir out/build/qos
```

预期得到 `out/delivery/qos/src-gen/` 和 `out/build/qos/amw_producer`、`amw_consumer`。需要 SDK/Gen；失败时先按 [排错指南](TROUBLESHOOTING.md) 检查环境。实际网络验证方法和各平台证据见 [验证记录](VALIDATION.md)。

只查看生成结果时，首先读 `metadata/qos.effective.json`：它按实例和端点列出最终值、模板名和警告。`generated/qos.hpp` 是私有 DDS 配置实现，已被 `apps.cpp` 引用；业务仍只包含 `apps.hpp`。

## 7. 维护参数目录

`tools/amw_tool/qos.py` 维护字段类型、默认值、支持条件和 C++ 映射，GUI 从同一目录获取控件描述。调整后同步 schema：

```bash
python3 tools/update_qos_schema.py
python3 tools/update_qos_schema.py --check
python3 -m unittest discover -s tests -p 'test_qos.py'
```

新增参数必须检查实际 SDK 头文件、生成后编译和必要的行为验证，不能仅因为 JSON 能保存就宣称已支持。默认值变化应更新默认值目录版本与迁移说明，不能悄悄改变旧工程的含义。
