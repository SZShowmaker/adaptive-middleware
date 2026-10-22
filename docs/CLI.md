# 命令行使用参考

以下命令在本仓库根目录执行。Linux 入口是 `./amw`，Windows 开发者 PowerShell 入口是 `.\amw.ps1`，后面的子命令和参数一致。

## 1. 五个命令分别做什么

| 命令 | 作用 | 成功后得到什么 |
|---|---|---|
| doctor | 检查配置中的 三平台 SDK 版本/架构/许可及 Gen 版本，并运行 Java 调用 Gen。 | 输出检查信息，不生成文件。 |
| validate | 读取工程，检查 JSON 格式、类型引用、连接、部署与所支持的策略兼容性。 | 输出 valid 和类型/App/实例数量。它不调用 Gen，也不证明生成代码一定能编译。 |
| generate | 先校验，生成业务接口，并打包公共模块及三平台 SDK。 | 完整 src-gen 交付目录。 |
| build | 先执行同样的生成流程，再调用 CMake 编译。 | 中间件库、生成接口库；加 --demo 才编译自带样例程序。 |
| gui | 加载一个有效工程并启动本地配置网页服务。 | 在终端打印本地网址，保持运行直至 Ctrl+C。 |

查看帮助：`./amw --help`、`./amw generate --help` 等。常见校验、配置和子进程错误会输出原因并返回非零退出码；自动化脚本应按退出码判断成功，不只搜索输出文本。

## 2. 参数和默认值

| 参数 | 哪些命令接受 | 默认值或说明 |
|---|---|---|
| --config | 全部命令 | 仓库根目录的 config.local.json。validate 接受该参数，但实际校验不读取本地工具配置。 |
| --project | validate / generate / build / gui | 仓库的 examples/demo/project.cm.json。必须是工程入口文件。 |
| --output | generate / build | 默认按模型的工程 ID 使用仓库 out/delivery/<工程ID>/src-gen；显式指定时使用该目录本身。目标应不存在，或是本工具此前完整生成的目录。 |
| --build-dir | build | 仓库的 out/build/native。换编译器、目标平台时换构建目录。 |
| --build-type | build | Debug；还可选 Release、RelWithDebInfo。 |
| --demo | build | 默认关闭；只适用于自带 demo 契约。 |
| --toolchain | build | 可选 CMake 工具链文件；同时关闭本机运行测试目标。额外的交叉工具链参数应使用 BUILD.md 中的直接 CMake 命令传入。 |
| --port | gui | 8765；只能监听本机 127.0.0.1。 |

显式传入的相对参数路径按当前终端目录解析；工程内 `type_files/deployment_file` 相对工程入口解析；本地配置中的 SDK/JAR/Java 相对配置文件解析。三者的基准不同，自动化中也可以统一使用绝对路径。

## 3. 为自己的工程生成

假设已按 [界面指南](QUICKSTART_GUI.md#7-保存业务源配置) 将自己的源配置保存到 `local/projects/vehicle/project.cm.json`（local/ 被中间件仓库忽略，正式业务版本请另行管理）：

```bash
./amw validate --project local/projects/vehicle/project.cm.json
./amw generate --project local/projects/vehicle/project.cm.json --output out/delivery/vehicle/src-gen
./amw build --project local/projects/vehicle/project.cm.json --output out/delivery/vehicle/src-gen --build-dir out/build/vehicle --build-type Release
```

build 会重新校验和生成，不能用它绕过生成目录的手改检查。如果只想编译已有产物，使用 `cmake --build <已经配置好的构建目录>`。

省略 --output 时，从工程内容的 project_id 推导 `out/delivery/<工程ID>/src-gen`，不使用文件名或工程文件所在目录的名称。同一 ID 再次生成会更新其合法、未手改的产物；改 ID 后使用新目录，旧目录保留。不同工程应使用不同 ID，并避免仅大小写不同。显式 --output 仍指定完整目标目录；build-dir 仍需按工程和平台单独配置。

## 4. 指定本地配置、继续界面工程

```bash
./amw generate --config config.arm.local.json --project local/projects/vehicle/project.cm.json --output out/delivery/vehicle/src-gen
./amw gui --project local/projects/vehicle/project.cm.json --port 8766
```

生成 C++ 本身不由 SDK 路径决定 CPU 架构，最终架构在编译时选择。不要仅因文件叫 config.arm.local.json 就认为产生的是 ARM 动态库。

GUI 默认草稿为 `out/editor/<工程ID>/`，生成目录为 `out/delivery/<工程ID>/src-gen`，不会回写 --project 的输入目录。gui 没有 --output 参数；界面的“生成位置设置”可指定本机绝对根目录，最终生成到 `<自定义根目录>/<工程ID>/src-gen`。该偏好只保存在当前浏览器站点，不随工程导出，不影响 CLI。不同端口仍可能编辑相同 ID，建议同一仓库只运行一个编辑器。

## 5. 失败时保留什么

生成器在临时目录工作，成功后才替换正式输出。旧输出若包含额外文件、符号链接或被手改的生成文件，生成会拒绝覆盖。突然断电或强制结束进程可能留下锁或备份目录，恢复方式见 [常见问题](TROUBLESHOOTING.md)。

生成过程可追踪信息保存在 generation-manifest.json，包括模型、模板、JAR 摘要、三平台编译器要求以及全部生成/随包文件摘要。它用于核对生成批次，不是程序运行时读取的网络配置文件。
