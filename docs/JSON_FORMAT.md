# 如何编写消息类型文件（JSON v1）

这份文档面向需要为自己的 App 定义收发数据的开发者。你不需要先掌握 DDS 或 IDL；先列出“一条消息中有哪些字段”，再用下面的格式把它们写出来即可。

**类型文件用来描述数据结构。** 例如“车速是一个浮点数，单位为 m/s”，写在类型文件中；某一时刻的车速 `12.5`，由业务程序在运行时填写并发送。配置工具根据类型文件生成 C++ 数据类型和通信代码。

建议按顺序阅读前五节，完成自己的第一份文件。工程和网络配置放在第八节，需要时再查。

## 1. 从只有两个字段的消息开始

假设你的 App 要发送车辆状态，每条消息包含：

| 业务含义 | 字段名 | 选择的类型 |
|---|---|---|
| 车速，单位 m/s | speed | float32，单精度浮点数 |
| 制动是否激活 | brake_active | bool，布尔值 |

新建一个 UTF-8 文本文件，命名为 `vehicle.cmtypes.json`，完整内容如下，也可以直接复制仓库中的 [vehicle.cmtypes.json](../examples/type-guide/vehicle.cmtypes.json)。文件名可以更换，建议保留 `.cmtypes.json` 后缀，方便识别。

```json
{
  "format_version": 1,
  "types": [
    {
      "id": "vehicle.VehicleState",
      "version": "1.0.0",
      "kind": "struct",
      "description": "车辆当前状态",
      "fields": [
        {
          "id": 1,
          "name": "speed",
          "type": "float32",
          "unit": "m/s",
          "description": "车辆行驶速度"
        },
        {
          "id": 2,
          "name": "brake_active",
          "type": "bool",
          "description": "true 表示制动已激活"
        }
      ]
    }
  ]
}
```

可以把这个定义理解为下面的 C++ 结构体。这里只说明数据含义，实际生成的类名会包含版本号。

```cpp
struct VehicleState {
    float speed;
    bool brake_active;
};
```

各个配置项的含义如下：

| 配置项 | 怎么填写 |
|---|---|
| 最外层的 format_version | 当前固定填数字 `1`，表示工具使用哪一版 JSON 格式。 |
| types | 本文件定义的类型列表。可以只定义一个类型，也可以定义多个。 |
| 类型的 id | 你为类型起的名称，例如 `vehicle.VehicleState`。`vehicle` 用来区分业务领域，`VehicleState` 表示车辆状态。这个点号不代表文件路径。 |
| 类型的 version | 当前类型的版本号，用字符串表示，例如 `"1.0.0"`。第一次定义可以从它开始。 |
| kind | `"struct"` 表示结构体；另一种选择是枚举 `"enum"`，见第四节。 |
| fields | 结构体包含的字段列表，至少一个字段。 |
| 字段的 id | 当前结构体内的字段编号。建议从 `1` 开始分配，每个字段一个不同的编号。它不是业务数据中的目标 ID。 |
| name | 字段名称，会成为生成 C++ 结构体中的成员名。 |
| type | 字段的数据类型。基础类型直接写字符串，数组、列表等用一个 JSON 对象描述，见第二节。 |
| unit | 可选，说明单位，例如 `"m/s"`。工具不会据此换算数值。 |
| description | 可选，说明用途；可以写中文。类型和字段都可以带这个说明。 |

除了 `unit`、`description`，上面示例中的配置项均为必填。结构体必须写 `fields`；枚举则改为写 `enumerators`。

## 2. 如何为每个字段选择类型

先按业务含义选择类型，再考虑大小和上限。下面都是字段的 `type` 写法，不是完整文件；使用时放进 `fields` 中某个字段的 `type` 位置。

### 单个数值或开关

| 需求 | type 写法 | 生成的 C++ 类型 |
|---|---|---|
| 是否有效、是否触发 | `"bool"` | bool |
| 无符号整数 | `"uint8"`、`"uint16"`、`"uint32"`、`"uint64"` | uint8_t、uint16_t、uint32_t、uint64_t |
| 有符号整数 | `"int8"`、`"int16"`、`"int32"`、`"int64"` | int8_t、int16_t、int32_t、int64_t |
| 一般的速度、距离、角度 | `"float32"` | float |
| 需要更高数值精度 | `"float64"` | double |

整数名称中的数字表示位宽。根据业务范围选择，例如 uint8 可表示 0～255，uint16 可表示 0～65535。不能写 `"int"`、`"float"` 或 `"double"`，工具只接受表中明确列出的名称。浮点样本目前不能包含 NaN 或正负无穷。

