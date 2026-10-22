# 终端日志与时间工具

本章要求中间件 0.1.1 及以上，适用于提供 `amw::log`、`amw::time` 的中间件版本。日志供业务 App、CM 和后续平台模块共用；0.2 交付包将其公共源码放在 runtime/，不按每个 App 重复生成。

首版只向 **stderr** 打印，所有等级共用一个输出流。不创建日志文件、不滚动文件、不上传 DDS、不监听 XML 变化。应用可自行重定向 stderr；重定向产生的文件不由中间件管理。Fast DDS 自己的内部日志仍由其自身机制管理，不受本 XML 过滤。

## 1. 从完整示例开始

本目录的 [logging.cpp](examples/logging.cpp) 是完整程序，[logging.xml](examples/logging.xml) 是完整配置。程序自行解析 `--log-config`，再把路径传给中间件；日志库不会擅自扫描程序命令行或寻找某个固定目录。

应用初始化的核心写法：

```cpp
amw::log::Options options;
options.app_name = "camera_front";
options.config_path = "/opt/my-app/config/logging.xml";
auto result = amw::log::initialize(options);
if (!result) {
    // 输出 result.config_path 和 result.detail，再按应用启动策略处理。
}
```

上面是片段。初始化失败时没有悄悄启动默认日志；完整示例会向 stderr 报告并退出。`config_path` 必填、使用 UTF-8；可以是绝对路径，也可以是相对初始化时当前工作目录的路径。`Result.config_path` 返回解析后的绝对路径（无法解析路径时可能为空），不以可执行程序所在目录为基准。Windows 路径可写 `C:/my-app/config/logging.xml`。

`app_name` 是进程日志身份，可传部署实例 ID。App 与模块名都限制为 1～128 个 ASCII 字母、数字、下划线、连字符或点；点不能在首尾或连续出现。不要把它当作可写任意文本的消息字段。

## 2. 构建与运行

在业务目录准备完整 src-gen，并复制本手册 logging.cpp 为 main.cpp。下面是仅使用日志/时间的完整 CMakeLists.txt：

```cmake
cmake_minimum_required(VERSION 3.22)
project(log_client LANGUAGES CXX)
set(AMW_BUILD_CM OFF CACHE BOOL "Only use log/time")
add_subdirectory(src-gen)
add_executable(log_client main.cpp)
target_link_libraries(log_client PRIVATE amw::log amw::time)
amw_deploy(log_client)
```

在业务目录执行：

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel 4
./build/log_client --log-config build/config/logging.xml
```

此方式不查找 DDS。若业务同时使用通信，按 [接入指南](INTEGRATION.md) 链接 amw::app，它已传递日志和时间模块依赖。日志仍由应用显式初始化和关闭。

Windows 使用 VS 2022，构建加 --config Release；ARM 使用包内 toolchains/aarch64-linux.cmake 并指定 AMW_TOOLCHAIN_ROOT。详见接入指南。公共库可通过 BUILD_SHARED_LIBS 选择静态或动态构建。

维护者仍可在中间件仓库根目录独立验证基础库：

```bash
cmake -S . -B out/build/log-only \
  -DAMW_BUILD_CM=OFF -DAMW_BUILD_LOG_EXAMPLE=ON \
  -DCMAKE_BUILD_TYPE=Release
cmake --build out/build/log-only --parallel 4
ctest --test-dir out/build/log-only --output-on-failure
```

## 3. XML 配置逐项说明

下面是完整配置，与固定示例一致：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<logging version="1">
    <defaultLevel>INFO</defaultLevel>
    <timestamp timezone="local" precision="milliseconds"/>
    <console enabled="true" color="auto"/>
    <queue capacity="1024" maxMessageBytes="4096"/>
    <modules>
        <module name="cm" level="DEBUG"/>
        <module name="perception" level="INFO"/>
    </modules>
</logging>
```

