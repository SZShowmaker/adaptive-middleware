# 只接入一个 src-gen 文件夹

本手册适用于 0.2.0 的完整交付包。每个项目生成一份 `src-gen/`，包含全部 App 的接口以及 CM、日志、时间工具和三个平台的 DDS SDK。同一份包可以交给各 App 开发者，各自只构造自己的 App 实例。

## 1. 前提与完整接入示例

应用开发电脑需要 CMake 3.22+ 和与包内 SDK 匹配的 C++17 编译器。Linux x64、ARM64 Linux 和 Windows x64 分别使用自己的编译器；不需要安装本中间件仓库、AMW SDK、DDS SDK、Python、Java 或 Gen。

在生成目录外维护业务文件，目录如下：

```text
my-app/
├── CMakeLists.txt
├── main.cpp
└── src-gen/                  原样复制完整交付目录
```

下面是可以保存的完整 `CMakeLists.txt`：

```cmake
cmake_minimum_required(VERSION 3.22)
project(my_app LANGUAGES CXX)
add_subdirectory(src-gen)
add_executable(my_app main.cpp)
target_link_libraries(my_app PRIVATE amw::app)
amw_deploy(my_app)
```

`main.cpp` 由应用提供，通过 `apps.hpp` 使用本项目接口，也可包含 `amw/log/log.hpp`、`amw/time/time.hpp`。接口名称以 `generated/apps.hpp` 和 `generated/types.hpp` 为准；固定示例见本手册 `examples/`，仅对应 demo 契约。

在 **my-app 根目录**构建 Linux x64：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
cmake --install build --prefix "$PWD/run"
```

产物为 `build/my_app` 和部署目录 `run/bin/`。`amw_deploy` 将所需通信共享库复制到程序旁，设置 Linux 的相邻库查找路径，并提供安装规则。可在 `run/bin` 工作目录运行 `./my_app`。应用若使用日志，应显式调用 initialize，指定 `config/logging.xml` 或自己的配置路径；打包不会自动初始化日志。

默认日志模板被复制到程序旁的 `config/logging.xml`；已有配置不被后续构建/安装覆盖。修改这份运行配置，重启应用生效。交付目录中的模板由生成器管理，不应直接修改。

## 2. 包内各部分的职责

```text
src-gen/
├── CMakeLists.txt             统一接入入口
├── generated/                apps.hpp、types.hpp、apps.cpp、wire/
├── runtime/                  CM、日志、时间源码及公共头文件
├── dependencies/             linux-x64、linux-arm64、windows-x64 SDK
├── cmake/                    公共构建和部署规则
├── toolchains/               可配置的 ARM64 工具链文件
├── config/logging.xml         日志默认模板
├── metadata/                 IDL、模型和路由
├── guide/                    本通用手册，所有项目原样附带
└── generation-manifest.json   所有随包文件的版本和摘要
```

公共运行库在中间件仓库统一维护，随包复制一次，同一 CMake 构建中的多个应用复用 targets。业务契约源码根据 JSON 生成，业务 DTO 和公共 CM API 仍独立于 DDS 实体。

`amw::app` 包含当前工程的通信接口，并传递 CM、日志、时间依赖。仅需要基础模块的目标可链接 `amw::log`、`amw::time`；如整个构建都不需要通信，可在 add_subdirectory 前设置 `AMW_BUILD_CM=OFF`，此时不查找 DDS SDK，也不创建 `amw::app`。

一个构建当前只接一份项目契约。多个可执行程序可链接同一个 `amw::app`；多份契约需先在配置端合并，不能在同一构建加入两个独立 src-gen。

## 3. Windows x64

在 VS 2022 x64 开发环境中，从 **my-app 根目录**执行：

```powershell
cmake -S . -B build-windows -G "Visual Studio 17 2022" -A x64
cmake --build build-windows --config Release --parallel 4
cmake --install build-windows --config Release --prefix "$PWD/run-windows"
```

运行 `run-windows/bin/my_app.exe`。所需第三方 DLL 由 amw_deploy 部署在程序旁；Windows 系统应已安装匹配的 MSVC 运行库。首批 SDK 使用 Release、动态 CRT（/MD）。多配置生成器只提供 Release/RelWithDebInfo/MinSizeRel；Debug 或 /MT 配置会被拒绝，不能强行混用。

## 4. ARM64 Linux：工具链路径在构建时指定

在 Linux 开发电脑的 **my-app 根目录**执行，将占位路径换为实际编译器目录：

```bash
cmake -S . -B build-arm \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/src-gen/toolchains/aarch64-linux.cmake" \
  -DAMW_TOOLCHAIN_ROOT=/path/to/aarch64-toolchain \
  -DAMW_COMPILER_PREFIX=aarch64-none-linux-gnu \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build-arm --parallel 4
