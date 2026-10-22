# 环境准备与首次交付

本页面向维护配置和生成交付包的工程师。应用开发者拿到完整 src-gen 后，直接阅读 [随包接入手册](app-guide/INTEGRATION.md)，无需准备生成环境。

## 1. 维护者需要准备什么

将团队提供的仓库地址 clone 到自己的工作区，然后进入 adaptive-middleware 目录。后续操作都在该目录执行；不要求固定的用户名或绝对路径。Git 目录约定见 [团队协作说明](CONTRIBUTING.md)。

- Git、Python 3.10+（含 venv/pip）、requirements.txt 中的 jsonschema、浏览器。
- 编译中间件时准备 CMake 3.22+、C++17 编译器及 make 或 Ninja；默认 Linux SDK 对应 GNU 11.x。
- Fast DDS-Gen 4.3.0、JDK 17、开发机 C/C++ 预处理器。
- 三套共享库 SDK：Linux x64、ARM64 Linux、Windows x64，均为 Fast DDS 3.6.2.0、Fast CDR 2.3.6 和 foonathan_memory，包含头文件、库、可移动的 CMake 配置及许可。
- SDK 依赖的额外非系统共享库及许可。例如本机 SDK 启用了 OpenSSL，需要把匹配的 libssl/libcrypto 一并提供。

SDK 和 Gen 继续由独立的 fastdds-build-kit 构建或由团队提供。本仓库只消费这些产物，不下载第三方源码或联网构建。生成机可以是 Linux，包内同时携带 Windows 和 ARM SDK；生成机不需要用这两个目标的编译器执行代码生成。

## 2. 配置本机路径

在仓库根目录首次准备（已有 config.local.json 时不要覆盖）：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
test -e config.local.json || cp config.example.json config.local.json
```

以上安装只涉及 Python 依赖，不会下载 SDK 或 Gen。已有配置会保留；首次复制后须编辑 config.local.json，把占位路径替换为实际安装路径。不要将个人路径写回 config.example.json。

下面是完整配置示例，所有占位路径都必须换为实际目录或文件：

```json
{
  "generator_jar": "/path/to/fastddsgen.jar",
  "java": "/path/to/jdk-17/bin/java",
  "delivery_sdks": {
    "linux-x64": {
      "sdk_prefix": "/path/to/sdk/linux-x64",
      "compiler_id": "GNU",
      "compiler_major": 11,
      "extra_files": {
        "lib/libssl.so.3": "/path/to/openssl/libssl.so.3",
        "lib/libcrypto.so.3": "/path/to/openssl/libcrypto.so.3",
        "share/openssl/LICENSE": "/path/to/openssl/LICENSE"
      }
    },
    "linux-arm64": {
      "sdk_prefix": "/path/to/sdk/linux-arm64",
      "compiler_id": "GNU",
      "compiler_major": 9
    },
    "windows-x64": {
      "sdk_prefix": "/path/to/sdk/windows-x64",
      "compiler_id": "MSVC",
      "compiler_major": 19
    }
  }
}
```

`compiler_id/compiler_major` 是维护者对 SDK 工具链的声明，构建时检查消费者的编译器；主版本匹配仍不能替代 ABI/sysroot 的实际验证。Windows 首批支持 Release /MD SDK。请提供与团队工具链匹配的 SDK，不能只修改声明绕过检查。

`extra_files` 是相对 SDK 根目录的目标路径到本机来源文件的映射，不能覆盖 SDK 已有文件，必须随附额外依赖的许可。没有额外依赖时可省略它。是否完整应通过安装后运行和动态依赖检查验收，doctor 不会自动解析所有 DLL/ELF 间接依赖。

相对来源路径以本地配置文件所在目录解析；配置被 Git 忽略。工具链本身不放进 src-gen，ARM 编译器路径在应用构建时指定，见 [接入手册](app-guide/INTEGRATION.md)。

Windows 生成机使用 Python 虚拟环境和 Developer PowerShell，配置路径可使用 `C:/...`。命令入口换成 `.\amw.ps1`。原生 Windows Python/Java/浏览器全链路尚未完整验收；Windows 消费交付包的 C++ 构建另行记录。

## 3. 检查并生成

在仓库根目录：

```bash
./amw doctor
./amw validate
./amw generate
./amw gui
```

doctor 检查三套 SDK 的声明版本、主要库架构、关键 CMake/许可文件和 Gen 版本。validate 输出 demo 的 3 个类型、2 个 App、5 个实例。generate 成功后输出完整目录路径，默认是 `out/delivery/demo/src-gen/`。

包内应有 generated、runtime、dependencies、config、metadata、guide，以及 demo.amw.json、CMakeLists.txt 和 generation-manifest.json。缺少平台、版本/架构不匹配或文件被手改会报错并保留旧包；修正配置后重试，不删除清单绕过保护。

GUI 启动后打开终端显示的网址（默认 http://127.0.0.1:8765）。在界面新建消息类型或导入 JSON、配置 App 及完整消息连接，点击“生成 src-gen”，默认按工程 ID 写入 `out/delivery/<工程ID>/src-gen/`（demo 为 `out/delivery/demo/src-gen/`），页面会提前显示完整路径。回到终端 Ctrl+C 停止本地服务。

下一步按 [GUI 操作指南](QUICKSTART_GUI.md) 配置自己的项目，或按 [交付说明](INTEGRATION.md) 将同一份完整目录交给每位 App 开发者。


## 4. 常见部署问题

- 缺少 venv/pip、CMake、编译器或 Java：先用所在 Linux 发行版的软件包管理器准备对应工具，确认命令在 PATH 中。浏览器自动化用的 Playwright/Chromium 只用于测试，不是 GUI 产品依赖。
- `config.local.json` 不存在或路径仍是占位值：复制模板后填写自己的 SDK、Gen 和 Java 路径；已有配置不要覆盖。
- `doctor` 提示缺少平台或架构/版本不匹配：当前交付规则要求三套匹配 SDK，补齐或换成正确 SDK 后重试。`validate` 只检查模型，不代替环境检查。
- 生成提示未知文件或文件被手改：使用新的输出目录，或先保留业务改动并恢复受控文件；不要删除 manifest 绕过保护。

示例成功后，用界面创建自己的工程，或把业务源配置放到 local/projects/ 下。公共功能修改按 [提交约定](CONTRIBUTING.md) 审查；配置模板和正式测试应提交，本机路径、虚拟环境和生成包会被忽略。
