# 项目交付与业务接入

从 0.2.0 开始，每个项目交付一个完整的 **src-gen/**。包内已包含生成接口、公共 CM/日志/时间源码、三个平台 DDS SDK、构建/部署规则和通用手册；应用开发者无需另行安装 AMW 或 DDS SDK。

## 维护者交付

前提：已按 [环境准备](GETTING_STARTED.md) 配好 Java/Gen 和三平台 SDK。在仓库根目录执行：

```bash
./amw doctor
./amw validate
./amw generate
```

CLI 与 GUI 默认产物都是 `out/delivery/<工程ID>/src-gen/`，demo 为 `out/delivery/demo/src-gen/`。GUI 的完整路径在生成前显示，可通过“生成位置设置”修改根目录。同一项目只生成一份完整目录，原样交给所有 App 开发者。根目录自动附带 `<工程ID>.amw.json`，供配置工作台“打开工程”恢复这次生成的类型、App、连接与部署配置；本机 SDK/生成器路径不在其中。自定义输出参数指定交付根目录本身。下面假设已按 [界面指南](QUICKSTART_GUI.md#7-保存业务源配置) 保存业务输入文件，例如：

```bash
./amw generate --project local/projects/vehicle/project.cm.json --output out/delivery/vehicle/src-gen
```

输出含 `generated/`、`runtime/`、`dependencies/`、`config/`、`metadata/`、`guide/` 和根目录 CMake/清单。缺少任一必需平台 SDK、版本/架构错误或生成失败时，不发布不完整包，保留上次成功目录。

工程输入 JSON 应单独版本管理；metadata 保存解析快照。通用手册原样附带，不按 App 改写。业务工程自行编写 main，只构造属于自己的 App/部署实例；把其他 App 的接口放在包里不会启动其他业务。

## 应用开发者接入

完整 CMake、Linux/Windows/ARM 命令、可配置工具链路径、部署和错误处理见 [通用接入手册](app-guide/INTEGRATION.md)。应用只需 add_subdirectory(src-gen)、链接 amw::app，并用 amw_deploy 部署运行依赖和默认日志配置。

收到包后先看 README.md 和 guide/。编译器、系统运行库仍需匹配包内 SDK；一个源码包支持三个目标，不表示同一个二进制跨平台运行。业务源码和构建目录放在 src-gen 外面。

## 从旧交付方式迁移

0.1 的 out/generated 目录继续保留，不自动改写。0.2 默认生成到新的 out/delivery，防止旧目录里的 src-gen 子目录与新的交付根目录混淆。

用新的完整目录替换业务引用，移除 find_package(amw) 和外部 DDS 路径，使用手册中的统一接入方式。公共 C++ API 和 App 命名保持不变；原 amw_project target 仍存在，推荐使用 amw::app。

旧包不能通过单独复制 log.cpp 或移动旧 src-gen 子目录完成升级。若显式复用旧的完整受控输出目录，生成器仍先核对原清单，确认无未知/手改文件后才整体替换。
