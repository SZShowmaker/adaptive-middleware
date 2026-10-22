# 浏览器回归数据

`sample-types.cmtypes.json` 是独立编写的通用测试数据，不来源于业务头文件或用户项目。包含 22 个结构体：sample.Item → sample.Batch → sample.Message 的嵌套数组链、两个外层引用和 17 个简单指标类型。

`browser_type_search.py` 和 `browser_workspace.py` 用它检查类型名/说明/字段搜索、依赖跳转、结构预览和类型库滚动；工作台测试再增加类型至 203 项检查布局。测试运行不需要使用者的业务文件，数据不自动导入产品。
