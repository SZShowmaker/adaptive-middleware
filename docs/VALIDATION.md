# 验证记录（0.1 / 0.2）

> 2026-10-15 清理说明：按用户要求已清空仓库 out/，历史草稿、生成包、构建缓存及验证日志/截图均已删除。本文中的历史验证结论保留，但指向 out/ 的历史证据路径已不可用；需要时重新运行相应检查生成。

普通 SHM 与 UDP 双订阅补充验证：2026-10-20；最新工作台布局验证：2026-10-15；类型检索、分组与 QoS 验证为 2026-10-14，见文末相应记录；单目录交付验证为 2026-10-13；下面先保留 0.1 历史记录（交付检查 2026-10-08，初次验证始于 2026-09-30）。本文回答“哪些环境和行为实际检查过”。正常使用流程从 [入门指南](GETTING_STARTED.md) 开始；下面的测试命令主要供维护者复现。

“交叉编译通过”仅表示在开发机成功生成目标平台二进制，不表示已经在板端运行；“生成通过”也不等于程序实际通信成功。表中分别记录这些结果。

| 项目 | 结果与范围 |
|---|---|
| Python 模型/生成器 | 13 项通过；包括非法字段/引用/边界、递归、QoS 不匹配、生成名称冲突、重复 JSON 键、实例隔离，以及真实 Gen 重复生成一致、失败保留旧产物、锁冲突和手改产物保护。 |
| Linux C++17 构建 | Debug CM、Fast DDS 绑定、生成接口、发布者/订阅者均通过。 |
| C++ 运行库 | CTest 通过；覆盖溢出替换、发送错误、重复启停、启动回滚、必需回调缺失、空后端端点、回调内停止和启动时立即回调请求停止。最后一项循环 30 次。 |
| Linux 实际 UDP 通信 | 隔离网络内发布 380 次，两种消息。早退出订阅者各收到 125 条，持续订阅者各收到 323 条；全部内容校验有效。另一服务实例收到 0 条。样例为 BEST_EFFORT，数量包含发现/退出时间差，不能解释为可靠性或吞吐测量。 |
| Windows C++ 与通信 | VS 2022/MSVC，Release 静态 CM、外部 DDS DLL，构建与 CTest 通过。发布 250 次，两类消息各收到 239 条，内容校验有效。 |
| AArch64 交叉编译 | GCC 9.2，Release，CM/绑定/生成接口/两个应用均通过。该项未在目标板执行。 |
| 独立消费安装 SDK | CMake install 后，外部应用通过 find_package(amw) 与生成目录构建成功。 |
| 浏览器 | Linux Chromium 自动化通过：加载、搜索、导入、增加输出、撤销、校验、生成、保存；另从空工程新增两个 App、输出和完整消息订阅，再次校验/生成。无脚本错误。 |
| 类型映射 | 另编译覆盖 bool、固定宽度整数、浮点、枚举、受限 string/sequence、定长及多维数组的生成契约。 |

Windows 验证使用宿主已生成的 C++，尚未完成 Windows 原生 Python/Java 全流程及浏览器操作验证。共享内存配置与实现已具备，但本次未验证实际 SHM 数据路径或测量其性能。未执行跨主机以太网、板端、长期压力或线程消毒器测试。

## 复现

配置 config.local.json 后：

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
./amw build --demo
ctest --test-dir out/build/native --output-on-failure
python3 tests/integration.py out/build/native
```

网络集成测试使用示例 Domain 37，请在没有其他同契约进程的环境运行。Linux 可在隔离网络内执行（系统需允许 user/net namespace）：

```bash
unshare -Urn sh -c 'ip link set lo up && python3 tests/integration.py out/build/native'
```

可选浏览器验收需要 Python Playwright 与 Chromium，不属于产品运行依赖：

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
python3 tests/browser.py
```

该测试启动本地 18765 端口服务，会更新 out/editor、out/generated/editor，并将截图写入 out/browser-test。Windows 和 ARM 构建操作见 [构建指南](BUILD.md)。

## 首版支持边界

已实现主流程是固定 JSON → 可视化 App/完整消息连接 → 校验 → IDL/官方 Gen/强类型 API → 编译 → 发布订阅。服务接口、实例、Event 分层；队列、数据所有权、错误和统计由公共运行库管理。正式输入以 JSON_FORMAT.md、schemas 和 examples 为准。

本版本采用整个 App 端点集合的 start/stop 与静态选源。端点匹配数不是完整服务发现或服务健康协议。部署被编译进生成接口，变更须重新生成/构建。一个应用构建只链接一个生成契约包（amw_project/amw_generated）；多个契约应先合并成一个工程，尚不支持独立生成包并列链接。

当前不实现单服务独立 offer/stop、Method/Field、动态选源、运行时热配置、ARXML 或 ara::com 源码兼容。vsomeip、SM/EM 按 ROADMAP 后续推进；终端日志与时间工具的新增范围见下方 2026-10-10 记录。DTO 与 wire 转换涉及复制，每端点一个线程；零拷贝、硬实时和大规模资源预算均未承诺。

REQUIREMENTS.md 保留产品演进目标与验收建议；这些后续目标不能据首版编译成功视为全部完成。后续引入业务前，应根据实际消息大小、频率、端点数量和板端资源完成容量与故障测试。


## 2026-10-08：面向工程师的文档流程核验

重整 README 与文档导航，补充首次生成、CLI、跨平台构建、独立业务接入、排错和团队保存/交付流程。类型编写指南中的示例已在前一次文档修改中通过校验、生成与编译。

本次在独立 checkout 中按新说明执行了以下检查：

- 核对五个 CLI 子命令的 --help 与文档参数；执行 doctor、validate、generate。
- 构建 demo，运行 CTest，并将中间件安装到指定 SDK 目录。
- 使用 INTEGRATION.md 中完整 CMakeLists.txt 和仓库 producer/consumer 源文件，构建独立业务工程。
- 按 GUI 指南中的准确名称建立 sensor/display 配置，保存为三个文件，复制到独立业务源目录，再执行 validate、generate 和自定义契约 Release 构建。
- 编译检查接入指南中的回调示例；检查 Markdown 本地文件链接及格式差异。

以上验证了本次新增的 Linux 命令和示例。此次没有重新执行浏览器点击、Windows 原生生成、ARM 上板或网络收发测试，不扩大前文的已验证范围。Windows/ARM 命令与现有脚本和工具链参数做了核对。

