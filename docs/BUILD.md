# 编译库和运行样例

本文假设已按 [环境准备](GETTING_STARTED.md) 配好 SDK、Java 和 Gen。所有命令从中间件仓库根目录执行，除非另有说明。

生成的 C++ 通常可以用于不同目标平台编译，但**编译器、SDK 和运行平台必须一致**。不要把 Linux .so 用于 Windows，也不要把 x86_64 库链接到 ARM 程序。

## 1. Linux 本机：编译并运行 demo

```bash
./amw build --demo
ctest --test-dir out/build/native --output-on-failure
```

该命令会先生成 demo，再编译 CM、Fast DDS 绑定、生成接口和两个可执行程序。默认 Debug，构建结果在 out/build/native。CTest 检查本运行库的队列和生命周期等行为，它不等于两个真实 DDS 进程已经通信。

在终端 A 启动接收者：

```bash
./out/build/native/amw_consumer monitor 20
```

在 20 秒内打开终端 B 启动发送者：

```bash
./out/build/native/amw_producer camera_front 900
```

两个终端都位于仓库根目录。接收端退出时应显示 frames、health 大于 0，invalid 为 0；发送端应显示 failures 为 0。数量会受启动顺序、发现时间和运行时长影响，不要求两端计数完全相同。

monitor 与 recorder 订阅 camera_front 的输出；rear_monitor 订阅 camera_rear。要验证后摄实例，双方实例名一起换成对应名称。类型相同但来源实例不同，默认就不会收到数据。

## 2. Linux：编译自己的生成工程

前提：已按 [界面指南](QUICKSTART_GUI.md#7-保存业务源配置) 保存 local/projects/vehicle/project.cm.json 及其引用文件。

```bash
./amw build --project local/projects/vehicle/project.cm.json --output out/delivery/vehicle/src-gen --build-dir out/build/vehicle --build-type Release
```

这是编译通信库和生成接口，不会替你编写业务 main。自己的契约不要加 --demo，因为仓库样例 main 只认识 demo 中的类型和接口。如何构建自己的可执行程序见 [业务接入](INTEGRATION.md)。

## 3. Windows x64：MSVC 构建

先按生成环境指南准备三平台 SDK 并生成完整交付包；本节脚本固定构建 Release。使用 Developer PowerShell for VS 2022，在仓库根目录执行：

```powershell
.\amw.ps1 generate
.\tools\build_windows.ps1 -Demo
```

脚本使用交付包中的 Windows SDK。构建脚本会查找 VS C++ 工具、设置 x64 环境，调用 CMake/Ninja 并运行 CTest；它读取已有生成目录，不会替你执行代码生成。默认输出 `out/build/windows`。

在两个终端设置 DDS DLL 路径，然后分别运行接收和发送程序：

```powershell
$env:PATH = "$PWD/out/delivery/demo/src-gen/dependencies/windows-x64/bin;$env:PATH"
.\out\build\windows\amw_consumer.exe monitor 20
```

另一终端使用同样的 PATH，再执行：

```powershell
.\out\build\windows\amw_producer.exe camera_front 900
```

编译自定义契约时先生成，再显式传入目录，不加 -Demo：

```powershell
.\amw.ps1 generate --project local/projects/vehicle/project.cm.json --output out/delivery/vehicle/src-gen
.\tools\build_windows.ps1 -GeneratedDir out/delivery/vehicle/src-gen -BuildDir out/build/windows-vehicle
```

默认 CM 是静态 .lib，Fast DDS 若来自动态 SDK，运行时仍需要对应 DLL。CM 的动态库构建可通过 CMake BUILD_SHARED_LIBS 设置，但当前验证基线是静态 CM，动态产物需另行验证。不要将 Debug SDK 与本节的 Release 构建混用。

脚本当前使用 VS 检测到的工具位置，不接受单独指定 MSVC 版本的参数；特殊工具链选择需自行配置 CMake。脚本执行策略、路径字符等问题见 [排错指南](TROUBLESHOOTING.md)。

## 4. 应用端 ARM64 / Windows / Linux 构建

交付包独立构建、可配置 ARM 工具链路径、安装运行依赖的完整步骤见 [通用接入手册](app-guide/INTEGRATION.md)。应用只需要完整 src-gen，不再另找 AMW 和 DDS 安装目录。

维护者若要交叉编译仓库 demo，在仓库根目录先生成，再执行：

```bash
./amw generate
cmake -S . -B out/build/arm \
  -DCMAKE_TOOLCHAIN_FILE="$PWD/out/delivery/demo/src-gen/toolchains/aarch64-linux.cmake" \
  -DAMW_TOOLCHAIN_ROOT=/path/to/aarch64-toolchain \
  -DAMW_COMPILER_PREFIX=aarch64-none-linux-gnu \
  -DAMW_GENERATED_DIR="$PWD/out/delivery/demo/src-gen" \
  -DAMW_BUILD_DEMO=ON -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build out/build/arm --parallel 4
```

本机/ARM/Windows 使用不同构建目录。编译器须匹配包内平台声明。上板运行仍需单独验证。

## 5. 独立维护运行库

仓库仍保留 CMake install 与日志独立构建，供中间件自身维护、已有 SDK 使用方和模块验证。新应用交付使用完整 src-gen，不再要求开发者自行安装中间件 SDK。

## 独立构建日志与时间模块

仅需要终端日志或计时的程序，可用 `-DAMW_BUILD_CM=OFF` 构建和安装基础库，无须 DDS。完整命令、XML 和外部消费示例见 [日志与时间工具](app-guide/LOGGING.md)。默认构建仍包含 CM 和 Fast DDS 绑定。
