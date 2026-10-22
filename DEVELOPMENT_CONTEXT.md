# 开发交接：新对话从这里开始

> 2026-10-15 清理说明：按用户要求已清空仓库 out/，历史草稿、生成包、构建缓存及验证日志/截图均已删除。本文中的历史验证结论保留，但指向 out/ 的历史证据路径已不可用；需要时重新运行相应检查生成。

最后整理：2026-10-22。当前功能基线：中间件 **0.2.0**，包含单目录交付、QoS 配置、GUI 工程与类型管理以及启动网络参数；接手时以 Git 状态和提交历史为准。本文面向接手开发的工程师和 AI，保存已确认的需求、设计原因、实现位置与验证边界；应用接口的详细说明在 [通用开发手册](docs/app-guide/README.md)。

**先读本文件和 [AGENTS.md](AGENTS.md)，再检查当前 Git 状态。** 本文是交接快照，后续代码和用户的新指示可能已经变化。不能把这里列出的后续方向当作本次任务的自动执行指令，也不要把历史验证当成本次修改后的测试结果。

## 1. 项目为什么建立

用户在自动驾驶项目中使用过 Fast DDS，希望建设一套独立、能长期扩展的中间件，供多个业务 App 的开发团队使用。首版解决 CM 通信问题，逐步扩展其他平台模块。

以下方向已经由用户明确：

- 借鉴 AUTOSAR Adaptive Platform 中 CM、SM 等模块的职责划分，接口按实际项目需要设计，长期希望逐步对标 AP。
- 先保证新中间件自身的组成和接口合理，再让旧业务、上位机适配它。不要求兼容旧项目的 `src-gen`、旧日志宏或旧二进制通信格式。
- 首版以发布订阅完整消息为主，同时保留协议绑定和后续服务能力的扩展边界。
- 工程师通过固定格式 JSON 定义消息，通过可视化界面配置 App、输出、输入及连接，生成 IDL 和业务接口。
- 界面中“选择输入信号”实际指**订阅一条完整消息**，不是从结构体中选择几个字段进行网络订阅。
- JSON 格式由本仓库统一定义，使用者遵从该格式；不能随意导入任意 C/C++ 头文件并假设能自动解析。

当前公开接口是 `amw::cm`、`amw::log`、`amw::time`。**没有声明 `ara::com` / `ara::log` 源码兼容或完整 AUTOSAR AP 符合性。** “对标 AP”是演进目标，不是已经通过的认证结论。

2026-10-16 已完成 [CM 核心规范差距评估](docs/CM_GAP_ASSESSMENT.md)，以 R25-11 CM SWS、DDS 通信与服务发现协议正文为依据，记录 26 个条款组/评估项、源码证据、建议验收和优先级。当前主要差距在服务级生命周期/发现、订阅与取样/样本配额、标准 API/错误及 DDS 线上格式；Method/Field/Trigger 未实现。部分 DDS 条款为 DRAFT，partition 命名还存在待澄清的文本差异；Core、Manifest、语言绑定及全部条款尚未审计。推荐先确定目标接口与适用范围，保留 GUI/JSON/单 src-gen 交付。本次只做评估，未授权开始改造，不将评估项数量换算为符合率。

2026-10-19 补充启动网络参数：生成 App 构造函数接受可选 `amw::cm::NetworkOptions`，只覆盖 IPv4 网卡和初始发现对端，构造时复制、启动时校验；未设置继承生成值，显式空值清空。Domain、Topic、类型、路由和 QoS 保持生成契约，`amw_generated::domain_id` 暴露只读 Domain。错误地址通过 start 的 Result 返回；无热更新。通用手册和固定发布示例已同步。

该能力已在外部应用接入中完成 Linux/Windows 构建、本机 DDS 收发和 ARM64 交叉编译验证；外部业务适配、发布脚本和验证产物不作为公共中间件源码提交。部署副本的共享库去重与符号剥离已验证，原始 src-gen 保持完整。实际目标板到 Windows 的以太网联调仍待执行，不能把交叉编译、打包或回环测试当作上板验证；详细范围见 [验证记录](docs/VALIDATION.md)。

## 2. 当前已经做到了什么