### 字符串：长度会变，但要约定最大长度

例如传感器名称：

```json
{
  "id": 3,
  "name": "sensor_name",
  "type": { "kind": "string", "max_length": 32 }
}
```

生成的成员是 `std::string`，允许空字符串，最多 32 字节。上限按 UTF-8 编码后的字节数计算，因此 32 字节不等于 32 个汉字。发送超长字符串时会被校验拒绝，不会自动截断。

### 定长数组：每条消息都有固定数量的元素

例如三维坐标始终有 x、y、z 三个数：

```json
{
  "id": 4,
  "name": "position",
  "type": { "kind": "array", "element": "float32", "length": 3 },
  "unit": "m",
  "description": "依次为 x、y、z；坐标系由业务协议约定"
}
```

生成的成员是 `std::array<float, 3>`。`element` 说明每个元素是什么类型，`length` 说明固定有多少个元素。工具不会自动理解坐标顺序、坐标系或正负方向，这些含义需要写在说明中，由收发双方共同遵守。

### 变长列表：每条消息的元素数量可能不同

例如一组测量值，每次可能有 0～16 个：

```json
{
  "id": 5,
  "name": "measurements",
  "type": { "kind": "sequence", "element": "float32", "max_length": 16 }
}
```

生成的成员是 `std::vector<float>`。它的实际长度可以为 0，也可以小于或等于 16；`max_length` 是允许的最大元素个数，不是初始化时必须填满的数量。超过上限会被拒绝，不会自动丢掉后面的元素。

数组和列表的区别是：`array` 的长度固定，`sequence` 的长度可变。两者都必须给出边界。上限应根据业务最大需求确定，还要考虑消息大小和队列容量；填很大的上限并不意味着运行时资源一定够用。

### 已经定义过的结构体或枚举

如果另一个类型已经定义为 `perception.Object`、版本为 `1.0.0`，使用它时写：

```json
{
  "id": 6,
  "name": "nearest_object",
  "type": { "ref": "perception.Object", "version": "1.0.0" }
}
```

`ref` 表示“使用这个名字的类型”，`version` 指定使用哪一版。它们必须与类型定义完全一致。定义可以在同一个文件中，也可以在另一个已加入工程的类型文件中；工具不会根据名字自动查找或下载文件。

## 3. 完整例子：一帧感知结果包含多个目标

假设每帧需要发送帧号、传感器名称和目标列表；每个目标包含目标编号、三维位置和类别。可按下面的层次定义：

```text
perception.Frame：一帧感知结果
├── frame_id：帧号
├── sensor_name：传感器名称
└── objects：0～128 个 perception.Object
    ├── object_id：目标编号
    ├── position：3 个坐标值
    └── category：perception.Category 枚举
```

下面是一份可以完整保存为 `perception.cmtypes.json` 并导入的文件，仓库中也提供了可直接使用的 [perception.cmtypes.json](../examples/type-guide/perception.cmtypes.json)：

```json
{
  "format_version": 1,
  "types": [
    {
      "id": "perception.Category",
      "version": "1.0.0",
      "kind": "enum",
      "description": "目标类别",
      "enumerators": ["Unknown", "Vehicle", "Pedestrian"]
    },
    {
      "id": "perception.Object",
      "version": "1.0.0",
      "kind": "struct",
      "fields": [
        { "id": 1, "name": "object_id", "type": "uint32" },
        {
          "id": 2,
          "name": "position",
          "type": { "kind": "array", "element": "float32", "length": 3 },
          "unit": "m",
          "description": "车体坐标系 x、y、z；x 向前，y 向左，z 向上"
        },
        {
          "id": 3,
          "name": "category",
          "type": { "ref": "perception.Category", "version": "1.0.0" }
        }
      ]
    },
    {
      "id": "perception.Frame",
      "version": "1.0.0",
      "kind": "struct",
      "description": "单帧感知结果",
      "fields": [
        { "id": 1, "name": "frame_id", "type": "uint64" },
        {
          "id": 2,
          "name": "sensor_name",
          "type": { "kind": "string", "max_length": 32 }
        },
        {
          "id": 3,
          "name": "objects",
          "type": {
            "kind": "sequence",
            "element": { "ref": "perception.Object", "version": "1.0.0" },
            "max_length": 128
          }
        }
      ]
    }
  ]
}
```

注意三个地方：

