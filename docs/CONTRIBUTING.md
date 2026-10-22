# 团队开发与 Git 提交

先按 [环境准备](GETTING_STARTED.md) 在自己的 Linux 开发机配置依赖。本文命令在仓库根目录执行；忽略规则随仓库 clone 生效，不需要安装 hooks 或修改全局 Git 配置。

## 1. 哪些文件放在哪里

| 内容 | 位置与提交规则 |
|---|---|
| 中间件源码、GUI、生成器、schema、构建脚本 | include/、src/、ui/、tools/、schemas/、cmake/，提交。 |
| 通用示例、正式测试及其模拟数据 | examples/、tests/，提交；不能忽略整个 tests/。 |
| 文档、配置模板、依赖声明和第三方许可 | docs/、config.example.json、requirements.txt、dependencies.lock.json、third_party/，提交。 |
| 本机 SDK/Gen/Java 路径 | config.local.json 或 config.<名称>.local.json，忽略。不要改配置模板来保存个人路径。 |
| 个人业务工程、临时脚本与实验 | local/projects/、local/experiments/，忽略；需要共享的业务源文件放到独立业务仓库。 |
| 草稿、交付包、构建与验证结果 | out/，忽略。其他位置的 src-gen/ 目录也忽略；自定义输出推荐放到 out/、local/ 或仓库外。 |
| Python 环境、IDE 偏好、缓存 | .venv/、.vscode/、.idea/ 等，忽略。 |

根目录下载的 *.amw.json 也会忽略。其他业务类型 JSON 不按扩展名全局忽略，应放进 local/；正式 schema、示例和测试数据仍会显示在 git status 中。生成源码目录受清单保护，不要把个人代码写进去。

忽略不等于备份。不要依赖 out/ 或 local/ 保存唯一一份重要业务配置。`.gitignore` 也不会隐藏已跟踪源码的修改；临时修改正式源码请用独立分支或工作树管理，不使用 assume-unchanged / skip-worktree 掩盖变更。

## 2. 日常检查示例

创建个人工作目录不会改变中间件输入格式：

```bash
mkdir -p local/projects local/experiments
./amw validate
# 查看每条本机文件路径由哪条规则忽略（路径可以尚不存在）
git check-ignore -v config.local.json local/projects/my_project/project.cm.json out/editor/demo/project.cm.json
# 正常状态仅显示公共文件改动；需要查看被忽略的内容时显式加 --ignored
git status --short
git status --short --ignored
```

正式测试代码修改仍应出现在状态中。临时测试的日志、抓包、截图和输出放在 local/ 或 out/；请勿为隐藏某次实验而给具体源码文件添加忽略规则。

## 3. 提交前审查

先检查工作区、未跟踪文件，以及是否曾错误跟踪本机文件：

```bash
git status --short --untracked-files=all
git diff --check
git diff --stat
git ls-files -ci --exclude-standard
```

最后一条正常应无输出。若有输出，表示已跟踪文件与忽略规则冲突；先判断该文件是否属于公共内容。应退出跟踪的本地文件需有选择地执行 `git rm --cached <具体文件>`，这会保留工作区文件；不要批量清空索引，也不要删除真实业务数据。

根据改动范围执行 [验证记录](VALIDATION.md) 中对应检查。例如模型/生成器改动需配置 SDK 和 Gen 后运行 Python 测试；运行库改动还需构建和 CTest。类型搜索/布局改动需运行浏览器回归。

审查后仅暂存本次要交付的公共文件。下面是 Git 操作形式示例，尖括号内容需替换，不是可直接复制的命令：

```text
git add <本次确认的文件或目录>
git diff --cached --check
git diff --cached --stat
git diff --cached
```

确认新增模块、测试辅助脚本和 fixtures 一并进入提交，且没有工具安装路径、业务数据、临时结果或账号信息，再按团队约定 commit/push。`.gitignore` 不会阻止 `git add -f`，也无法判断写进正式源码或文档中的内容是否私人化，最终仍需审查差异。

## 4. 新环境与验证副本

Linux 依赖、模板复制、doctor/validate/生成步骤见 [首次部署](GETTING_STARTED.md)。所有本机路径都从 config.local.json 配置；SDK 和工具链不随源码仓库提交。当前生成完整包仍需三平台 SDK，不能把“Linux 上生成”理解成只需要 Linux SDK。

浏览器测试会启动本地服务并写草稿、生成包和截图，应在独立开发副本执行，复制该副本所需的本机配置后再串行运行。副本必须包含本次新增的公共文件；仅复制已提交的旧 HEAD 无法验证尚未提交的新功能。测试配置和产物留在被忽略的位置，具体端口与范围见 [验证记录](VALIDATION.md)。

## 5. 公开主分支与本地配置

公开源码和文档使用通用平台名称与示例路径。内部项目代号、板卡别名、实际 SDK/工具链目录、设备地址、业务消息和调试证据放在被忽略的本地配置、local/ 或 out/ 中；不要为说明“禁止提交”而在公共文件中列出真实内部名称。

发布前同时审查待提交文件名、内容和 main 可达的历史提交；仅清理工作区或添加忽略规则不会清除历史内容。历史整理是独立操作，不能靠忽略规则完成，也不能直接把个人配置分支合入 main。

已有生成包不会随文档修改自动更新。Git 忽略规则不控制 SDK/src-gen 的打包内容；交付包可能包含业务工程定义和上游 SDK 的构建信息，应按交付对象单独审查，不能将本地业务包作为公开示例上传。

## 新公开仓库的首次推送

本地 main 从当前完整源码快照开始，仅包含一条初始提交；旧 Git 数据保存在仓库外，不作为公开分支或标签携带。已有本地配置和生成物仍由忽略规则保护。

在 GitHub 新建空仓库，不自动添加 README、许可证或 .gitignore；然后在对应本地仓库根目录执行下列命令，将示例 URL 替换为自己的新仓库地址：

```bash
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```

首次推送只指定 main，不使用 --mirror，不从旧备份导入历史或分支。提交前检查 `git log -1 --format=fuller`，作者及提交者邮箱应为个人公开邮箱或 GitHub noreply 邮箱；避免全局企业邮箱进入后续提交。本地仓库配置可单独设置身份，无需修改全局 Git 配置。
