# `deepmind-dynamic/vqfree-xm` 配置与避坑指南

当你使用导师提供的 `--xm_resource_alloc=deepmind-dynamic/vqfree-xm` 来获取此配额池的 TPU 资源时，**必须**严格遵守以下规范。这些规范汇总自 `projects.md` 与 `AGENTS.md` 中的系统历史踩坑记录：

## 1. 必须强制声明 `PROD` 优先级 (Service Tier)
分配到 `vqfree-xm` 意味着你拥有该组的生产级保障配额 (guaranteed PROD capacity)。
- **规则**：在 `xm_launcher.py` 或打包脚本的 `xm.JobRequirements()` 中，**必须显式定义** `service_tier=xm.ServiceTier.PROD`。
- **如果不做**：XManager 默认会以低优先级 (`BATCH` 或 `FREE`) 提交任务。导致的结果是，尽管 quota 池里有机器，Borg 也会拒绝你消耗 PROD quota，导致任务在 UI 上一直卡死在 `awaiting resources`。

## 2. 严禁使用极小的 TPU 拓扑切片 (如 `v6e-8`)
`deepmind-dynamic` 是大规模生产队列，其内部资源碎片管理非常严格。
- **规则**：申请 `v6e` 等资源时，**最低请使用 `v6e-16` (4x4) 或更大尺寸切片**。
- **如果不做**：强行分配 `v6e-8` (2x4) 极大概率触发 Borg Admission Controller 的秒拒，XManager 前端不会有任何日志或堆栈，状态直接变成无前兆的 `FAILED`。

## 3. 必须使用 Bazel 原生打包 (禁止 GCP Python Container)
- **规则**：提交该队列必须使用原生 `xm_abc.Borg` 和 Bazel 打包（例如设置 `package_mode="bazel"`）。
- **如果不做**：`deepmind-dynamic` 并没有绑定独立的 GCP (Google Cloud) 项目。如果使用 `xm.python_container`，它会尝试请求 Cloud Build，当场抛出 `No project set for pool_name: deepmind-dynamic` 异常。

## 4. 状态栏 "RUNNING" 其实是“排队中”
在 XManager 控制台中，任务刚刚成功投递给该 PROD allocator 后，状态会显示为 `RUNNING`。请注意，这**并不代表**你的代码已经开始运行。此时它处于纯粹的排队等卡 (PENDING) 状态，直至分配到物理节点并拉取完镜像，才真正开始产生运算和日志。