| 项目 | 含义与默认值 |
|---|---|
| logging.version | 必须为 `1`。 |
| defaultLevel | 必填。TRACE、DEBUG、INFO、WARN、ERROR、FATAL、OFF，大小写严格匹配。 |
| timestamp | 可省略；默认本地时区、毫秒。出现时必须同时填写 timezone 与 precision。 |
| timezone | `local` 或 `UTC`；本地时区由运行环境决定，不在 XML 内定义 IANA 时区。 |
| precision | `milliseconds` 或 `microseconds`，表示显示位数，不承诺时钟实际精度。 |
| console | 可省略；默认 enabled=true、color=auto。出现时两个属性都必填。 |
| enabled | `true` 或 `false`；false 时全部过滤。 |
| color | `auto`、`always`、`never`。auto 只在兼容终端使用颜色；重定向不加颜色。Windows auto 还要求终端已启用 VT 支持。 |
| queue | 可省略；默认 capacity=1024、maxMessageBytes=4096。出现时两个属性都必填。 |
| capacity | 排队记录上限，1～65536。满时丢弃新记录，所有等级相同。 |
| maxMessageBytes | 每条消息正文的字节上限，1～65536；超出截断并标记 `[truncated]`。 |
| modules | 可省略；模块等级覆盖默认值，模块名不能重复。 |

capacity × maxMessageBytes 不超过 64 MiB；这是队列正文预算，不是整个进程内存上限。每条记录还有模块名、时间和线程等元数据，输出中的转义也可能增加长度。XML 文件上限 64 KiB。

模块采用“最具体的点分名称优先”：例如 `cm=DEBUG` 对 `cm.send`、`cm.receive` 生效，对 `cmd` 不生效；再写 `cm.receive=ERROR`，接收模块采用 ERROR。没有匹配配置则使用 defaultLevel。模块名由调用者传入，不要求在 XML 中逐个注册。

等级设 INFO 时，输出 INFO、WARN、ERROR、FATAL；设 OFF 时关闭该模块。`FATAL` 不自动退出或终止程序。没有旧项目的 ALWAYS、NOTICE、DEBUG_FP，也不接受 INFO 拼写错误后的静默降级。

未知字段、重复节点/模块、无效值、格式错误、缺失必填项都会使初始化失败。请将配置错误修好后再启动，不要把日志初始化成功与 XML 文件读取失败混为一谈。

## 4. 写一条日志

包含 `amw/log/log.hpp` 后，在初始化成功的程序中使用：

```cpp
AMW_LOG_INFO("perception", "frame_id=" << frame_id << " objects=" << objects.size());
AMW_LOG_WARN("cm.send", "queue full, endpoint=" << endpoint_name);
```

这是片段，变量由业务定义。宏有 TRACE/DEBUG/INFO/WARN/ERROR/FATAL 六种，不需要 `std::endl` 或末尾换行；一条调用自动生成一条记录。常见输出：

```text
2026-10-10T14:32:18.123+08:00 [INFO] [camera_front] [perception] [tid=4821] frame_id=42 objects=5
```

宏在调用线程先检查等级，关闭的日志不会求值正文表达式；启用时才在调用线程格式化，随后交给后台线程输出。正文格式化异常被捕获并累计 format_errors，不传出日志宏。日志调用仍可能进行内存分配和短时间互斥，不承诺硬实时或零开销。

宏是单个表达式，可用于 if/else。模块表达式会求值，不要依赖日志正文中的副作用完成业务动作。自定义 `operator<<` 里不要再次打印日志或执行 initialize/shutdown。流格式（如 std::hex）只影响这一条记录，不污染其他线程。

已有字符串可以直接提交：

```cpp
auto submitted = amw::log::write("perception", amw::log::Level::info, text);
```

`write` 返回 accepted、filtered、not_initialized、queue_full、invalid_argument 或 failed。accepted 仅表示已进入日志队列，不表示已输出。宏也返回 Submit；宏前置过滤（包括未初始化）统一返回 filtered，底层 write 才区分 not_initialized。日志不接管业务错误处理。

正文的换行、回车、制表符与控制字节被转义，避免一条记录跨行或改变终端颜色。字节上限约束日志内部的格式化缓冲和队列正文；调用者表达式自己创建的大字符串、容器或执行时间不受这个上限约束。

## 5. 初始化、运行与退出

应用应链接同一份日志库，一个进程共用一个日志会话。若多个业务 DLL/插件分别静态链接一份 amw_log，会产生各自独立状态；这种部署应统一使用同一份日志动态库，或由宿主提供日志接口。

推荐顺序：

```text
解析应用启动参数 → initialize(日志 XML)
  → 创建/启动 CM 和业务线程 → 发布订阅与业务日志
  → 停止 CM、退出业务线程 → shutdown(日志) → 程序退出
```