## 2026-10-09：GUI 重名报错后重试

修复“选择输入”弹窗在端口重名报错后，改名重试只增加连接、没有增加 App 输入的问题。原因是失败回滚替换了模型，弹窗保留的 App 对象已经失效。现在输入与输出弹窗只保留 App ID，在每次应用时查找当前对象。

扩展 `tests/browser.py` 并用 Linux Chromium 验证：

- 从空工程建立 sensor、sensor2、display，先配置第一路订阅；选择第二路来源，在同一弹窗连续两次触发端口重名，再改名提交。旧代码在“应出现第二个输入”断言处失败，修复后通过。
- 对输出消息名执行相同的连续报错流程，随后新建输出端口；检查端口、服务接口和部署通过完整模型校验。
- 检查重试后的输入、连接、部署绑定和保存文件一致，撤销/重做能还原完整模型；错误提交不增加编辑历史，取消不清空原有重做历史。
- 移除重试创建的连接、撤销移除、保存草稿、真实 Fast DDS-Gen 生成均通过；页面无 JavaScript 错误。截图仍保存在 `out/browser-test/editor-fresh.png`。

原有浏览器主流程与 13 项 Python 模型/生成器测试同时通过。本次修改仅涉及前端编辑与验收，未重新执行 C++ 构建、Windows 浏览器、板端或通信测试。已有异常模型不会自动修复，恢复步骤见 [常见问题](TROUBLESHOOTING.md#重名报错后连接出现了但-app-中没有对应输入)。

## 2026-10-09：工程识别与数据流向图

新增固定在页面顶部的当前工程名称、保存状态和 App/连接数量，浏览器标签同步显示工程名。保存状态比较当前模型与载入/最近成功保存的快照，保存请求只确认其提交时的内容。连接文字列表改为前端 SVG 图：App 节点、输入/输出端口、有向连线、连接详情与移除操作，支持缩放及滚动。没有增加第三方前端库或联网绘图服务。

Linux Chromium 已验证：

- 新建、打开工程包、撤销/重做后工程名和浏览器标题一致；空工程与孤立 App 正常显示。
- 分支、多级、跨级、反馈回路、自订阅均可绘制；回路路径在画布范围内。点选编号或键盘选中连线可查看完整端口及消息信息，移除和撤销同步更新模型与图。
- 全宽图形布局、缩放、适应宽度、滚动时固定的工程栏，以及 680 像素窄窗口无页面横向溢出。复杂关系仍可能有交叉线，图不表示实时通信健康状态。
- 保存失败仍保留未保存标记；保存请求期间继续编辑，返回后仍保留后续编辑的未保存标记；撤销到已保存内容后标记恢复。
- 原有浏览器生成流程及重名重试回归通过，真实 Gen 生成与保存通过，无页面脚本错误；13 项 Python 模型/生成器测试通过。没有重跑 C++、Windows 浏览器、板端或通信测试。

配置好 `config.local.json`、Python 依赖和 Playwright/Chromium 后，在仓库根目录依次执行：

```bash
python3 tests/browser_flow.py
python3 tests/browser.py
```

新增图形测试使用本地 18766 端口，原有测试使用 18765。两者都会保存测试草稿到 `out/editor`，应在独立验证副本执行，且不能因端口不同就并行运行或与日常编辑器共用目录。图形测试截图位于 `out/browser-flow/`，原有流程截图仍在 `out/browser-test/`。新增测试不需要运行实际 DDS 通信；原有流程测试需要可用 Gen。

## 2026-10-10：随生成包交付通用应用开发手册

新增 `docs/app-guide/`，包含接入步骤、API 介绍、错误/线程/生命周期说明及固定 demo 发布订阅示例。生成器将同一份内容原样复制到 `guide/`，并输出生成目录和 `src-gen/` 的 README 入口；手册不按工程或 App 改写，随中间件接口和行为统一修订。全部随包文件纳入原有生成摘要保护。

独立验证副本中实际通过：

- 15 项 Python 测试，包括真实 Gen 的重复生成、失败保留旧输出、锁和手改保护。新增测试使用不同 App 名/工程名的模型验证手册逐字节相同，并检查 manifest 包含手册。
- 构造不含手册、清单合法的旧布局包，重新生成能补齐手册；手改随包 API 文档后，生成拒绝覆盖并保留文件及原清单。该旧布局用当前输出移除新增文件构造。
- 真实 Fast DDS-Gen 4.3.0 生成 demo；Linux Release 构建并安装 CM/绑定 SDK。
- 从生成包的 `guide/examples` 构建独立发布者/订阅者，使用安装后的 CM SDK 与外部 DDS SDK。
- 原样提取手册 INTEGRATION.md 的完整 CMake 代码块，以固定发布示例作为 main.cpp，构建独立 `my_app` 成功。
- 核对源手册与随包手册的本地文件链接，均不依赖包外文档；`git diff --check` 通过。

本次验证手册交付及 Linux 编译，没有重新运行网络收发、Windows/ARM 构建、板端或浏览器测试。GUI 与 CLI 使用同一个生成入口，本次未改变界面或通信运行库。固定示例仅适用于 demo 契约，不能直接用于任意自定义 App。

已有生成目录不会因仓库更新而自动改写。下一次正常生成时才附带手册；请保留原有生成保护，不要将业务笔记或构建缓存放进生成目录。

## 2026-10-10：0.1.1 终端日志与时间模块

按已确认范围实现 amw::log / amw::time：应用指定 XML 路径和进程名，初始化时读取配置；分级及点分模块覆盖、线程安全记录、有界异步队列、stderr 输出、自动日期/时区时间戳、单调计时。无文件日志、自动滚动或热更新。CM 接入启动诊断以及限频的发送失败/回调异常日志。使用方法见 [日志与时间手册](app-guide/LOGGING.md)，手册修订为 1.1，生成包原样附带。

实际验证范围：

- Linux 独立基础库和完整 CM/demo 构建通过；完整 CTest 4 项通过：原 CM 运行测试、初始化日志后的相同 CM 测试、日志/时间功能、阻塞终端和关闭管道。
- 日志功能测试覆盖非法 XML/未知项/重复节点和模块/错误等级/缺失文件/超限配置、绝对路径、模块继承与覆盖、INFO 正确解析、关闭日志不执行正文表达式、6 线程共 1800 条记录完整性、控制字符转义、超长截断、格式化异常、重复初始化/停止、停止与提交并发、修改文件不影响当前会话、新会话重置计数。
- 时间测试覆盖固定 UTC 时间和微秒格式、当前本地时区偏移、单调耗时。Linux 与 Windows 实际示例均打印了带日期和时区的时间戳。
- 背压测试故意不读取子进程 stderr，在管道堵塞时提交 10000 条日志，提交线程仍完成，溢出计数增加；恢复读取后排空。关闭管道后输出错误被计数，进程保持存活。Linux SIGPIPE 只在日志工作线程屏蔽，没有改变应用全局信号处置。
- Linux AddressSanitizer + UndefinedBehaviorSanitizer + LeakSanitizer 检查通过。首次沙箱内测试在结束时被 ptrace 环境阻止泄漏检查，授权后在沙箱外执行通过；没有将该环境失败计作通过。未执行 ThreadSanitizer。
- VS 2022/MSVC：完整 CM/生成契约/demo 与静态日志库构建通过，4 项 CTest 通过；独立共享基础库产生 amw_log.dll/.lib、amw_time.dll/.lib，2 项 CTest 和示例运行通过。Windows 复用宿主生成的代码，没有新增 Windows 原生 Java 生成验证。
- AArch64 GCC 9.2：独立日志/时间静态库和示例 Release 交叉编译通过；未在板端运行。
- 安装后独立程序直接使用手册中完整 CMake 构建成功；使用完整 SDK、显式禁用查找 fastdds/fastcdr 后，以 COMPONENTS log time 消费仍成功。完整 SDK 的生成包发布/订阅示例也编译通过。
- 16 项 Python 模型/生成器测试通过；本地文档链接与 git diff --check 通过，已查看更新后的组成图。未重跑实际 DDS 网络通信或浏览器。

集成过程中发现原有 Fast DDS-Gen 默认临时目录按 IDL 文件名保存预处理结果；两个工程同时生成 messages.idl 时可能相互覆盖。本次为每次生成传入独立 -t 目录，结束后清理，再生成摘要。新增真实 Gen 并发测试使用不同字段定义，核对两份 wire 类型互不污染；保留原失败回滚和生成保护。该修复不改变 JSON 格式或业务接口命名。

可从仓库根目录复现：

```bash
cmake -S . -B out/build/log-only -DAMW_BUILD_CM=OFF -DAMW_BUILD_LOG_EXAMPLE=ON -DCMAKE_BUILD_TYPE=Release
cmake --build out/build/log-only --parallel 4
ctest --test-dir out/build/log-only --output-on-failure
./out/build/log-only/amw_log_example --log-config "$PWD/docs/app-guide/examples/logging.xml"
```

背压测试由 CMake 在找到 Python3 时注册。完整 SDK 继续使用 ./amw build --demo 和对应 CTest。运行时不需要 Python、Java 或 XML 之外的配置服务；普通日志调用不启动 GUI 或网络连接。异步提交不等待终端，但会分配/格式化/短暂加锁；shutdown 等待排空，输出端永久阻塞时也可能等待，不承诺硬实时或异常退出不丢日志。

## 2026-10-12：开发交接文档

新增根目录 DEVELOPMENT_CONTEXT.md，整理用户已确认需求、0.1.1 功能基线、架构与依赖、代码入口、CM/日志/生成保护约定、验证边界、后续未决项和新对话提示词；AGENTS、README 与文档导航提供入口。交接中的日志状态为已实现，vsomeip/SM 等为待后续任务，不把规划自动视为授权。

本次仅修改文档。已对照当前代码、Git 历史和现有验证记录核对内容，检查本地链接、引用路径及 git diff --check；未重新编译、运行网络/浏览器或扩展平台验证结论。

## 2026-10-13：0.2.0 单个 src-gen 交付与结构化类型编辑

用户确认以一个项目的完整 src-gen 交付给各 App 开发者，首批覆盖 Linux x64、Windows x64 和 ARM64 Linux，ARM 工具链路径可配置。实现包括：公共模块源码随包复制、三平台 SDK/许可打包、统一 CMake/部署入口、默认日志模板、可配置 ARM 工具链、完整清单保护，以及 GUI 的结构体/枚举/嵌套字段编辑。

JSON 格式保持 v1，公共 CM/日志/时间 API 和生命周期语义不变。旧 out/generated 不自动迁移；默认 CLI 输出改为 out/delivery/demo/src-gen，GUI 为 out/delivery/editor/src-gen。打包缺少平台或检测到错误 SDK 时失败，不发布残缺交付物。

本次实际验证：

| 范围 | 结果 |
|---|---|
| Python | 全量 21 项通过；随后增加嵌套输出拒绝用例，交付专项 5 项通过（其中 4 项为重跑，合计 22 个用例）。覆盖三平台包内容、源码/手册保护、版本/架构检测、取消/失败保留旧包、生成一致性与并发隔离。 |
| Linux 仓库构建 | `./amw build --demo` 通过，native CTest 4 项全部通过。 |
| 独立交付包 | 将整包复制到 /tmp 的独立目录，不提供 AMW/DDS 安装路径，构建发布/订阅/日志示例并安装成功。安装后的 ldd 确认通信依赖来自程序相邻目录；日志运行通过。 |
| 通用手册 | 原样提取接入手册和日志手册的完整 CMake 代码块，分别构建 my_app/log_client；日志程序运行通过。仅 log/time 模式不查找 DDS。 |
| Linux 共享构建 | BUILD_SHARED_LIBS=ON 的 CM/绑定/生成契约/日志/时间及示例构建、安装通过；共享库设置相邻目录 RPATH，ldd 无缺失库，日志运行通过。修改已部署 XML 后再次 install，文件保持不变。 |
| Windows | 同一份交付目录复制到 Windows 本地，VS 2022/MSVC Release 构建、安装和日志运行通过；不提供外部 AMW/DDS SDK 路径。实际本机发布 250 次，两种消息各收到 239 条，回调失败 0，发送失败 0。发现时间差不能解释为吞吐/可靠性测量。 |
| ARM64 | 从相同交付包用可配置的 AMW_TOOLCHAIN_ROOT/AMW_COMPILER_PREFIX 选择 GCC 9.2，完整 CM/日志/时间/契约/三示例交叉构建与安装通过。没有板端运行。 |
| GUI | 在独立副本串行执行原浏览器编辑/重名重试回归、工程状态/流向图、新结构化类型流程。新流程从空工程创建枚举、嵌套结构体、定长数组、有界列表与字符串，验证错误重试、撤销重做，建立两个 App 的完整消息连接，生成三平台包并保存。无页面脚本错误。 |
| 自定义类型编译 | 对上述 GUI 创建的 vehicle.Category/Object/Frame 契约实际执行 CMake Release 编译，生成接口和 DDS 类型支持均通过。 |
| 文档 | 本地文件链接和 git diff --check 通过；架构 DOT 重新生成 PNG/SVG 并查看。 |

本次没有重新执行 Linux 实际网络集成、Windows 原生 Python/Java 生成、Windows 浏览器、ARM 上板、跨设备、实际 SHM、长期压力或消毒器测试；既有历史证据不能扩大为本次结论。Windows 新交付验证为静态中间件配合 SDK DLL，未重做 Windows 中间件 DLL 组合。编译器主版本检查只是早期防错，不证明任意同主版本工具链/目标系统 ABI 兼容。

现有 SDK 的非系统依赖由维护者通过 delivery_sdks.*.extra_files 补齐；当前 Linux x64 包含匹配的 OpenSSL 库与许可。操作系统基础库、C++ 运行库、Windows CRT 仍属于部署环境前提；doctor 不自动审计全部间接动态依赖。

复现（仓库根目录，先配置 config.local.json 的三平台 SDK）：

```bash
./amw doctor
python3 -m unittest discover -s tests -p 'test_*.py'
./amw build --demo
ctest --test-dir out/build/native --output-on-failure
cmake -S out/delivery/demo/src-gen/guide/examples -B out/build/delivery-client \
  -DAMW_GENERATED_DIR="$PWD/out/delivery/demo/src-gen" -DCMAKE_BUILD_TYPE=Release
cmake --build out/build/delivery-client --parallel 4
cmake --install out/build/delivery-client --prefix "$PWD/out/run/delivery-client"
./out/run/delivery-client/bin/guide_logging \
  --log-config "$PWD/out/run/delivery-client/bin/config/logging.xml"
```

浏览器需 Playwright/Chromium，在独立副本依次执行 tests/browser_flow.py、tests/browser.py、tests/browser_types.py；使用 18766/18765/18767 本地端口，仍共用测试副本的 out/editor 和 out/delivery/editor，不可并行。新截图在 out/browser-types。Windows/ARM 消费步骤见通用接入手册。

本机原始日志及隔离 GUI 副本位于忽略的 out/verification/；验证期间未改用户原有草稿或旧生成目录。本次沙箱阻止本地 HTTP 与 WSL Windows 互操作后，经授权在沙箱外完成相关验证，没有把初始环境失败计作通过。


## 2026-10-14：QoS 默认值、可视化配置与生成应用

本次验证对应工作区 0.2.0 的 QoS 扩展；前面 2026-10-13 的单目录交付记录仍是历史结果。支持与明确禁用项见 [QoS 指南](QOS.md)。

| 范围 | 本次结果 |
|---|---|
| Python | 完整 38 项通过，包含 16 项 QoS 默认值/继承/兼容性/范围/资源/版本目录/schema/有效快照用例，以及原有 22 项模型、生成、手册和保护用例。日志 qos-python-final.log。 |
| Linux 构建和 CTest | 默认 demo、自定义 examples/qos 和独立 QoS 消费工程构建；4 项 CTest 通过。 |
| 非默认生成分支 | 六种实体的枚举取值、XCDR2、Data-sharing on/auto、地址列表、十六进制字节、自定义属性及四种流量控制调度的生成代码通过 Linux SDK 语法编译。仅证明这些 C++ 分支可编译，不等于各策略行为都已测量。 |
| Linux 实际通信 | 隔离 user/net namespace，examples/qos 的可靠、持久历史、异步模式、分区和自定义流量控制配置进行两消息收发、读者退出及服务实例隔离测试，通过。 |
| Linux QoS 行为 | 发布 8 条消息后才启动 Reader，确实仅收到最后 3 条（编号 5、6、7）；无效深度由 DDS 拒绝，绑定销毁及 App 再启动通过。测试还检查默认控制器映射和自定义控制器配置。 |
| Windows | 同一 examples/qos src-gen 复制到 Windows，VS2022/MSVC Release 构建，并运行上述晚加入历史、QoS 失败清理和重启用例，通过。构建时修复 SDK imported target 在父目录不可见导致 DLL 导入宏丢失的问题。未验证 Windows 原生 Python/Java/浏览器生成链。 |
| ARM64 | GCC 9.2、可配置工具链路径，随包 publisher/subscriber/logging 示例交叉编译通过；未在板端执行。 |
| 浏览器 | 独立仓库副本中 browser_qos.py、browser.py、browser_flow.py、browser_types.py 四组通过。QoS 组覆盖默认值、未修改应用不脏化、非法值重试、枚举/数值/时间/列表、条件禁用、撤销重做、空策略、端点分配、分组参数、前后端有效值一致、真实生成与保存，无页面脚本错误。 |
| 文档/手册 | 新通用 QOS.md 原样随包并进入清单；固定示例随生成包实际编译。完整 examples/qos 输入通过真实 CLI 校验。 |

原始日志在 `out/verification/`：`qos-python-final.log`、`qos-default-build-final.log`、`qos-example-build-final.log`、`qos-network.log`、`qos-semantics.log`、`qos-windows.log`、`qos-arm-final.log`、`qos-emitter-probe.log` 及各 browser 日志。浏览器副本位于 `qos-gui-repo/`，不会读写用户正式 out/editor 草稿。

Windows 测试目录为用户 LocalAppData 下的 AMWQos-20261014，属于验证产物而非构建依赖。Linux 的 DDS 错误日志中出现 `HISTORY DEPTH must be higher than 0` 是故意注入的失败用例，通过后的 PASS 才是测试结论。

维护者在仓库根目录可复现：

```bash
python3 tools/update_qos_schema.py --check
python3 -m unittest discover -s tests -p 'test_*.py'
./amw build --demo --project examples/qos/project.cm.json \
  --output out/delivery/qos/src-gen --build-dir out/build/qos
cmake -S tests/qos-client -B out/build/qos-client \
  -DAMW_GENERATED_DIR="$PWD/out/delivery/qos/src-gen" -DCMAKE_BUILD_TYPE=Debug
cmake --build out/build/qos-client --parallel 4
unshare -Urn sh -c 'ip link set lo up && out/build/qos-client/qos_delivery_test'
```

最后一条要求 Linux 允许 user/net namespace，测试使用域 147/149；在 Windows 使用对应 Release 可执行程序。不要在已有同契约进程运行时直接进行未隔离网络测试。浏览器测试依赖 Playwright/Chromium，沿用上文独立副本方法运行 `tests/browser_qos.py`，该脚本会保存副本草稿并生成三平台交付包。

本次没有验证 Data-sharing/普通 SHM 的实际数据路径、跨机器传输、全部线程调度配置、全部资源组合、长期容量/性能、板端或硬实时。配置校验与编译结果不能替代这些运行证据。


## 2026-10-14：默认分组与编辑订阅

本次只修改 GUI 编辑流程，不修改 JSON 格式、生成命名规则或通信运行库。新 App 默认一个输出分组；已有单组沿用原名，多组时明确选择；输入自动命名，支持修改已有订阅和本地分组名称。类型下拉框显示短名称，保留完整名称与同名消歧。

在独立副本 `out/verification/groups-gui-repo/` 中执行 Linux Chromium 浏览器验收，五组通过：

- `tests/browser_groups.py`：默认输出组、多消息、多组选择、自动输入命名、切换来源与保留手工名称、订阅增减/重命名、保留多实例的不同来源、迁移/清理消息 QoS 覆盖、输入输出重名拒绝、错误重试、撤销/重做、类型名称消歧、保存后重新加载校验，以及窄窗口检查。关键编辑结果通过实际 Python 模型校验。
- `tests/browser.py`：原有导入/添加输出/订阅、连续错误重试、历史记录、真实生成和保存流程。
- `tests/browser_types.py`：结构化类型编辑、无需填写分组建立两个 App 的收发关系、真实生成含三个平台 SDK 的完整交付包。
- `tests/browser_flow.py`：图形连接、分支/回路、自订阅、移除/撤销、保存状态与窄窗口。
- `tests/browser_qos.py`：QoS 默认值、覆盖/校验重试、策略分配、有效值对照、真实生成与保存。

日志为 `out/verification/groups-browser*.py.log`；分组与表单截图位于副本的 `out/browser-groups/`。浏览器无页面脚本错误；`git diff --check` 通过。未将历史 C++、Windows、ARM 或真实网络结果算作本次重跑。

复现前提：配置好生成器和三平台 SDK、Python 依赖、Playwright/Chromium。请在独立仓库副本根目录运行，避免覆盖用户的 `out/editor/` 和交付目录。新增用例占用本机端口 18769，按顺序执行：

```bash
python3 tests/browser_groups.py
python3 tests/browser.py
python3 tests/browser_types.py
python3 tests/browser_flow.py
python3 tests/browser_qos.py
```

成功时每个脚本打印 PASS 并关闭服务；失败时查看 traceback 和相应 `out/browser-*/` 证据，修复后重跑受影响的流程。完成后按界面指南校验并保存正式工程，再生成交付包。


## 2026-10-14：业务样本类型转换（历史验证）

当时使用外部业务头文件验证 22 个结构体、244 个字段及嵌套数组的类型转换，完成 schema/语义检查、字段类型与数组维度编译断言、官方 Gen 和 Linux 生成代码语法编译。该样本及其项目专用说明现已移出公共仓库，不是当前输入模板。没有验证内存布局兼容、CRC、Windows/ARM 业务构建或板端通信。当前通用回归数据见 tests/fixtures/README.md。

## 2026-10-14：输出数据类型搜索与结构预览

输出类型改为搜索框与结果列表，不默认选择类型；即使唯一匹配也要明确点击。支持类型名、说明、递归字段路径检索、完整名称/版本消歧和按需展开结构预览。修改搜索词或清除选择后禁用“应用”，重新打开窗口也不复用上次类型。JSON 格式与生成规则没有变化。

新增 `tests/browser_type_search.py`，用当时的业务类型库验证：22 个结构体导入、名称优先排序、不区分大小写、说明检索、嵌套字段名 递归匹配路径、数组/列表路径、逐级结构预览、非方形二维数组维度显示、无结果/清除/重新打开行为、键盘选择、相同短名称与不同版本、枚举不能作为输出、无效循环引用草稿的搜索保护，以及撤销/重做和保存。发布事件必须保存明确选中的完整类型 ID 和版本，临时工程通过实际后端模型校验。

维护者复现：配置好 Playwright/Chromium、仓库 Python 依赖、生成器及 SDK，在独立仓库副本根目录运行，避免影响用户草稿。新增测试占用本机 18770 端口：

```bash
python3 tests/browser_type_search.py
python3 tests/browser_groups.py
python3 tests/browser.py
python3 tests/browser_types.py
python3 tests/browser_flow.py
python3 tests/browser_qos.py
```

脚本成功打印 PASS 并关闭服务。本次在 `out/verification/groups-gui-repo/` 隔离副本运行，以上六组 Linux Chromium 流程全部通过，包括真实 Fast DDS-Gen 生成、三平台交付包生成、保存和 QoS 回归，无页面脚本错误。日志为 `out/verification/groups-browser*.py.log`。已查看搜索截图，并通过文档链接与 `git diff --check` 检查；未重跑 C++、Windows/ARM 构建或真实 DDS 网络测试。当时的类型搜索截图已随历史验证目录清理；失败时检查 traceback，再重跑受影响流程。运行旧版本 GUI 服务时，应先保存草稿，再重启服务并打开草稿，以加载新增的静态资源路由。


## 2026-10-15：工作台布局与大类型库

界面调整为独立滚动的固定高度类型库、应用配置/数据流图视图切换、侧边类型详情、工程菜单、按需展开的部署概览和详细结果。分类依据实际 App 输出，类型详情区分直接输出与嵌套使用，并可追踪直接依赖和引用者。视图操作不进入模型或撤销历史。库详情与输出类型选择共用只读结构遍历；页面在脚本就绪后再载入模型。

新增 `tests/browser_workspace.py`，使用当时的业务类型库并扩展到 203 个类型，检查列表独立滚动、搜索框固定、页面高度不随类型数增长、筛选、嵌套字段搜索、类型/枚举详情、引用跳转、实际 App 使用关系、关闭后焦点、撤销/重做后的分类更新、工作区切换、错误摘要与详细结果，以及 1440/680 像素布局。这份历史业务样本已移出仓库；当前回归输入改为通用 `tests/fixtures/sample-types.cmtypes.json`，不依赖使用者的业务文件。

复现前提与之前浏览器测试相同：准备 Python、Playwright/Chromium、生成器及三平台 SDK，在独立副本根目录串行执行，避免写入用户草稿和交付目录。新增测试端口为 18771。

```bash
python3 tests/browser_workspace.py
python3 tests/browser_types.py
python3 tests/browser_type_search.py
python3 tests/browser_groups.py
python3 tests/browser_flow.py
python3 tests/browser.py
python3 tests/browser_qos.py
```

本次验收副本为 `out/verification/workspace-gui-repo/`；日志为 `out/verification/workspace-browser*.py.log`。截图在副本 `out/browser-workspace/`，包含桌面、侧边详情和窄窗口。此前中断测试在旧 groups 副本留下生成锁，本次新建独立副本继续验证，没有绕过生成目录保护或影响用户草稿。

本次七组 Linux Chromium 浏览器流程均通过：工作台、结构化类型编辑、输出类型检索、分组/订阅编辑、数据流图、原生成主流程和 QoS。包含真实三平台 src-gen 生成及保存；新增校验/保存进行中状态后，重新验证工作台、异步保存/流图和 QoS 流程通过。已检查桌面/窄窗口/详情截图，JS 语法、文档本地链接和 git diff --check 通过。此次没有重跑 C++、Windows/ARM 构建或真实 DDS 网络测试。


## 2026-10-15：工程栏操作入口

工程栏直接展示“新建工程 / 打开工程 / 导出工程包”，与当前工程名称、保存状态同排；窄窗口自动换行。主工具栏保留保存、校验、生成与撤销/重做，“编辑完整模型”移到独立的“高级工具”入口。“打开工程”的提示明确接收 `.amw.json` 工程包。文件格式、保存路径和生成逻辑保持原有行为。

在上述 workspace 隔离副本重跑 `browser_workspace.py`、`browser_type_search.py`、`browser_flow.py`、`browser.py`、`browser_types.py`，五组 Linux Chromium 回归全部通过，包含真实 src-gen 生成与草稿保存。另用临时浏览器检查 `out/verification/workspace-gui-repo/tests/toolbar_check.py` 验证工程按钮直接可见、实际点击导出/打开后的模型一致、文件选择器、高级编辑取消、Escape 收起与焦点返回，以及 375 像素宽度无横向溢出；结果在 `out/verification/workspace-toolbar_check.py.log`。

已查看更新后的 1440/680 像素截图，路径仍为副本的 `out/browser-workspace/workspace-desktop.png` 和 `workspace-narrow.png`。JS 语法、文档链接及差异空白检查通过。本次未修改运行库，未重跑 C++、Windows/ARM 构建或 DDS 网络测试。


## 2026-10-15：按工程 ID 保存与生成

CLI/GUI 默认交付目录统一为 `out/delivery/<工程ID>/src-gen`；GUI 草稿使用 `out/editor/<工程ID>`。界面在生成前显示完整目标路径，可设置绝对生成根目录并恢复默认；偏好只保存在本机浏览器站点，工程包格式不变。任务使用提交时的模型与路径，改名后保留旧目录。旧版草稿仍可显式加载，下次保存使用新目录。

新增 `tests/test_paths.py` 检查不同 ID 草稿保留、目录穿越/Windows 保留名/相对路径/符号链接拒绝，以及 CLI 默认目标与显式 --output 优先级。新增 `tests/browser_paths.py`（端口 18772）验证两份草稿隔离、改名和目标预览、自定义根目录刷新后恢复、恢复默认、非法保存请求，以及真实 Gen 生成中切换工程后仍交付原任务目录，原草稿保持不变。

沿用前述 Python/Playwright/Chromium/三平台 SDK 环境，在 workspace 隔离副本依次执行：

```bash
python3 tests/browser_paths.py
python3 tests/browser_workspace.py
python3 tests/browser_type_search.py
python3 tests/browser_flow.py
python3 tests/browser.py
python3 tests/browser_types.py
python3 tests/browser_groups.py
python3 tests/browser_qos.py
```

八组 Linux Chromium 流程全部通过，包括真实三平台包生成、异步保存、工程切换、分组、QoS 和类型编辑回归；没有改写用户正式草稿或交付目录。日志为 `out/verification/workspace-browser*.py.log`，新增截图为隔离副本 `out/browser-paths/project-paths.png`。已查看更新后的桌面/窄屏截图，JS 语法、CLI generate/build 帮助与文档本地链接、git diff --check 通过。本次未修改运行库，未重跑 C++、Windows/ARM 构建或实际 DDS 收发。

完整 `python3 -m unittest discover -s tests -p 'test_*.py'` 共 41 项通过（86 秒），包含真实生成、确定性/并行 Gen、失败/取消保留旧包、未知文件/嵌套目录保护和新增路径规则；日志为 `out/verification/project-paths-python.log`。


## 2026-10-15：生成包附带可打开的工程文件

每次生成在 src-gen 根目录附带 `<工程ID>.amw.json`，使用与 `metadata/model.resolved.json` 相同的序列化结果，自动计入生成清单。文件记录提交生成时的完整模型，不记录本机工具路径和浏览器偏好。根目录 README 说明打开工程及其他配置文件的用途；通用 guide/ 手册内容和 GUIDE_FILES 不变。

完整 `python3 -m unittest discover -s tests -p 'test_*.py'` 共 42 项通过（89 秒），包含真实 Gen 和三平台 SDK 打包。检查不同工程命名/内容、完整模型校验、两份 JSON 字节一致、摘要覆盖、手改工程文件拒绝覆盖，以及缺少新增文件的旧受控包升级。原有并行生成、确定性、失败保留和手册保护回归通过。

在 /tmp 下临时隔离仓库执行 `tests/browser_paths.py`，通过实际“打开工程”文件选择器载入生成的 `path_second.amw.json`，恢复模型与生成快照完全一致；测试同时在生成中切换工程，确认包内仍保存提交时配置。该 Linux Chromium 流程通过，临时副本完成后清理，没有改写用户现有交付包。临时日志为 `/tmp/amw-project-bundle-python.log` 和 `/tmp/amw-project-bundle-browser.log`，可能被系统清理；复现所需前提沿用上面的浏览器环境说明，端口为 18772。

文档本地链接与 git diff --check 通过。未改动公共接口和生成 C++，未重跑 C++ 编译、Windows/ARM 构建或实际 DDS 通信。现有生成包需要正常重新生成，才会获得根目录工程文件；未手工补写受控目录。


## 2026-10-16：团队仓库与本机文件隔离

完善 .gitignore，统一 local/ 为个人业务配置和实验目录，out/ 为草稿、生成与验证产物；保留公共源码、schema、配置模板、正式测试和通用模拟数据的可见性。新增 docs/CONTRIBUTING.md，清除已移出业务目录的链接、业务专用名称与个人绝对路径，更新 Linux 首次部署及业务配置保存说明。第三方组件作者、许可和修改说明保留。

从当前工作区的已跟踪文件及未被忽略的新公共文件构造临时副本；副本不包含原仓库 out/、业务文件或个人环境，另行注入本机 config.local.json 以使用已安装 SDK/Gen。没有修改原仓库索引、hooks、全局 Git 配置或提交历史，也没有 commit/push。检查结果：

- 模拟个人配置、业务 JSON、实验脚本、虚拟环境、IDE 设置、构建文件、生成包、抓包与日志，均被忽略；公共 JS/Python/示例 JSON/测试样本/配置模板仍可见，已跟踪测试源码的修改仍会显示。
- 原仓库 `git ls-files -ci --exclude-standard` 无输出，没有需退出跟踪的本机文件。
- 副本 doctor、demo/QoS 工程校验、QoS schema 同步检查通过。
- 完整 Python 42 项通过，包含真实 Gen/三平台 SDK 打包和生成保护回归。
- browser_type_search.py、browser_workspace.py 两组 Linux Chromium 流程通过，验证独立编写的通用 22 类型样本与 203 类型布局，不依赖业务头文件。
- 测试后副本公共文件无修改，无新增文件漏出忽略规则。文档本地链接、CLI 参数、类型示例（按跨文件依赖合并）与通用样本校验、git diff --check 通过。

复现前提：按 GETTING_STARTED.md 配好 Linux Python、SDK/Gen；浏览器流程另需 Playwright/Chromium，并在包含全部本次公共变更的独立副本中串行执行 tests/browser_type_search.py、tests/browser_workspace.py。检查忽略规则和待提交文件的方法见 CONTRIBUTING.md。此次临时副本已清理，日志暂存在 `/tmp/amw-repository-review-logs/`，不属于仓库输入且可能被系统清理。

这是隔离源码副本上的验证，依赖当前机器已安装的外部工具；没有重新安装全新 Linux 系统，也没有重跑 C++、Windows/ARM 构建或实际 DDS 网络测试。此前各平台验证结论仍按各自日期与范围记录。

## 2026-10-16：CM 规范差距评估

新增 [CM_GAP_ASSESSMENT.md](CM_GAP_ASSESSMENT.md)，以当前 main 工作区（检查时 HEAD 为 94321f1，含未提交的 0.2.0 修改）对照 AUTOSAR R25-11。取得 CM SWS 675 页、DDS 通信协议 70 页及 DDS 服务发现协议 29 页正文，抽取文本并重点审阅报告列出的章节；未逐页/逐条审核整个规范集。

对照公开接口、运行库、模型/schema、生成器、DDS 绑定和已有测试，形成 26 个条款组/评估项及建议验收条件。已区分规范条款与本项目建议、published 文件与 DRAFT 条款、确定差异与待验证项；登记 partition 命名文本差异，以及 Core/Manifest/语言绑定等未展开依赖。下载件摘要、获取限制与复核入口记在报告中，原规范和临时 PDF 解析库仅放 /tmp，不新增仓库依赖。

本次检查报告中的条款 ID 是否存在于对应规范正文、源码文件/符号与本地 Markdown 链接，以及 git diff --check。没有改动 CM 行为、生成器、GUI、schema、SDK、通用随包手册或用户生成目录；没有新增或重跑 Python/C++/浏览器/网络/跨平台测试，没有 commit/push。历史测试只作为既有产品能力的证据入口，不视为标准符合性通过。本次未开始报告建议的架构改造。

## 2026-10-19 启动网络覆盖与外部应用接入验证

公共 API 增加 `NetworkOptions`：测试默认继承、显式覆盖/清空、IPv4 格式拒绝及 Domain 保持；真实生成 App 验证构造后修改选项不会影响启动，错误地址启动失败且可以安全 stop。`domain_id` 名称冲突进入公共模型校验。

本次执行结果：

- Python 全套 42 项通过；名称保留规则修改后模型 15 项复验通过。
- `./amw build --demo` 成功，native CTest 4/4；通用手册固定 CMake/C++ 示例实际编译成功。
- 外部发布应用的 Linux 仿真和 ARM64 交叉编译通过；Linux Qt 与 Windows MSVC 接收应用构建及各 4 项应用测试通过。这些是外部应用接入证据，其业务测试不属于本仓库测试集。
- 隔离 Linux 网络验证发布/订阅、并发提交与停止/重启、失败启动；Windows 回环收发与记录验证通过。测试使用 BEST_EFFORT，允许丢帧，未验证逐帧可靠记录。匹配数在发送端退出后可能为 0，不能据此判断此前未建立匹配。

外部业务适配、测试脚本、日志、回滚备份和发布清单不进入本仓库 Git；本地验证产物由忽略的 `out/verification/` 保存，不作为新环境可直接复现的测试输入。当前未在实际板端执行新二进制，也未验证目标板与 Windows 经真实以太网直连。

外部部署打包验证：Fast DDS、Fast CDR、foonathan_memory 的部署副本按 SONAME 去重，实体库执行 `strip --strip-unneeded`，别名使用相对软链接。动态符号和依赖保持一致；普通文件、软/硬链接输入、重复打包及同 SONAME 内容冲突拒绝检查通过。部署目录与归档内容一致，src-gen 原始库摘要未改变。该打包脚本由外部应用维护，本项不代表生成器默认执行符号剥离，也不增加板端运行结论。

## 2026-10-20：提交前仓库检查

核对待提交的 49 个已跟踪文件修改与 35 个新增文件，覆盖公共实现、构建模板、GUI、schema、示例、正式测试和文档。个人配置、生成包、SDK 副本及本地验证产物由忽略规则排除，未发现已跟踪文件与忽略规则冲突。业务专用交接记录整理为上述通用验证范围，保留实际板端联调未完成的限制。

在仓库根目录执行完整 Python 测试，42 项通过（97 秒）；`python3 tools/update_qos_schema.py --check` 和 `git diff --check` 通过。本次未重新执行 C++ 构建、浏览器、Windows、ARM 或网络测试；历史结果仍按各自日期和范围理解。

## 2026-10-20：普通 SHM 与 UDP 双订阅

在外部应用接入中，以同一份生成契约验证一个发布进程同时向 SHM 与 UDP 两个订阅进程发送完整结构体。环境为 Linux x64、GNU 11、Fast DDS 3.6.2.0；测试运行于隔离网络命名空间及单独挂载的共享内存空间。发布端与本机订阅端开启普通 SHM，另一个兼容订阅端仅开启 UDP，Data-sharing 保持关闭。

- 正常分发 120 帧：SHM 订阅端与 UDP 订阅端各收到 120 帧；逐项验证 11 个不同帧号字段及两个 uint8 计数的整数输出。
- 测试专用发送拦截器屏蔽 UDP 用户 DATA/DATA_FRAG 报文，保留内置发现消息；发布端仍匹配两个 Reader。SHM 订阅端收到 120 帧，UDP 订阅端收到 0 帧，并记录实际被屏蔽的 UDP 发送。这一对照用于证明实际 SHM 传输，不能仅凭共享内存文件存在或匹配数作结论。
- 实际应用发布适配层的并发提交、停止/重启与非法启动参数回归通过；独立订阅工具的无数据超时、非法参数及 SIGINT 退出检查通过。
- 独立订阅工具 Linux x64 构建运行、GNU 9.2 ARM64 交叉编译与可搬移运行包构建通过；部署副本 strip、SONAME 别名及重复打包检查通过，原始 src-gen 摘要不变。
- 外部发布应用的完整 ARM / ARM-lite 构建与部署打包通过；Windows 接收应用在 MSVC 下构建和 4 项 CTest 通过。使用仅开启 UDP 的兼容发布器验证新接收程序，验证副本与最终发布 exe 均收到并记录 118 帧，MF4 数量与接收计数一致；此项是 Windows 本机回环，不是板端到 Windows 的实网验证。

测试脚本、业务契约和详细日志保存在忽略的本地验证目录，不新增公共测试依赖；该接入测试不是 clone 后自带的通用测试入口。复核需要原验证目录中的发布样本、UDP 对照接收器和拦截器。上述接收计数不是 BEST_EFFORT 的逐帧保证，也不证明故障后自动回退、吞吐量、延迟、长期容量或零拷贝。未执行实际 ARM 板端、跨设备以太网或 Data-sharing 路径验证。

## 2026-10-20：ARM 板端匹配查询死锁与修复

在 ARM64 Linux 6.1.83-rt28 目标板，通过 SSH 启动真实业务发布进程及同机订阅工具，
普通 SHM 开启、Data-sharing 关闭，未加载 UDP 拦截器。两进程输出均重定向到文件，
避免将终端输出等待误判为通信问题。原订阅程序收到 33 条后停止更新，进程未退出。
远程线程栈显示 SHM 接收线程在 `NativeReader::on_data_available → Endpoint::enqueue`
等待 CM 锁，查询线程在 `get_subscription_matched_status` 等待 DDS Reader 锁。
结合源码确认 `Endpoint::matches` 持 CM 锁调用绑定，导致锁顺序相反。

修复在公共 `src/cm.cpp`：只在锁内复制 Reader/Writer 的共享引用，锁外执行匹配查询，
并保证与 stop 重叠时端点不会提前销毁。无公共 API、JSON 或 QoS 格式变化，无需修改 DDS SDK。

- 新增通用 `cm_matches` 回归：模拟接收线程持绑定锁回调入队、另一线程同时查询匹配。
  旧实现于 3 秒断言失败；修复后通过。另覆盖 Reader 和 Writer 查询期间并发 stop 的对象生命周期。
- GNU 11 native 构建及 CTest 5/5 通过；通用手册固定发布、订阅、日志示例重新生成 demo 后编译通过。
- GNU 9.2 ARM64 构建成功。将修复后订阅工具上传到板端临时目录，
  保持原发布进程连续运行，180 秒收到并打印 3599 条，帧号 9759～13357 连续，
  定时停止完成，`replaced=0`、`rejected=0`、`callback_failed=0`。
- 板端 `/opt` 正式程序、用户业务源码及原交付 src-gen 未被替换；
  调试启动的应用已停止。临时修复程序和重新生成的包保存在忽略的验证目录中。
  已有应用必须重新生成并编译才能取得修复，单独替换 Fast DDS 共享库无效。

本机证据保存在忽略的 `out/verification/` 下的专用验证目录，包含原始调用栈、
旧版回归失败记录、修复后 CTest、交叉编译日志及导出的板端日志。
初次抓栈使用了早期同源构建的符号文件，底层 DDS 动态符号及入队栈可识别，
一个优化栈帧存在符号偏差；后续以与板端二进制摘要一致的构建进行地址映射，
确认对应 `NativeReader::matches`。详见该目录 HANDOFF.md。
本次未重跑 Windows、跨主机网络或拦截实验，未进行长时间压力、性能或 Data-sharing 验证。

## 2026-10-22：公开源码与本地配置整理

公开说明改用通用平台名称，清理内部项目标识和专用证据目录名称；本机配置、原始证据与已有生成物保留。当前候选公共文件的已知内部标识与路径扫描、Git 忽略边界、差异格式检查通过；三平台 SDK/Gen 的 doctor 和 demo 模型 validate 通过。未修改运行库或生成器，未重跑 C++、GUI 或板端通信测试。

当前文件整理后，以完整快照建立新的单提交 main；旧 Git 数据与个人引用完整保存在仓库外的本地备份中，不带入公开仓库。旧远程地址不继承，推送由维护者自行完成。先前文件检查报告仍在忽略的 local/ 中。此次 Git 基线整理不改变代码、依赖或既有平台验证范围。