cmake --install build-arm --prefix "$PWD/run-arm"
```

`AMW_TOOLCHAIN_ROOT` 下应有 bin/ 编译器；前缀不带结尾连字符。默认 sysroot 由编译器查询，另有目标 sysroot 时增加 `-DAMW_SYSROOT=/path/to/sysroot`。也可使用项目自己的 CMake toolchain 文件，正确设置 Linux/aarch64、编译器与 sysroot。

包内首批 ARM SDK 对应 GNU 9.x，实际验收使用 GCC 9.2。路径可以改变，但换编译器、ABI、sysroot 或目标系统时仍须匹配依赖；工具链路径可配置不意味着任何 ARM 库都兼容。不同编译器主版本会在 CMake 配置时被拒绝，应由维护者提供匹配 SDK 后重新打包。

将 `run-arm/bin/` 中程序、共享库和配置部署到板端。操作系统基础库、目标 C++ 运行库由板端系统提供。交叉编译成功不代表已经上板验收。

## 5. 编译随包固定示例

仅适用于 demo 契约。在 **src-gen 根目录**执行，构建和安装目录放在包外：

```bash
cmake -S guide/examples -B ../demo-build \
  -DAMW_GENERATED_DIR="$PWD" -DCMAKE_BUILD_TYPE=Release
cmake --build ../demo-build --parallel 4
cmake --install ../demo-build --prefix "$PWD/../demo-run"
```

得到 `demo-run/bin/guide_publisher`、`guide_subscriber` 和 `guide_logging`。在该 bin 目录，先启动订阅者，再在另一终端启动发布者：

```bash
./guide_subscriber monitor 20
```

```bash
./guide_publisher camera_front 500
```

独立日志示例：

```bash
./guide_logging --log-config config/logging.xml
```

Windows 使用对应 `.exe`，构建/安装加 `--config Release`；ARM 配置时增加第四节的工具链参数。固定示例只适用于 demo App 命名，自定义项目应使用自己的接口，不要为运行 demo 修改业务契约。

## 6. 常见错误与下一步

| 现象 | 检查与处理 |
|---|---|
| 提示缺少 profile.cmake / SDK 文件 | 完整复制 src-gen，不只复制 generated/ 或某些头文件。 |
| 编译器版本不匹配 | 查看 dependencies/对应平台/profile.cmake，选择匹配工具链，或由维护者重新提供 SDK。 |
| 提示外部 DDS target 已存在 | 先接入 src-gen，移除应用中重复查找的其他 DDS SDK，避免混用。 |
| 找不到 apps.hpp | 链接 amw::app，不要自行拼 include/lib 路径。 |
| 类/字段不存在 | 检查 generated/apps.hpp 和 types.hpp，固定示例不适用于所有工程。 |
| 启动失败或 matches 为 0 | 检查回调、metadata/routes.json 中实例来源、Domain、网卡和防火墙。 |
| 日志初始化失败 | 查看 Result.detail 和绝对配置路径，确认运行工作目录，或传入绝对 XML 路径。 |
| 找不到 DLL/共享库 | 对应用调用 amw_deploy，并用 cmake --install 部署；同时核对系统运行库。 |
| 重新生成拒绝覆盖 | 保留本包，恢复原始受控文件或生成到新的空目录；业务文件移到包外，不删清单绕过保护。 |

修改消息、连接、部署或中间件版本后，由维护者重新生成完整目录；应用团队更新整个包并重新构建。网络参数仍编译进代码，metadata JSON 是快照，不是运行时热配置。日志 XML 则在显式初始化时读取。

下一步阅读 [API](API.md) 了解发送成功、队列、回调和停止的准确语义，阅读 [日志与时间工具](LOGGING.md) 接入日志。

需要在机器上选择网卡时，构造 App 传入 `NetworkOptions`，详见 [启动网络覆盖](API.md#启动时选择本机网络)。接口地址和对端地址无需为每台机器重新生成交付包；Domain、Topic 和 QoS 的改变仍需重新生成并同步两端。