| 部分 | 当前实现 |
|---|---|
| 类型与契约 | JSON Schema + 语义校验；类型、服务接口、Event、App、部署实例分层；支持固定宽度基本类型、枚举、受限字符串/序列、定长数组等。 |
| 代码生成与打包 | 生成完整 src-gen：generated/ 业务 DTO/App/官方 DDS 代码，runtime/ 公共模块源码，dependencies/ 三平台 SDK，以及根目录 <工程ID>.amw.json、CMake、配置、metadata、手册和全包摘要清单。 |
| CM | 类型化发布、订阅回调、样本所有权、有界队列、溢出策略、启停与回滚、错误和统计。 |
| DDS 绑定 | Fast DDS 3.6.2.0 + Fast CDR 2.3.6；官方 Fast DDS-Gen 4.3.0。默认 UDP，可配置普通共享内存传输；Data-sharing 默认关闭，可通过 QoS 表单配置。 |
| GUI | 本地配置页面；结构化新建/编辑结构体和枚举、嵌套字段/数组/有界列表，或导入类型/工程；配置 App/输入/输出（默认单输出组、自动输入命名、按需分组与编辑订阅）、校验/生成 src-gen/保存、撤销重做；工程状态和逻辑数据流图；固定高度类型库、侧边类型/引用详情、应用/流图视图切换与按需展开的结果/部署。 |
| QoS | 标准/扩展参数目录、默认值、结构化表单、模板/实例/端点覆盖、公共校验；生成私有 qos.hpp 与完整有效快照。支持范围和明确未接入项见 docs/QOS.md。 |
| 日志 | 终端分级日志，XML 启动配置，全局等级和模块覆盖，有界异步输出与统计，CM 关键诊断接入。 |
| 时间工具 | 带日期/时区的时间戳、Unix/单调时钟和 Stopwatch 耗时测量，可独立于 DDS 使用。 |
| 开发者交付 | 通用手册和固定示例原样附带到生成包的 `guide/`，从 src-gen 根目录的 README 进入。 |

尚未实现：vsomeip、Method/RPC、Field、完整动态服务发现/选源、单服务独立 offer/stop、SM/EM/健康监督、ARXML、配置热加载。没有零拷贝或硬实时保证。具体状态以 [验证记录](docs/VALIDATION.md) 和当前代码为准。

## 3. 仓库与依赖的关系

```text
fastdds-build-kit
  ├─ 目标平台 SDK：头文件、库、CMake 配置
  └─ 开发机 Gen / Java 工具
            ↓ 通过本地路径引用
adaptive-middleware
  ├─ JSON / GUI / 校验 / 生成器
  ├─ 共用 CM 运行库与 Fast DDS 绑定
  └─ 共用日志与时间基础库
            ↓ 一个完整 src-gen（生成接口 + 公共源码 + 三平台 SDK + 手册）
业务工程
  └─ 手写业务代码，调用生成的 App 接口
```

`fastdds-build-kit` 是独立的第三方依赖构建仓库。不复制其源码或顺带升级依赖。0.2 打包时将已安装 SDK 产物收集到忽略的 out/ 交付目录，随包提供许可。三平台 SDK（delivery_sdks）和生成器路径通过忽略的 `config.local.json` 配置，模板是 [config.example.json](config.example.json)。

首批平台为 Linux x64 / GNU 11.x、ARM64 Linux / GNU 9.x、Windows x64 / MSVC 19.x Release /MD。平台声明来自维护者选择的 SDK；编译器主版本匹配还不能替代 ABI/sysroot 验证。

ARM 交付包自带 toolchains/aarch64-linux.cmake，工具链根目录由应用构建时的 AMW_TOOLCHAIN_ROOT 配置，可选 AMW_COMPILER_PREFIX 和 AMW_SYSROOT；不要把 特定板卡名称或某位工程师的绝对路径写成团队默认。Windows、Linux 主机和 ARM 各自使用匹配的库、ABI 和构建目录。Gen 运行在开发机，生成的 C++ 再由目标平台编译器编译。

日志/时间可以通过 `AMW_BUILD_CM=OFF` 独立构建，不需要 DDS 或 Gen。XML 解析器是本仓库私有的 TinyXML-2 副本，来源及许可在 [third_party/tinyxml2/README.md](third_party/tinyxml2/README.md)，命名空间已隔离为 `amw_log_xml`。

## 4. 阅读代码的入口

