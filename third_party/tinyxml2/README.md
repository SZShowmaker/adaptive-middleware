# TinyXML-2 6.2.0

来源：既有业务工程中的 include/xml/tinyxml2.hpp 和 src/xml/tinyxml2.cpp。原作者 Lee Thomason；源文件保留 zlib 许可声明，许可证同时保存于 LICENSE.txt。

本副本修改：头文件改名为 tinyxml2.h，源文件 include 路径改为同目录。将既有集成中的 XML 命名空间改为私有 amw_log_xml，避免与 Fast DDS 或业务自带 XML 解析器符号冲突。公共日志 API 不暴露 XML 类型，不需要系统安装 XML 库。

升级时同时替换头文件和实现，核查许可及日志 XML 严格校验测试；不要依赖 DDS 内部的 XML 库符号。
