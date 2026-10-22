# 常见问题：按失败发生的阶段排查

先确认失败在哪一步：读取配置、校验模型、生成、编译，还是运行通信。保留完整错误文本、执行命令及所用配置，通常比只截最后一句“失败”更容易定位。

## 1. 启动工具或 doctor 失败

| 现象 | 检查和处理 |
|---|---|
| 找不到 config.local.json | 首次使用从 config.example.json 复制，并填写真实路径；已有文件不要直接覆盖。 |
| No module named jsonschema | 当前运行 amw 的 Python 是否就是安装 requirements.txt 的环境？激活虚拟环境后用 python -m pip 安装。 |
| python 指向错误版本 | Linux 检查 python3，Windows 检查 python；要求 3.10+。amw.ps1 调用的是 PATH 中的 python。 |
| delivery_sdks / SDK missing / wrong architecture | 按 config.example.json 配置三平台 SDK；各 sdk_prefix 指向匹配平台安装根目录。 |
| Unable to access jarfile / 找不到 Java | generator_jar 必须是存在的 JAR 文件，java 应是可执行程序或 PATH 中的 java。 |
| generator version mismatch | 确认配置指向 Fast DDS-Gen 4.3.0，不能只检查另一个终端命令中的 fastddsgen 版本。 |
| Windows JSON 路径解析失败 | 优先用 C:/tools/...；若用反斜杠，在 JSON 字符串中要写成双反斜杠。 |

PowerShell 若禁止执行脚本，先遵循公司的执行策略。在开发者终端中也可以直接用 `python .\amw ...` 运行 Python 入口；它与 amw.ps1 调用的是同一个程序。虚拟环境未激活时可显式使用 `.\.venv\Scripts\python.exe .\amw ...`。Windows 构建的 CMake 参数见 tools/build_windows.ps1，脚本授权按团队规范处理。

## 2. JSON 校验失败

先核对 `--project` 是否传了 project.cm.json。类型库 `.cmtypes.json` 和界面导出的 `.amw.json` 都不能直接作为该参数。