| 要修改什么 | 先看哪里 |
|---|---|
| 业务输入模型、引用和语义校验 | [model.py](tools/amw_tool/model.py)、[schemas/](schemas)、[JSON_FORMAT.md](docs/JSON_FORMAT.md) |
| IDL/DTO/App/随包手册生成 | [generate.py](tools/amw_tool/generate.py)；`GUIDE_FILES` 列明随包手册文件。 |
| 完整交付组装/平台 SDK/构建模板 | [package.py](tools/amw_tool/package.py)、[tools/package/](tools/package)、[AmwRuntime.cmake](cmake/AmwRuntime.cmake) |
| CLI 命令与本机配置 | [cli.py](tools/amw_tool/cli.py)、[CLI.md](docs/CLI.md) |
| QoS 默认值、字段、校验和 C++ 映射 | [qos.py](tools/amw_tool/qos.py)、[QoS 指南](docs/QOS.md)、[schema 同步工具](tools/update_qos_schema.py)、[qos.js](ui/qos.js) |
| GUI 模型编辑与渲染 | [ui/index.html](ui/index.html)、[ui/types.js](ui/types.js)、[ui/type-picker.js](ui/type-picker.js)、[ui/workspace.js](ui/workspace.js)、[ui/paths.js](ui/paths.js)，本地服务在 [server.py](tools/amw_tool/server.py)。 |
| CM 公共接口和线程/队列 | [cm.hpp](include/amw/cm/cm.hpp)、[cm.cpp](src/cm.cpp)、[RUNTIME.md](docs/RUNTIME.md) |
| DDS 实体、类型注册和传输 | [fastdds_binding.hpp](include/amw/cm/fastdds_binding.hpp)、[fastdds_binding.cpp](src/fastdds_binding.cpp) |
| 日志 API/配置/异步输出 | [log.hpp](include/amw/log/log.hpp)、[log.cpp](src/log.cpp)、[LOGGING.md](docs/app-guide/LOGGING.md) |
| 时间与计时 | [time.hpp](include/amw/time/time.hpp)、[time.cpp](src/time.cpp) |
| 构建、安装与导出 targets | [CMakeLists.txt](CMakeLists.txt)、[cmake/](cmake)、[BUILD.md](docs/BUILD.md) |
| 演示契约和业务接入 | [examples/demo/](examples/demo)、[docs/app-guide/](docs/app-guide) |
| 图片内容 | [架构图](docs/ARCHITECTURE.md)、[DOT 源文件及维护说明](docs/diagrams/README.md) |

## 5. 不能丢失的设计与行为约定

### 5.1 契约与接口分层

类型回答“消息有什么字段”；服务接口组织一组 Event；App 定义提供/需要的服务端口；部署实例确定具体来源和策略。不要把 App ID、App 实例 ID、服务实例名混为一个概念。

业务消息是普通 C++ DTO，DDS wire 类型是后端细节，二者当前有转换和复制。CM 与绑定运行库共用，不为每个 App 再生成一份线程实现。`NetworkBinding` / `Writer` / `Reader` 是协议实现边界。

一个业务构建目前只接一套生成契约：target 为 `amw_project`，命名空间为 `amw_generated`。需要多个服务时先在配置工程中合并，不把两个独立生成包同时加入同一构建。交付一个完整 src-gen 根目录；应用 add_subdirectory(src-gen) 并链接 amw::app（保留 amw_project），无需另安装中间件/DDS SDK。amw_deploy 提供共享库和默认日志配置的构建/安装部署；已部署 XML 不覆盖。

### 5.2 CM 生命周期

- 先构造 App、注册全部输入回调，再 `runtime.start()`；第一次 start 即冻结端点配置，包括启动失败的情况。
- `try_publish()` 成功只表示本地入队，不表示 DDS 写入成功、远端收到或业务处理完成。
- 一个 Runtime 对应自己的 Participant；同 Runtime 的端点共用它。每个通信端点目前有自己的工作线程，不同订阅可能并发回调。
- 回调拿到 `shared_ptr<const T>`；需延后处理时保留所有权。回调依赖的业务资源必须覆盖回调和 App 停止期间的生命周期。
- CM `stop()` 会丢弃尚未处理的队列，等待正在执行的操作结束，**不是 flush**。
- 回调中需要停止时调用 `request_stop()`，由外部控制线程完成 stop；不能在自己的回调中销毁 App。
- 网络、路由和通信策略编译进生成代码；修改源 JSON 后必须重新生成、编译。旁边的 JSON 快照不是运行时热配置。
- DDS 匹配数不是服务健康；普通共享内存传输不等于 Data-sharing 或零拷贝。Data-sharing 虽可配置，但尚无本项目实际路径验证。

完整语义、错误码和指标以 [接口手册](docs/app-guide/API.md) 为准。

### 5.2.1 QoS 默认值与生成配置

用户已确认同时覆盖 DDS 标准与 Fast DDS 扩展的可视化配置；所有开放参数必须有默认值，仅按需修改。当前参数目录 `fastdds-3.6.2/amw-qos-1` 包含 82 个描述条目，部分适用于多个实体。它不代表 82 种独立 QoS，也不代表所有 Fast DDS API 成员都已开放。

