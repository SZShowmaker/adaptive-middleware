# 应用使用的 QoS 配置

完整 src-gen 已包含各应用的默认策略与项目覆盖。应用开发人员无需在业务代码中逐项初始化 DDS QoS，仍按 [接入步骤](INTEGRATION.md) 包含 `apps.hpp`、构造 App、注册回调并启动 Runtime。

## 配置在哪里

| 随包文件 | 用途 |
|---|---|
| `metadata/qos.effective.json` | 查看默认值目录版本、每个实例与消息端点的最终 QoS、使用的策略名及警告。 |
| `metadata/model.resolved.json` | 生成时的源模型快照，保留显式覆盖；省略字段的有效值看 qos.effective.json。 |
| `metadata/routes.json` | 查端点键、Topic、模板和最终消息策略。 |
| `generated/qos.hpp` | 生成实现使用的私有 DDS 配置，不是应用公共接口。 |
| `generation-manifest.json` | 文件摘要和 `qos_defaults_version`，用于核对交付版本。 |

以上路径均相对于 src-gen 根目录。元数据文件用于查看，不是运行时配置文件；不要手改生成目录。

## 需要修改时怎么办

让维护配置工程的工程师在可视化界面选择策略模板或端点，修改所需字段，校验并重新生成 src-gen。未修改的字段使用版本化默认值。替换完整交付包后，重新编译、部署相关应用；两端策略应一起检查兼容性。

同一模板可以被多个应用实例引用；只改变一条消息时，应复制策略并为该端点选择新模板。默认值、Topic 继承、Reader/Writer 覆盖以及实例分组配置均由生成器解析，业务代码无需再次处理继承关系。

## 运行时应知道的行为

- reliable 不代表业务已处理。`try_publish()` 成功仍只表示进入 CM 队列；DDS 写入失败计入 `send_failed`。
- CM 队列与 DDS 历史缓存独立。修改 History 深度不会自动扩大 CM 队列；修改队列容量也不会扩大 DDS 缓存。
- transient_local 可让晚加入的 Reader 获取仍存活 Writer 的历史样本，具体受双方策略与容量约束。
- Deadline 配置不会替业务定时发布；当前公共 CM 尚未提供 DDS deadline/liveliness 状态通知接口。
- Data-sharing 默认关闭。启用与否受类型、内存分配、共享目录和平台条件影响；它与普通共享内存传输不同，也不意味着业务 DTO 的转换与复制被消除。
- 线程优先级、亲和性及栈设置依赖操作系统与权限。配置合法不能替代板端资源、时延和负载验证。
- 配置在构建时确定，不提供 QoS 热更新。日志 XML 的启动读取行为独立于此。

如果 `runtime.start()` 失败，记录 `Result.detail`。错误会指出失败的 DDS 端点；检查其有效策略、平台资源与权限，再反馈给配置维护者。完整生命周期与停止规则见 [API 手册](API.md)。