典型类型错误见 [类型指南的排错表](JSON_FORMAT.md#6-常见问题与排查方法)。连接和部署错误还要检查：

- App 的输入/输出端口是否存在，引用的服务接口名和版本是否一致。
- 输入是否选择了一个合法来源，部署选择是否符合逻辑连接。
- 修改 App 或端口后，部署中的 provides/requires 是否一起更新。
- Reader 要求可靠传输时，来源 Writer 是否也提供 reliable；历史数据策略是否兼容。

界面可以保存未通过校验的草稿，但重新打开时会先校验。若打不开，使用文本编辑器修复源文件，或恢复已验证的旧版本；“打开工程包”也不能绕过校验。

### 重名报错后，连接出现了，但 App 中没有对应输入

这是旧版界面的缺陷：弹窗报错时恢复了模型副本，重试仍修改旧 App 对象，导致端口与连接不一致。修复版在每次提交时重新查找当前 App；“选择输入”和“增加输出”都已修正，允许在原弹窗内改名后再次提交。

修复不会自动补齐已经产生的异常连接。如果旧页面仍然打开，按以下顺序保留编辑并恢复：

1. 可先“导出工程包”留存现场备份。在旧版“连接概览”中仅移除缺少对应输入的那条连接；新版则点选数据流向图中的对应连线，在详情中“移除连接”。
2. 重新打开目标 App 的“选择输入”，选择原来的来源，填写不重复的端口 ID，勾选需要的消息并应用。关闭后重新打开弹窗也能避开旧版的失效引用。
3. 确认 App 输入和连接一致，点击“校验”，通过后“保存草稿”。
4. 更新代码后，停止旧 GUI，在仓库根目录执行下列命令，再刷新页面。这样会加载刚保存的工程；不带 `--project` 会加载默认示例。

```bash
# 以下假设工程 ID 是 vehicle_demo，替换为你的实际 ID
./amw gui --project out/editor/vehicle_demo/project.cm.json
```

不要直接刷新尚未保存的页面。若异常草稿已经保存且页面已关闭，先备份文件，再修复 `project.cm.json` 中的连接及 `deployment.json` 中对应的输入绑定，或恢复已校验的版本；无法校验的现场备份不能直接通过“打开工程包”载入。

## 3. 校验通过，但生成失败

校验只检查模型，不会实际调用 Gen。生成阶段还需要 Java、JAR、C/C++ 预处理器及三平台交付 SDK。

| 现象 | 检查和处理 |
|---|---|
| Fast DDS-Gen failed | 查看后面的完整输出；检查 IDL 生成错误、Java 和预处理器是否可用。Windows 使用 VS Developer PowerShell。 |
| each demo app needs at least one deployment instance | 虽然错误文本带 demo，这条规则也适用于自建工程；为每个 App 添加至少一个部署实例。 |
| refusing to overwrite unmanaged output directory | 目标不是本工具完整生成的目录；换一个尚不存在的输出路径。不要将生成目标指向手写业务目录。 |
| generated file was edited | 文件内容与清单不一致。先保留手改内容，将需要的业务修改移出生成目录或落实到源 JSON，再选择新目录生成。 |
| output contains unmanaged files or symlinks | 检查额外文件、编辑器备份或符号链接；保留它们后使用干净的新目录。 |
| generation lock exists | 同一输出已有任务，或异常退出留下了同名 .lock。先确认是否仍有生成进程，不要在任务运行时移走锁。 |
| previous generation backup exists | 输出旁存在 .previous 备份，可能上次替换中断；先检查、备份旧结果，不要直接删除。 |

恢复时最简单的办法是保留异常目录，用 CLI 指定一个新的 --output。只有确认没有正在运行的任务、且已保留需要的文件后，才人工整理旧锁和备份。GUI 不能修改输出路径，必要时退出编辑器后再恢复其固定输出目录。

## 4. 编译失败

| 现象 | 检查和处理 |
|---|---|
| 找不到 fastdds / fastcdr 的 CMake package | 确认收到完整 src-gen，dependencies 中平台 SDK 和 CMake 配置齐全；维护者检查打包来源。 |
| 找到版本但不满足 EXACT | 要求 DDS 3.6.2.0/CDR 2.3.6；不要把另一个版本的头文件和库拼到一起。 |
| 找不到 amw | 0.2 交付方式不需要 find_package(amw)，改用 add_subdirectory(src-gen)，见接入手册。 |
| 已有 amw_project / 重复定义 | 是否同时加入两个生成包，或既链接 amw_project 又手动编译同一组生成 .cxx？当前只支持一个统一生成包。 |
| 自建模型加 --demo 后编译失败 | 去掉 --demo；样例 main 只认识仓库 demo 接口，自己的模型需要自己的业务 main。 |
| file format、架构或链接符号错误 | 检查 x86_64/ARM/Windows、编译器、Debug/Release 和 ABI 是否一致。 |
| 换工具链后 CMake 仍用旧编译器 | 换一个构建目录，不复用旧 CMakeCache。 |

## 5. 程序启动失败或没有数据

先解决动态库加载问题：Windows 检查 SDK 的 bin 是否在 PATH 中；Linux 检查加载器能否找到匹配的 .so。不要通过随意复制另一版本的同名库来消除错误。

启动阶段检查 App 实例名称，以及 runtime.start 的结果。`missing subscription handler` 表示某个输入没有注册回调；首次 start 已冻结配置，应修正初始化后重建 App 对象。

程序都启动了却没有消息时，依次检查：

1. 两端是否来自一致的类型/服务约定，Domain 是否相同。
2. 对照 routes.json，Reader 与 Writer 的 Topic、类型及服务实例是否相符；尤其检查前摄/后摄来源。
3. 两端是否均已 start，发送者是否持续运行；启动后需要时间完成发现。
4. 查看 matches()、sent、send_failed、received、delivered，而不是只看 try_publish 是否返回成功。
5. 再检查本机网卡选择、以太网连通性、防火墙和 DDS 发现条件。跨主机测试没有被本仓库当前验证记录覆盖，应在目标环境实测。

matches 为 0 表示尚未匹配，但 matches 大于 0 也不能证明业务健康。共享内存开关打开不代表已经走 SHM，定位传输路径需要额外观察；不要仅凭“同一 SoC”推断。

如果程序退出前只发布一次并立即 stop，样本可能还在本中间件队列里就被丢弃。先用 [持续发送的 demo](BUILD.md) 验证通信，再设计业务退出时序。

## 6. 向维护者提供什么信息

提供仓库提交、操作系统/编译器、SDK 和 Gen 版本、完整命令及错误文本；模型错误附最小复现 JSON，通信问题附相关实例的 routes.json、端点统计和网络配置。路径配置可去掉本机用户名等无关部分。优先保留第一次失败时的输出，避免在不明原因时重复覆盖生成物。


## QoS 配置或启动失败

先在“QoS / 默认策略 / 网络”查看参数当前值与继承值。`history.depth` 错误通常表示 KEEP_LAST 深度超过资源容量；Reader RELIABLE / Writer BEST_EFFORT、Deadline 或分区错误需要检查连线两端的最终策略。“未知流量控制器”需检查实例继承到的 Participant 控制器列表及异步发布模式。

生成前的校验不能替代目标环境检查。DDS 端点创建失败时记录 `runtime.start().detail`，核对 `metadata/qos.effective.json`、内存、线程权限、共享目录和网络地址。不要修改生成头文件或元数据来试图热更新。完整操作见 [QoS 指南](QOS.md)。