`policy.dds` 按 topic/writer/reader 保存覆盖；部署与实例的 `qos` 按 participant/publisher/subscriber 保存覆盖。旧七字段和空策略均可读取。先解析 AMW 默认、旧字段、Topic 同名值、端点覆盖；实例分组则按项目与实例覆盖。未填字段不回写源配置。应用开发者仍只接入 src-gen，不需要自己设置 DDS 实体。

表单“应用”检查字段/局部一致性，完整校验与生成检查连线两端 requested/offered、资源、分区和引用。生成私有 `generated/qos.hpp`，输出 `metadata/qos.effective.json`，清单记录默认值版本。DDS 对象只进入 Fast DDS 绑定；公共 CM/DTO 保持独立。默认流量控制器使用 SDK 常量映射，不能猜测内部字符串。

官方尚未实现的 7 类标准 QoS，以及需要额外 CM/部署能力的手动活性、持久化服务、安全、部分发现/传输等选项在界面标注不可用；详细矩阵以 docs/QOS.md 为准，不把“全量配置方向”当作全部成员已实现。不会静默接受未知覆盖。修改字段目录后运行 schema 同步和检查，修改生成映射应实际编译验证。

### 5.3 日志与时间：用户已确认的范围

用户明确选择：**只打印终端；XML 修改后重启生效；提供接口指定 XML 路径。** 不应擅自扩展文件日志、滚动、热重载或 DDS 日志上传。

应用调用 `amw::log::initialize(Options{app_name, config_path})`，XML 路径按初始化时的当前工作目录解析，并在结果中报告绝对路径。初始化失败返回具体原因，不静默换用默认配置；CM 不替应用寻找 XML 或初始化日志。

等级为 TRACE/DEBUG/INFO/WARN/ERROR/FATAL/OFF。全局等级加最长点分模块前缀覆盖。全部等级写 stderr；宏在启用时才求值正文，记录时间在调用处采集。队列满时丢新记录并计数，FATAL 也不自动终止或绕过队列。

日志 `shutdown()` 会排空已接纳记录，这与 CM stop 丢弃待处理样本的语义不同。正常顺序是先初始化日志，再启动业务/CM；退出先停止业务/CM，最后关闭日志。终端永久阻塞时日志 shutdown 可能等待，不承诺异常退出不丢缓存或硬实时。

计时使用单调时钟，日志关联时间使用系统日历时间；不把日志时间自动当成传感器采集时间，不声称实现了跨设备时钟同步。多个 DLL 若各自静态链接日志库会有独立状态，需要共享状态时应共用动态库或宿主接口。

### 5.4 生成保护与通用手册

每次生成在 src-gen 根目录写入 `<工程ID>.amw.json`，与 metadata/model.resolved.json 共用同一次序列化结果；可直接通过“打开工程”恢复本次生成的完整配置。它与其余产物一起参与摘要、保护及原子替换，旧的完整受控包正常再生成即可补齐。不要手改随包工程文件；先在界面编辑或复制到包外。它不包含本机工具路径和浏览器偏好，也不自动跟随生成后的编辑更新。通用 guide/ 文件清单未变。

生成器通过锁、暂存目录、摘要清单和替换/回滚保护产物；遇到未知文件或手改文件应拒绝覆盖。不要删 manifest、手修 wire 源码或强制清空目录来绕过保护。业务代码、构建缓存和项目专用笔记放在生成目录之外。

已修复 Fast DDS-Gen 的跨工程临时文件竞争：每次生成必须保留独立 `-t` 临时目录，结束后清理。同名 messages.idl 在并行生成时不能共用预处理文件。

**通用应用手册不按工程或 App 改写。** 源文件在 `docs/app-guide/`，生成时原样复制到 `guide/` 并计入摘要。只有中间件模块、接口、行为或接入方式变化才统一修订。普通消息字段/App 名变化不需要改这份手册，也不要恢复早期讨论过、后来被用户否定的“每次生成专用 App 手册”方案。固定示例仅演示 demo 契约。

### 5.5 GUI 编辑约定

错误回滚会替换模型对象。弹窗重试不能继续使用旧 App 对象引用，必须凭 App ID 从当前模型重新查找；否则可能出现“连接增加了，但 App 输入没增加”。输入和输出弹窗都要守住这个约定。