已初始化时再次 initialize 返回失败，不自动替换配置。修改 XML 不改变本进程等级；正常部署通过重启生效。不提供文件监视、热重载、运行中 set_level 接口。shutdown 完成后允许重新 initialize 建立新会话，主要用于测试或明确的整段生命周期重建。

初始化前和 shutdown 后的日志不会输出。初始化失败信息请由应用用 stderr 报告。CM 本身不会寻找 XML 或偷偷初始化日志；只使用已经建立的日志会话。init/shutdown 由应用控制线程负责，不在静态对象析构、信号处理器或日志格式化回调中调用。

shutdown 停止接纳新记录，并等待已接纳记录全部尝试输出；因此应先停止所有产生日志的线程。终端或管道阻塞时，日志后台线程和 shutdown 仍可能等待；后台线程不会反过来让提交者等待队列腾出空间。进程被 kill、崩溃或异常终止时可能丢失缓存；包括 FATAL 在内，首版没有同步紧急输出通道。

同进程通过本日志模块提交的记录逐条输出，不会在一条记录中拼入另一条记录的内容。多线程按实际入队顺序输出；时间在调用处采集，因此并发情况下显示时间不一定严格递增。不协调其他进程、直接 printf 或第三方库对同一终端的写入。

## 6. 队列统计与 CM 诊断

`amw::log::metrics()` 返回当前会话快照，shutdown 后仍可读取；成功开始新会话后清零。

| 字段 | 含义 |
|---|---|
| accepted | 接纳的记录数。 |
| written | 后台完整写出且 fflush 成功的记录数。 |
| dropped | 队列已满而丢弃的新记录数，包括高等级日志。 |
| output_errors | 写出或后台格式化失败次数；不在同一路径递归记录错误。 |
| format_errors | 调用侧格式化/记录构造失败次数。 |
| truncated | 已接纳且正文超长被截断的记录数。 |
| queued / queue_high_water | 当前排队数、历史最大排队数；不含正在输出的一条。 |

被等级过滤、未初始化或无效参数的调用不计入 accepted/dropped。正常 shutdown 后，accepted = written + output_errors。fflush 成功只是运行库向操作系统提交成功，不代表终端用户已经看到内容或任何文件持久化保证。应用可周期性查询 dropped，避免调试期间的过载被忽略。

CM 在 `cm.lifecycle` 记录启动失败及 DEBUG 级激活信息；`cm.send` 的后端发送失败和 `cm.receive` 的业务回调异常带端点键、Topic 与累计失败数。连续失败在第 1、2、4、8……次打印，避免每帧刷屏；完整计数仍查 CM metrics。回调异常日志不保存业务异常文本，业务可自行捕获并记录具体原因。没有默认打印每条收发消息或所有信号内容。

## 7. 时间工具

包含 `amw/time/time.hpp`，链接 `amw::time` 后可单独使用，不需要初始化日志：

| 接口 | 用途 |
|---|---|
| unix_now_ns() | 当前系统时间，Unix epoch 纳秒。用于与外部记录关联，系统校时可能使其跳变。 |
| steady_now_ns() | 本机单调时钟纳秒。只比较同一时钟域内的间隔，不当作 Unix 时间。 |
| format_timestamp(unix_ns, zone, precision) | 把系统时间格式化为带日期、时区的字符串。UTC 用 Z，本地时间用 ±HH:MM；超出平台日历范围等情况可能抛异常。 |
| now_string(zone, precision) | 格式化当前系统时间；默认本地时区、毫秒。 |
| Stopwatch::elapsed_ns()/elapsed_ms() | 从对象创建/最近 reset 起的单调耗时；纳秒为整数，毫秒为 double。 |
| Stopwatch::reset() | 重新开始计时；同一个 Stopwatch 不要在没有同步的线程间并发 reset/read。 |

示例：

```cpp
amw::time::Stopwatch timer;
// 执行需要测量的业务操作。
AMW_LOG_INFO("perception", "elapsed_ms=" << timer.elapsed_ms());
```

这些工具不负责设备时钟同步，也不会自动修改 DDS 的 SampleInfo 或消息中的采集时间。跨设备分析时延仍需明确传感器时间字段和同步方案。
