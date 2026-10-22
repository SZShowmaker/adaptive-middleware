# 仓库维护说明

新对话先阅读 [开发交接](DEVELOPMENT_CONTEXT.md)，核对当前分支、工作区与本次任务；交接中的后续方向不等于已经授权的新任务。

修改行为前阅读 README.md、docs/ARCHITECTURE.md、docs/JSON_FORMAT.md 和 docs/RUNTIME.md。docs/REQUIREMENTS.md 保存产品目标，docs/VALIDATION.md 记录实际验证范围，不能将需求目标当作已实现能力。

- 公共 CM 和业务消息类型保持独立于 DDS 实体；NetworkBinding 是协议实现边界。
- CLI 和 GUI 共用模型、校验和生成逻辑，修改格式时同步 schema、语义规则、示例和说明。
- 不手改 out/generated，不覆盖生成目录中的未知文件。
- 修改生命周期和队列行为时，补充有意义的失败/并发验证。
- fastdds-build-kit 是外部 SDK/生成器提供者，不在常规 CM 变更中复制或修改其源码。
- 日志/时间模块独立于 DDS；XML 仅在显式初始化时读取，只输出终端，不增加热更新或文件输出。
- vsomeip 属于后续阶段，授权前只维护路线图。
- 区分本机、Windows、交叉编译和实际板端测试，按证据记录结果。

## 文档维护要求

面向工程师的操作文档应写清前提、工作目录、具体步骤、预期产物、错误处理和下一步。先给完整可用示例，再解释术语；片段与可直接保存的完整文件要明确区分。

新增或修改命令，应核对 --help/脚本参数；新增 JSON 示例应通过真实校验；声称可编译的 CMake/C++ 示例应实际检查。不要给未实现功能编写看似可用的命令或按钮操作。

修改入口、保存路径、生成产物或支持范围时，同步 docs/README.md 导航、对应使用指南及验证记录。历史需求示例留在 REQUIREMENTS.md 并标明用途，不与当前输入模板混淆。

通用应用手册源文件位于 docs/app-guide/，生成时原样复制到 guide/，不按 App 或工程改写。公共接口、运行行为或接入方式变化时同步修订手册并编译固定示例；增删随包文件时更新生成器 GUIDE_FILES。不要把项目专用接口清单写入这份通用手册。

重要功能完成或需要中断交接时，同步 DEVELOPMENT_CONTEXT.md 的功能基线、当前能力、验证摘要与未决项；保持为可独立阅读的现状说明，不堆叠聊天流水账。

## 常用检查

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
./amw build --demo
ctest --test-dir out/build/native --output-on-failure
```

生成集成测试需要已配置的 config.local.json 和 Gen。真实网络集成用 `python3 tests/integration.py out/build/native`，建议在隔离测试网络运行。可选浏览器测试见 docs/VALIDATION.md。