GUI 用“输入/输出分组”解释逻辑服务端口。新 App 首次输出自动建立 output；已有单组沿用原名，多组时必须明确选择，卡片内“添加消息”可指定分组。输入分组按来源自动命名并避开本 App 输入/输出重名；高级设置允许改名。“编辑订阅”更新已有输入的消息集合，保留每个部署实例原来的来源；改名迁移绑定和保留消息的 QoS 覆盖，取消订阅/移除连接清理相关覆盖。JSON 格式和生成命名规则保持原样，旧工程不会因打开页面而改名。新增输入仍默认绑定来源 App 的首个实例，多实例选源需检查部署。输出类型使用搜索框与结果列表，默认不选中；按类型名、说明或递归字段名检索，显示嵌套字段路径，点击结果后可逐级预览结构。完整名称和版本用于消歧；修改搜索词清除旧选择，未选中时禁用应用。类型检索/预览只读，不更改契约和生成命名规则；键盘操作与循环引用草稿保护在 ui/type-picker.js。新增静态资源路由后，已运行的旧 GUI 服务需保存草稿再重启。

工作台已整理为固定高度类型库与主工作区。列表独立滚动，按实际 App 输出引用分组并提供筛选；侧边详情面板显示字段、直接类型依赖/引用、直接或嵌套使用它的 App 输出。主工作区切换应用配置/数据流图；顶部工程栏常驻显示新建/打开/导出，与工程名称和保存状态放在一起；主工具栏保留保存/校验/生成，完整模型编辑放在独立“高级工具”入口，打开工程接收 .amw.json 工程包；部署概览及详细结果按需展开。视图和筛选状态不写入模型或撤销历史。库详情与输出选择共用 createTypeInspector 做只读嵌套结构遍历，防止循环引用草稿卡死。页面等待 DOMContentLoaded 后载入模型，确保工作台脚本已就绪；隐藏数据流图在切换显示时重新适应宽度。实现入口为 ui/workspace.js 和 ui/index.html。

工程保存状态来自当前模型与成功保存快照的比较，不是只判断修改次数。保存失败或保存过程中继续编辑时，不能错误地显示“已保存”。数据流图表示逻辑 App/端口连接，不是实时 DDS 拓扑或部署监控。

## 6. 新对话开始时怎样检查环境

先在仓库根目录进行只读检查：

```bash
pwd
git status --short
git log -5 --oneline
./amw --help
```

检查 `config.local.json` 是否存在及路径是否适用于当前机器；首次配置见 [GETTING_STARTED.md](docs/GETTING_STARTED.md)，不要覆盖已有个人配置。然后按实际任务需要使用 `./amw doctor` 和 `./amw validate`。没有个人配置不妨碍阅读代码或独立构建日志。

CLI 默认工程是 `examples/demo/project.cm.json`。CLI/GUI 默认交付目录均按模型 project_id 使用 `out/delivery/<工程ID>/src-gen`，demo 为 `out/delivery/demo/src-gen`。GUI 草稿为 `out/editor/<工程ID>`。GUI 在生成前显示完整目标路径，生成位置设置允许自定义绝对根目录，仍在其下追加 `<工程ID>/src-gen`；偏好保存在当前浏览器站点且不进入工程包，CLI 显式 --output 仍直接指定目标目录。旧目录不自动删除或迁移，改 ID 后使用新目录；同 ID 不隔离。旧 out/generated 不自动迁移，不要把新输出嵌入旧受控目录。继续自己的草稿时用：

```bash
# 以工程 ID 为 vehicle_demo 的草稿为例
./amw gui --project out/editor/vehicle_demo/project.cm.json
```

这要求该草稿实际存在且有效；不带 `--project` 会加载 demo。刷新页面前先保存或导出未保存内容。不要把自动化测试直接指向用户正在编辑的草稿。

本项目不要求所有工程师使用相同绝对路径。路径和实际运行状态应现场核实；本机历史位置见第 9 节，仅用于恢复旧证据。

当前仓库的业务目录已移除，浏览器测试仅依赖通用模拟类型库；源码及正式测试的改动应继续显示在 Git 状态中。本机文件和临时产物的目录约定以 `.gitignore` 与 [团队协作说明](docs/CONTRIBUTING.md) 为准。

## 7. 怎样选择验证，不要把所有检查混成一项