- `types` 中定义了三个类型，App 的一条输出只需选择 `perception.Frame`。其中使用到的 Object 和 Category 会随它一起生成，不需要为每个类型单独建立输出。
- `objects` 的 `max_length: 128` 表示最多 128 个目标，不是 128 字节。业务程序填入多少个目标，就发送多少个；没有目标时可以发送空列表。
- 配置项 `"id": 1` 是字段编号；名为 `object_id` 的成员才保存运行时的目标编号。不同结构体可以各自从字段编号 1 开始。

生成后，业务代码可以这样填充数据（需要包含生成的 `types.hpp`）：

```cpp
amw_generated::perception_Frame_v1_0_0 frame;
frame.frame_id = 100;
frame.sensor_name = "front_camera";

amw_generated::perception_Object_v1_0_0 object;
object.object_id = 7;
object.position = {12.5f, -0.3f, 0.0f};
object.category = amw_generated::perception_Category_v1_0_0::Vehicle;
frame.objects.push_back(object);
```

这时 `frame` 中有一个目标。把它交给生成 App 类中对应的发布接口即可；发布接口名称取决于你在界面中填写的输出端口和消息名，见 [README 中的接入示例](../README.md#接入自己的应用)。

## 4. 命名、编号和枚举有什么规则

**名称。** 类型名可以用点分层，例如 `vehicle.VehicleState`；每一段以及字段名、枚举项都使用英文字母开头的字母、数字、下划线。不要使用中文名称、空格、连字符、连续两个下划线或 C++/IDL 保留字。中文含义写在 `description` 中。也不要仅靠大小写区分两个名称；校验器会拒绝部分名称冲突，生成器也有命名限制。

**字段编号。** 字段 `id` 在同一个结构体内必须唯一，合法范围是 0～268435455，建议从 1 开始。字段换了排列位置仍应保留原编号；不要因为在中间插入新字段就给后面的字段重新编号，也不要把已删除字段的编号立即用于另一种含义。保留编号有助于维护协议，但不等于本版本支持新旧结构体自动互通。

**枚举。** 示例中的 Unknown、Vehicle、Pedestrian 分别对应数值 0、1、2，由列表顺序决定。当前不能指定自定义枚举数值。调整顺序会改变原有含义；后续新增或修改枚举要发布新的类型版本。枚举可以作为字段使用，App 的完整消息输出则必须选择结构体类型。如果只想发送一个枚举，也应把它放进一个结构体中。

## 5. 写好后如何导入、检查并生成代码

1. 在仓库根目录运行 `./amw gui`，打开提示的本地网址。首次使用先按 [README](../README.md) 配置 SDK 和生成器。
2. 点击“新建工程”，填写工程 ID（本例使用 `perception_project`）；点击“导入类型 JSON”，选择自己编写的 `.cmtypes.json` 文件，在预览中确认后点击“应用”。有跨文件引用时，把相关类型文件一并导入。
3. 添加发送 App，在它的“增加输出”中填写服务端口和消息名，并选择刚导入的结构体类型。例如选择 `perception.Frame`。
4. 添加接收 App，在“选择输入”中选中发送方的输出，并勾选要接收的完整消息。这里勾选 Frame 就会接收完整的目标列表，不能只勾选 Frame 内部的某个字段。
5. 点击“校验”。导入时能显示出来，只说明完成了读取和预览，不代表已经通过所有类型、连接和部署检查。
6. 校验通过后点击“生成 src-gen”。默认产物位于 `out/delivery/perception_project/src-gen/`，页面提前显示完整路径。点击“保存草稿”后，源配置保存在 `out/editor/perception_project/`。

也可以在保存后用命令行检查和生成整个工程：

```bash
./amw validate --project out/editor/perception_project/project.cm.json
./amw generate --project out/editor/perception_project/project.cm.json
```

`--project` 接收的是**工程入口文件**，不能把 `perception.cmtypes.json` 直接传给它；当前命令行没有单独校验类型文件的子命令。

界面导入已有的同名、同版本类型时，会替换编辑器中的原定义。修改已有类型前建议先导出工程包留存，再重新校验受影响的输出和输入。生成后的 `src-gen` 由工具维护，业务变更应修改 JSON 源文件，不要手改生成代码。

## 6. 常见问题与排查方法

| 现象或错误关键词 | 检查什么 |
|---|---|
| 文件无法解析、duplicate JSON key | JSON 不允许注释、末尾多余逗号或同一个对象中重复的键；字符串及键名必须用双引号。 |
| unknown primitive | 是否写成了 float/int 等未支持名称，应使用 float32/int32 等明确位宽的类型。 |
| unknown type/version | ref 的名字和版本是否与定义完全相同；被引用的文件是否已经导入或加入 type_files。 |
| duplicate field name、duplicate/invalid | 同一结构体中是否有重复字段名或字段编号。 |
| invalid/reserved identifier、name collision | 名称是否包含非法字符、保留字，或与其他生成名称冲突。 |
| recursive types unsupported | 是否直接或间接引用了自身；例如 A 包含 B，B 又包含 A。当前不支持这种递归结构。 |
| required / additional properties 等 schema 错误 | 是否漏了必填项，或自行增加了工具尚不认识的键。按提示路径定位对应位置。 |
| 生成成功，但 try_publish 返回 invalid_sample | 检查字符串/列表是否超长、浮点是否为非有限数、枚举是否越界，以及样本是否超过该端点的队列字节预算。 |

当前不支持无界列表、指针、map、union、optional、自定义字段默认值或自动单位转换。数组长度以及字符串/列表上限必须是 1～1048576 的整数；这是配置合法范围，不是推荐的业务容量。实际字符串和列表仍允许为空。

`sequence` 不能直接以 `array` 作为元素；可以像感知示例那样，先把数组放进一个具名结构体，再建立该结构体的列表。多维定长数组可以通过嵌套 `array` 表达。

## 7. 消息结构变化后怎么办

以下三类版本含义不同：

| 版本 | 含义与修改时机 |
|---|---|
| format_version | 本工具的 JSON 格式版本，目前固定为 1；新增一个业务字段不需要改它。 |
| 类型的 version | 业务数据结构的版本。字段、边界、枚举含义或单位发生变化时，应评审并发布新版本。 |
| 服务接口的 version | 一组对外消息的接口版本。改变对外消息约定时需要一起评审，不能只检查类型文件。 |

例如将 `perception.Object` 从 `1.0.0` 改为 `1.1.0` 后，引用它的 Frame 定义中的 `ref/version` 也要更新，并评审 Frame 自身及其服务接口的版本。版本号不会自动沿引用关系更新。

当前版本的中间件按相同通信定义互通：底层类型名称包含完整类型版本，DDS Topic 名称包含服务接口版本。**把版本改为 1.1.0 并不意味着它会自动兼容 1.0.0。** 需要同步更新有关 App 的配置，重新生成、编译，并验证收发双方。

## 8. 类型文件、工程文件和部署文件的关系

写类型文件只解决“消息长什么样”。“谁发、谁收”和“用哪个实例、哪些网络参数”由另外两层配置解决。使用界面时，这些文件可以由工具保存，不必一开始全部手写。

| 文件 | 回答的问题 | 示例 |
|---|---|---|
| 类型文件 | 一条消息包含哪些数据、各是什么类型？ | [messages.cmtypes.json](../examples/demo/types/messages.cmtypes.json) |
| 工程入口文件 | 加载哪些类型文件？有哪些 App、服务接口和消息连接？ | [project.cm.json](../examples/demo/project.cm.json) |
| 部署文件 | 每个 App 有哪些运行实例？输入绑定到谁？网络和队列怎样配置？ | [deployment.json](../examples/demo/deployment.json) |
| 界面导出或 src-gen 根目录附带的 .amw.json | 如何将类型、逻辑工程和部署一起保存、传给别人，再用界面打开？ | 使用“导出工程包”，或成功生成后的 src-gen/<工程ID>.amw.json。 |

工程入口包含 `format_version`、`type_files`、`deployment_file` 和 `model`。`type_files` 是类型文件路径列表，`deployment_file` 是部署文件路径；相对路径都以工程入口文件所在目录为起点。类型跨文件引用时，相关文件都应列在 `type_files` 中。`.amw.json` 工程包的顶层是 `types/project/deployment`，与命令行入口的格式不同。

`model` 中包含 `format_version`、`project_id`、`service_interfaces`、`apps`、`connections`：

- `service_interfaces` 将对外输出的消息组织成服务接口。接口的 `events` 是可发布、可订阅的消息列表；每条消息有编号、名称和结构体类型引用。Event 编号为 1～65535，在所属服务接口内唯一，与结构体内部的字段编号无关。
- App 的 `provides` 声明它提供的服务端口；`requires` 声明它使用的服务端口，并列出需要接收的 Event 编号。
- `connections` 用 `from.app/provided` 和 `to.app/required` 连接两端。一个输入端口只能选一个来源，一个输出端口可以供多个 App 订阅。

部署文件包含 `format_version`、`binding`、`transport`、`policies`、`instances`。当前 `binding` 只能是 `fastdds`。一个 App 定义可以部署成多个实例；每个实例在 `provides` 中为输出端口分配服务实例名，在 `requires` 中为输入端口指定来源实例和输出端口。这样，同一种消息类型也能区分前摄像头与后摄像头。

常用网络和策略配置如下：

| 配置项 | 含义 |
|---|---|
| transport.domain | DDS Domain 编号，0～232；需要通信的双方应配置一致。 |
| transport.shared_memory | 是否同时启用普通共享内存传输；最终使用哪条传输路径仍取决于双方运行条件。 |
| transport.interface_address | 要使用的本机网卡 IPv4 地址；空字符串表示不在此处限定网卡。 |
| transport.peers | 初始发现对端的 IPv4 地址列表。 |
| policy.queue_samples / queue_bytes | 本中间件端点队列的样本数和估算字节数上限，两项同时生效。 |
| policy.overflow | discard_oldest：丢弃队列中最旧数据；reject：拒绝新数据。 |
| policy.reliability | best_effort 或 reliable，分别表示尽力传输与 DDS 可靠传输。可靠传输不等于对端业务已执行。 |
| policy.durability | volatile 或 transient_local；后者可由仍存活的 Writer 为晚加入 Reader 提供历史样本，具体受历史配置等条件限制。 |
| policy.history_depth | DDS 历史缓存深度，与中间件自己的工作队列是两层配置。 |
| policy.max_blocking_ms | 底层可靠写入允许的最大阻塞时间，单位毫秒。 |

部署的 `policies` 中保存具名策略，每个实例通过 `policy` 选择它；还可用 `event_policies` 按 `端口名.消息名` 为单个端点选择另一策略。比如 Reader 要求 reliable 而来源 Writer 为 best_effort，校验会拒绝该组合。

同一生成工程共用一组 transport 配置，部署变更需要重新生成、编译。不同设备若要限定各自不同的网卡地址，需要分别生成相应部署配置，同时保持用于互通的类型、服务和实例约定一致。队列字节统计不等于进程总内存，DDS 缓存和其他对象也会占用内存。

需要核对全部必填项时，可查看 [类型 schema](../schemas/types.schema.json)、[工程 schema](../schemas/project.schema.json) 和 [部署 schema](../schemas/deployment.schema.json)。这些文件供工具做结构校验，类型引用、连接等规则还由公共校验器检查。运行时行为见 [RUNTIME.md](RUNTIME.md)，界面逐步操作见 [QUICKSTART_GUI.md](QUICKSTART_GUI.md)。

0.2 的交付根目录为 src-gen，内部 generated/ 保存接口，metadata/ 保存模型和路由。JSON 格式保持 v1；交付布局变化不改变类型/服务契约。


## 9. QoS 默认值与显式覆盖

策略字段现在可省略；`policies` 中的一份空对象就是可用的默认策略。新增可选 `policy.dds`，按 `topic`、`writer`、`reader` 保存覆盖；部署和实例的可选 `qos` 按 `participant`、`publisher`、`subscriber` 保存分组覆盖。现有七个公共策略字段仍可读取，详细优先级见 [QoS 指南](QOS.md)。

下面是**策略对象片段**，放在部署的 `policies` 中，不是完整部署文件：

```json
{
  "defaults": {},
  "reliable_state": {
    "dds": {
      "topic": {
        "reliability.kind": "reliable",
        "durability.kind": "transient_local",
        "history.depth": 3
      },
      "writer": {
        "publish_mode.kind": "asynchronous"
      }
    }
  }
}
```

带点号的键是完整字段名，不是嵌套对象。时间使用 `{"seconds": 1, "nanoseconds": 0}` 或 `"infinite"`；支持无限的资源上限使用 `"unlimited"`；流量控制器名称 `"default"` 由生成器映射为 SDK 默认控制器，不需要用户知道内部字符串。

完整可运行输入见 [QoS 示例工程](../examples/qos/project.cm.json)及其 [部署文件](../examples/qos/deployment.json)。源模型只需保留覆盖；生成包的 `metadata/qos.effective.json` 才是包含全部默认值的最终策略快照。不可用字段会在导入/校验时拒绝，不能用手写 JSON 绕过界面限制。
