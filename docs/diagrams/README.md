# 架构图片与维护方法

仓库直接提交图片，阅读 README 或架构说明无需安装绘图工具，也不依赖 Git 平台支持 Mermaid。

| 图片 | 解决的问题 | 可编辑源文件 | 放大版本 |
|---|---|---|---|
| [生成流程](generation-flow.png) | JSON 怎么变成 IDL、src-gen，最后怎样编译为程序？ | [generation-flow.dot](generation-flow.dot) | [SVG](generation-flow.svg) |
| [组件关系](component-map.png) | build-kit、CM、日志/时间、绑定、业务进程如何关联，后续模块放哪里？ | [component-map.dot](component-map.dot) | [SVG](component-map.svg) |

PNG 用于文档预览，SVG 用于放大查看或放入设计文档。两者由同一份 DOT 源文件生成。图示描述当前 0.1.1 版本；灰色虚线框为规划内容，不代表已经实现。具体平台验证范围以 [验证记录](../VALIDATION.md) 为准。

## 修改图片

只有维护图片的人需要安装 Python 3、Graphviz 和中文字体。普通使用者生成 src-gen、构建中间件时不需要 Graphviz。

Linux（Ubuntu / Debian）可以安装：

```bash
sudo apt-get install graphviz fonts-noto-cjk
```

Windows 安装 Graphviz 后，将其 `bin` 目录加入 `PATH`，并安装 Noto Sans CJK SC 字体；重新打开终端。两个平台先执行 `dot -V`，应能看到 Graphviz 版本。

在仓库根目录修改对应 `.dot` 文件后运行：

```bash
python3 tools/render_diagrams.py
```

Windows 可使用：

```powershell
python tools/render_diagrams.py
```

脚本会更新这里的两份 PNG 和两份 SVG，输出每个文件的路径。它只绘制文档图片，不调用 DDS 生成器，也不修改业务生成目录。脚本以自身所在位置查找图片源文件，所以也支持从其他目录调用。

提交前打开 PNG 检查中文是否完整、箭头有无穿过文字、缩小后能否辨认；同时预览 README 和架构文档中的图片。把修改后的 `.dot`、对应 PNG/SVG 及相关文档一并提交，避免源码与图片不一致。

出现 `Graphviz 'dot' was not found` 时检查安装和 `PATH`；中文显示方框时检查字体安装，再重新生成。不同 Graphviz 或字体版本可能造成布局和图片字节差异，维护时应检查视觉结果。本轮图片使用 Graphviz 2.43.0 和 Noto Sans CJK SC，在 Linux 生成；未验证 Windows 绘图环境。

## 内容约定

- 生成流程保持“配置 → 校验 → 生成 → 编译 → 交付”的顺序，明确区分源码和二进制产物。
- 公共 CM 是共用运行库；图中不可将其画成每次生成的代码或独立消息转发进程。
- GUI、CLI、Java 和 Gen 属于开发环境；Fast DDS 库属于应用的构建及运行依赖。
- 新增绑定应与 Fast DDS 绑定并列；未来功能仍用虚线框，并明确写“未实现”。
- 组件关系图是职责与数据路径概览；线程切换、队列和启动停止细节查 [运行说明](../RUNTIME.md)。

生成脚本：[tools/render_diagrams.py](../../tools/render_diagrams.py)。