**匹配查询死锁修复（2026-10-20）：** ARM64 板端复现接收一段时间后停住，调用栈确认：`Endpoint::matches()` 持有 CM 队列锁等待 DDS Reader 锁，而 DDS 接收回调持 Reader 锁等待 CM 入队，形成反向加锁。已改为锁内复制 Reader/Writer 共享引用、锁外调用绑定，保留与 stop 并发时的对象生命周期。新增 `cm_matches` 测试确定性复现旧实现失败，并覆盖 Reader/Writer 查询与 stop 并发；native CTest 5/5 和通用手册固定示例编译通过。临时 ARM 订阅程序在板端连续运行 180 秒，接收 3599 条，正常定时停止；正式业务程序与已有 src-gen 尚未替换，详见 VALIDATION.md。修复位于公共 `src/cm.cpp`，已有生成包不会自动更新，须重新生成和编译相关应用；不能仅更新 DDS 动态库。外部业务项目的正式交付与临时调试版本要分别记录。

**普通 SHM 补充验证（2026-10-20）：** 外部应用接入验证在隔离 Linux x64 网络与共享内存环境中，使用一个开启 SHM 的发布进程，同时连接同机 SHM 订阅进程及仅支持 UDP 的订阅进程；120 帧分别接收 120 帧。测试专用拦截器屏蔽 UDP 用户 DATA/DATA_FRAG、保留发现后，SHM 订阅仍收到 120 帧，UDP 订阅收到 0 帧，确认此环境下实际 SHM 路径。未修改公共运行库，Data-sharing 仍关闭；没有实际板端、跨主机或性能验证。业务项目与验证脚本仍位于公共仓库之外或忽略的 out/ 中，不能当作 clone 后自带的正式测试入口。详见 VALIDATION.md。

下列命令在仓库根目录执行。按修改范围选择，不能仅因新开对话就无差别运行所有测试。

| 修改范围 | 对应验证 |
|---|---|
| 模型、校验、生成逻辑、随包内容 | `python3 -m unittest discover -s tests -p 'test_*.py'`；包含真实 Gen 用例，需要可用的本机配置。 |
| CM、绑定或生成 C++ | `./amw build --demo`，再 `ctest --test-dir out/build/native --output-on-failure`；自定义类型还需实际生成/编译。 |
| 实际 DDS 收发 | `python3 tests/integration.py out/build/native`；单独验证网络，建议隔离网络运行，具体见验证文档。 |
| GUI | `tests/browser.py`、`tests/browser_flow.py`、`tests/browser_types.py`、`tests/browser_qos.py`、`tests/browser_groups.py`、`tests/browser_type_search.py`、`tests/browser_workspace.py`、`tests/browser_paths.py`；需要 Playwright/Chromium，串行且在独立副本运行，避免改用户草稿。 |
| 独立日志/时间 | 下面的日志构建与 CTest。背压用例需 CMake 找到 Python3 才注册。 |
| 文档与图片 | 核对链接、参数、实际接口和差异；新完整 CMake/C++ 示例应编译；图片改 DOT 后重新生成并查看。 |

独立日志构建无需 DDS：

```bash
cmake -S . -B out/build/log-only \
  -DAMW_BUILD_CM=OFF -DAMW_BUILD_LOG_EXAMPLE=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build out/build/log-only --parallel 4
ctest --test-dir out/build/log-only --output-on-failure
./out/build/log-only/amw_log_example \
  --log-config "$PWD/docs/app-guide/examples/logging.xml"
```

**团队仓库整理验证（2026-10-16）：** 完善 .gitignore、Linux 部署及 CONTRIBUTING 文档，业务目录引用和个人路径已清理。当前公共文件构成的隔离副本通过忽略/可见性检查、doctor、demo/QoS/schema 检查、Python 42 项及通用样本的类型搜索/工作台两组浏览器流程；测试后无公共文件修改和未忽略产物。没有需要退出跟踪的本机文件，没有修改原仓库索引或 commit/push。临时副本已清理，日志 /tmp/amw-repository-review-logs/；没有重新安装操作系统或重跑跨平台构建。

**随包工程文件验证（2026-10-15）：** Python 42 项与 Linux Chromium browser_paths 流程通过；根目录 .amw.json 与生成快照一致、可重新打开、受摘要保护，旧受控包再生成可补齐。浏览器验证使用 /tmp 临时副本并已清理，日志 /tmp/amw-project-bundle-{python,browser}.log；用户已有交付包未改写，下一次正常生成生效。未重跑 C++ 或跨平台通信。

**按工程路径验证（2026-10-15）：** 路径规则集中在 tools/amw_tool/paths.py，CLI 默认输出与 GUI 复用；GUI 自定义生成根目录偏好独立于业务模型。八组 Linux Chromium 流程通过，包括新增多工程草稿隔离、路径设置/刷新/恢复、生成时切换工程后仍写提交目录。完整 Python 41 项通过，包含原生成保护回归。测试入口 tests/browser_paths.py（18772）与 tests/test_paths.py，日志在 out/verification/workspace-browser*.py.log 和 project-paths-python.log。未重跑 C++ 或跨平台测试。

**GUI 工程栏验证（2026-10-15）：** 新建/打开/导出改为常驻按钮，完整模型编辑移到高级工具。工作台、类型检索、流图、原生成主流程和结构化类型编辑五组回归通过；另检查导出/打开完整往返、高级工具取消与 Escape 焦点、375 像素布局。证据在 out/verification/workspace-*，未重跑运行库或跨平台测试。

**GUI 工作台验证（2026-10-15）：** 七组 Linux Chromium 流程通过，包括 203 类型的固定高度列表、独立滚动、筛选/侧边详情/引用与实际 App 使用关系、只读操作不污染历史、视图切换、异步保存/校验状态、错误摘要、窄窗口，以及既有真实生成/保存和 QoS 回归。截图在 out/verification/workspace-gui-repo/out/browser-workspace/，日志在 out/verification/workspace-browser*.py.log。JS 语法、文档链接和差异检查通过；未重跑 C++ 或跨平台通信测试。

**GUI 输出类型检索验证（2026-10-14）：** 六组 Linux Chromium 流程通过，新增当时使用的 22 类型业务样本搜索、嵌套字段路径、结构预览、显式选择/清除、键盘与版本消歧；原分组/类型编辑/图形连接/QoS/真实生成与保存流程全部通过。证据仍在 out/verification/groups-*，截图在隔离副本 out/browser-type-search/。本次未重跑 C++ 或跨平台运行测试。

**GUI 默认分组验证（2026-10-14）：** 五组 Linux Chromium 流程通过，包含默认/多组输出、自动输入命名、编辑订阅、保留多实例不同来源、迁移和清理 QoS 覆盖、错误重试/撤销重做、真实 Gen 三平台包生成与保存。关键模型通过 Python 公共校验；证据在 out/verification/groups-*。本次没有重跑 C++、Windows/ARM 或网络收发。

**QoS 本次验证（2026-10-14）：** 完整 Python 38 项、Linux 默认/自定义交付构建与 4 项 CTest、16 项 QoS 单元用例（包含在 38 项内）、4 组浏览器流程通过。Linux 隔离网络收发和晚加入者历史深度行为通过；Windows MSVC Release 独立包构建、历史深度/失败清理/重启行为通过；ARM64 GCC 9.2 交叉编译通过，未上板。非默认代码生成分支另有 Linux SDK 语法编译探针。证据位于 out/verification/qos-*，详细范围见 VALIDATION.md。

**0.2 单目录交付历史验证（2026-10-13）：** Linux 独立交付包生成/移位构建/安装/日志运行、仓库完整构建和 4 项 CTest；Windows MSVC 独立包构建/安装/日志和实际本机 DDS 收发；ARM64 GCC 9.2 交叉构建/安装（未上板）。GUI 原流程/数据流图，以及结构化类型编辑→两个 App→生成三平台包通过；GUI 创建的自定义契约实际编译通过。完整明细及最终测试计数见 VALIDATION.md。

**0.1 历史证据（不冒充本次重跑）：**

| 范围 | 已有结果与限制 |
|---|---|
| 最近日志/生成更新 | 16 项 Python 测试；Linux 完整构建与 4 项 CTest；日志 ASan/UBSan/LSan 检查通过。未做 ThreadSanitizer。 |
| Windows | 最近完整 CM 与静态日志构建/测试通过；独立日志/时间 DLL/.lib 构建、测试和示例运行通过。使用宿主生成的 C++，不等于 Windows 原生 Python/Java/浏览器全链路已验证。 |
| ARM | CM 基线及后来日志/时间使用 GCC 9.2 交叉编译通过；未在板端运行。 |
| DDS 网络 | 较早基线做过 Linux 隔离 UDP 与 Windows 实际收发；最近日志更新没有重跑真实网络通信。 |
| GUI | 较早完成 Linux Chromium 的编辑/生成、错误重试、工程状态与图形连接自动化验证；日志更新没有重跑浏览器。 |
| 尚缺的环境证据 | 本仓库中间件的跨设备/板端部署、实际 SHM 路径、长期负载/容量和硬实时等不能据编译结果宣称完成。 |

详细时间和范围在 [VALIDATION.md](docs/VALIDATION.md)。其他业务项目在板端运行过某版 Fast DDS，不代表这套新中间件也已经通过板端验证。

### 通用回归数据

类型搜索和工作台浏览器测试统一读取 `tests/fixtures/sample-types.cmtypes.json`，这是独立编写的 22 个结构体的模拟数据，不依赖业务头文件。样本和正式测试必须一起提交；业务配置不作为产品内置协议。原业务目录和业务样本已移出仓库，公共说明不再引用它们。

## 8. 后续方向与未决项

当前已完成单目录交付：用户确认只交付完整 src-gen，首批覆盖 native Linux、Windows 上位机及 ARM64 Linux，嵌入式工具链路径可配置。公共 API/通信语义保持原基线，三平台依赖打包不等于板端验证。新对话从用户的新任务开始，不自动推进下列路线图。

用户此前提出的第二阶段之一是：把 **vsomeip** 加到公共 CM 之下，与 DDS 作为并列 Network Binding，并由配置界面选择协议。目前仍未实现，只有 [ROADMAP.md](docs/ROADMAP.md) 中的方向；不要因读到这里就开始迁移。

正式开展该阶段前，需要明确：

- 绑定选择按整个部署还是按服务；是否允许同一进程同时使用两种绑定。
- 服务/实例/Event 到 SOME/IP 标识的映射、编号和冲突规则。
- 两种协议的编码、发现、可靠性、订阅恢复与状态语义如何暴露。
- JSON、模型校验、生成器、运行库、GUI、依赖与测试怎样同步扩展。

后续还可能涉及 SM、EM、健康监督、Method/Field、线程资源模型和板端容量优化。以上是规划，不是首版承诺，也不是下一轮已经确认的工作清单。接口或范围有变化时，先说明设计影响，再按当前用户授权推进。

## 9. 仓库与个人工作区

团队提交中间件源码、GUI、工具、schema、通用示例、正式测试及模拟数据、文档和配置模板。`local/` 放个人业务配置与实验，`out/` 放草稿、生成包、构建结果和验证记录；本机配置为被忽略的 config.local.json 或 config.*.local.json。SDK/Gen 是外部依赖，由各工程师配置路径。新环境步骤见 docs/GETTING_STARTED.md，提交约定见 docs/CONTRIBUTING.md。

.gitignore 随 clone 生效，但不会隐藏已跟踪源码的修改，也不代替业务配置的备份。没有安装个人 Git hooks，不修改全局 Git 配置。历史机器路径不是构建依赖；验证结论保留在 VALIDATION.md，已清理的日志不能视为仍在仓库中。

公开仓库从当前完整功能快照建立单条初始提交，旧开发历史与个人引用仅保存在仓库外的本地备份中。本文的历史验证日期描述功能来源，不表示这些旧提交存在于公开历史。新会话仍应检查实际 Git 状态，不假设本地分支已经推送。

## 10. 给新对话的开场提示词

可以复制下面这段，并把最后一行替换成具体任务：

```text
请先读取当前仓库的 AGENTS.md 和 DEVELOPMENT_CONTEXT.md，再按需阅读相关设计及使用文档。
检查当前分支、工作区和本机配置，区分已有实现、规划目标与实际验证范围。
保留生成目录保护、公共 CM/绑定边界，以及通用手册不按 App 改写的约定。
本次任务完成后，请更新相关使用文档、验证记录和开发交接信息。
本次我要继续做的是：……
```

## 11. 后续怎样维护这份交接

它是面向下一位开发者的现状说明，不是逐条聊天记录。重要功能完成后，更新整理日期、功能基线、当前能力、关键约定、验证摘要和未决项；同时更新对应使用文档及 VALIDATION。清除已经过时的“尚未实现”，但保留能解释设计取舍的必要背景。

不要在这里记录密钥、账号、用户本机工具链作为团队默认，或把未经测试的结果写成已验证。开发任务尚未完成而需要交接时，应明确写出已改哪些文件、失败在哪、下一步是什么，避免下一对话重复工作或误认为已经交付。

## 12. 当前公开源码整理状态（2026-10-22）

公开文档采用通用平台名称和路径；实际配置与原始证据留在忽略的 config.local.json、local/ 和 out/。本次只改文档，doctor/validate、已知内部标识扫描、忽略边界及 diff 检查通过；已有业务工程、生成包和本机配置不变。已以当前快照建立新的公开 main，原 Git 数据完整备份到仓库外；新仓库不包含旧历史、个人引用或旧远程地址，尚未推送。提交审查方法见 CONTRIBUTING；不要把旧历史重新合入公开仓库。
