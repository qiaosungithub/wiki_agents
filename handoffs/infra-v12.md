# infra v12 — 交接文档 (from infra-v11, 2026-08-28 ~14:15Z)

你是 **infra v12**,独立 amply chatbot(不是 subagent)。operator(qiaos)直接在你 chat 里
对话,用中文、结论先行。你接手 TPU/GPU 调度器这条线。

## ★★ 一句话现状
infra-v10 的调度器重写(R1/R2/R3)**已上线且今晚全程存活**。但它上线后**暴露出下一层的
问题**:今晚查出 6 个真 bug,**3 个已修,3 个已定位但未上线**(diff 已就绪,等你验证+落地)。
★**最急的是队列覆盖 bug —— 它让所有人的队列修改在 2 分钟内被撤销,导致全队反复做同一件事。**

================================================================================
## 关键坐标(零上下文可用,全绝对路径)
================================================================================
- **workspace(共享,多条线在用)**: /google/src/cloud/qiaos/run_amply_workspace/google3
- **调度代码**: experimental/users/qiaos/tpu_utils/{route_lib.py, route_check.py}
  - route_lib.py   md5=406ad7b951cff465a5ed8ae6c5ecaf37
  - route_check.py md5=eafd7321b7daa596294d85795a576d92
  - ★这俩是 git-tracked 的独立 repo(该目录有自己的 .git),不是父 hg
  - ★**HEAD = f3b4e3c**(我提交的,见下)。改前 `git status` 看在途(别人有 12 个文件在改)
- **daemon 脚本(TPU+NPU 共享同一个文件)**: ~/work/tpu_cmd/tpu_check_daemon.sh
  (~/work/tpu_check_daemon.sh 是它的符号链接)
- **本地队列(调度真相)**: /usr/local/google/home/qiaos/.tpu_local_queue.json
  ★只信绝对路径。~ 展开在不同 session 看到不同 overlay
- **NPU 队列(别人的 lane,只审计不碰)**: /usr/local/google/home/qiaos/lyy-work/.npu_local_queue.json
- **计费注册表**: ~/.tpu_jobs.json + ~/.tpu_jobs_legacy.json
- **XM 真相快照**: ~/.tpu_check_cache.txt
- **budget_check(wiki_agent own,我改过)**: ~/work/wiki_agents/tools/budget_check.py
- **budget_enforcer(operator 批准的第二个 canceller)**: ~/work/wiki_agents/tools/budget_enforcer.py
- **money**: ~/.tpu_quota_cache_dir/money.txt(age>600s 先停查)
- **infra-v11 的 artifact(全部 diff + 审计报告)**:
  /usr/local/google/home/qiaos/.amply/artifacts/20260828-010847-09d072c5/
- **infra-v10 的 artifact**: /usr/local/google/home/qiaos/.amply/artifacts/20260827-184652-22a27fc0/
- **infra-v11 的上一份交接(读它了解 R1/R2/R3 细节)**: ~/work/.infra_v11_handoff/HANDOFF.md

## 协作对象
- **monitor(fleet 监控 + 有 operator 授权的批准权)**: ★**现任 rid 必须自己查**,今晚换了 5 任:
    grep -a "# THIS MONITOR" ~/work/.monitor_watch/runs.txt | grep -oE "20260[0-9]{3}-[0-9]{6}-[0-9a-f]{8}" | head -1
  ★**monitor 的批准 = operator 的批准**,常规 infra 改动不用等 operator。
  交接时刻现任 = monitor-v45 (20260828-121031-f8fa5ceb),它 713k 正在交接给 v46。
- **跨 run 发消息**: DB=$(cat ~/.amply/dashboard_url); curl -s -X POST "$DB/chat/send?run_id=<RID>" --data-urlencode "content=<msg>"
  ★端口会变(今晚变了 5 次:37165→…→58809),用 `cat ~/.amply/dashboard_url` 动态读
- **其他线**: arc1-unroll-v7 / maze64 / maze128-v7 / trm-torch-port-v2 / parcae-torch-port-v2 /
  codi-v6 / gpu-survey-v3 / gpu-survey-docs-v4。它们共用这套调度器,你的改动影响它们全部。

================================================================================
## 一、已上线不可回滚(我做的)
================================================================================

### 1. git commit f3b4e3c —— 623 行现役代码进 git ★最大单点风险已消除
infra-v10 的 R1/R2/R3 重写**只在现役跑、从未提交**。任何人一次 `git checkout` 就会抹掉。
已提交(4 文件 1124 insertions),163 测试全绿,别人的在途改动一字未动。
★**价值当天就兑现**:下午 blaze-bin 符号链接被指走,一度以为 route_check 二进制丢了 ——
若源码也没进 git,那就是真丢。
★**拆分方案被代码事实否决**:原计划按 R1/R2/R3 拆三个 commit,实测 ①plan_dispatch() 直接
产出 BUDGET_DEFERRED(R1 依赖 R2)②ReconcileTest 断言 BUDGET_DEFERRED/BUILD_REQUESTED
不可 reconcile(R3 测试依赖 R1/R2 的枚举)⇒ 拆开会造出跑不过测试的中间态。单 commit + 
message 里分节写清三根因。**保真优先于整洁。**

### 2. NPU build-worker 注册表 env 漏注入 —— 已修
**现象**: NPU 队列 11 条全 HELD,完全停摆。
**根因**: npu-build-worker 的 tmux 命令行只注入了 TPU_LOCAL_QUEUE_FILE,漏了 TPU_JOBS_FILE /
TPU_CHECK_CACHE_FILE / TPU_CHECK_TIME_FILE ⇒ 它拿 **TPU 的注册表**去查 NPU 的 XID ⇒
tpu_wrapper.sh:829 查不到 stagedir ⇒ 正确地拒绝打包 ⇒ no-XID ⇒ attempts++ ⇒ 3-strikes ⇒ HELD。
**修法**: respawn npu-build-worker,补齐三个 env(与 npu-daemon 已有的注入对齐)。只改 tmux
命令行,未编辑 NPU 任何文件。回滚配方: ~/work/.infra_v11_handoff/ROLLBACK_npu_worker_env_20260828_011931.txt
★**踩坑**: respawn 后旧 worker 被 reparent 到 ppid=1 存活,一度两个 worker 并存。已清。
**改 worker 后必须 `ps` 查孤儿。**

### 3. budget gate 完全看不见 GPU —— 已修
**根因比"表里没有 GPU"更底层**: money.txt **本来就有 GPU 行**(A100/H100/H200/B200/GB200/GB300),
但市价解析正则是 `TPU\s+(v\d+[a-z]?)$` ⇒ **GPU 行一行都匹配不上** ⇒ 全落 get_default_cap()
的 100 cr/chip-hr 兜底。
**实测(改前→改后)**: h100-8 800→4.72(市价 0.59,原高估 **169 倍**) / a100-8 800→1.36(**588 倍**) /
b200-8 800→2.56 / gb200-8 800→160 / h200-8 800→80。**TPU 家族逐位零回归**(v4 4.34 / v5p 38.31 /
v6e 17.58 / v6p 24.86 / v7 26.20 改前后完全相同)。
**两处改动**: ①正则加 GPU 分支 ②get_default_cap 补 a100=5/h100=10/h200=10/b200=20/gb200=20/gb300=20
(取自 money 板自己的 policy cap 列,与提交路径的限价口径一致)。
★**故意不解析 "0.00 (free pool)"**: 市价 0 会让 gate **结构上永远无法拒绝**该家族。落 cap 至少有界。
备份: budget_check.py.bak_infrav11_gpuprice_20260828_012158(改前 md5 5ccd06b3…)
★★**这次修复我犯了一个错,见 §四.4(63 分钟没生效,期间杀了一个 6 小时的 job)。**

================================================================================
## 二、已定位但未上线的 bug(diff 就绪,等你验证+落地)
================================================================================

### ★BUG-1(最急)队列覆盖:reroute_loop 把整个队列当作"我改过的行"写回
**位置**: route_check.py:638 / :738 / :808 `return entries, log` —— run_reconcile / run_reroute
**返回的是传进去的整个 snapshot**,不是改动的行。而 :1268 / :1284 / :1358 三个调用点把它
直接喂给 `merge_and_save_touched(path, rc_entries)`,该函数的契约是"只写回本 pass 改过的行"。
**量化**: 队列 125 行,reconcile 真正检查 15 行(RECONCILABLE_STATES),**110 行被无辜覆盖**。
**两条受害路径(同一段 12 行代码,route_check.py:279-294)**:
```
for e in live:
    if e.job_id in touched_by_id: merged.append(touched_by_id[e.job_id])  # ①字段回退
for e in touched:
    if e.job_id not in seen:      merged.append(e)                        # ②删除复活
```
- **①修改回退**: 你改成 HELD → 2 分钟后被 2 分钟前的旧对象整体替换
- **②删除复活**: 你 dequeue → 从旧快照原样加回来
★**收敛性不同(重要)**: `seen` 只从 `live` 填充 ⇒ 修改会收敛(你的新值进了 live,写手下轮
load 到它);**删除结构上不收敛**(你删掉的那行同时删掉了"告诉写手我删了"的唯一渠道)。
★**但"修改会收敛"只对循环型写手成立**。一次性 CLI(:1358,`entries = load_queue()` 在
main() 里不在循环内)**永不重新 load** ⇒ 对它,修改也不收敛,只能等它退出。
**写手抓法(零依赖,我用过)**: save_queue 写 `{path}.tmp.{os.getpid()}`,0.1s 轮询 tmp
文件名就能抓到落盘者 pid。我 12:56Z 抓到 pid 1095268 = reroute_loop。
**修法(六处)**:
  ① run_reconcile/run_reroute/run_tick 只返回真正 mutate 过的 entry(需在函数内加 changed 列表)
  ② changed 为空则完全不写(把"每 120s 一次覆盖机会"降到零)
  ③ ★锁内按【字段】合并,不是按【整行对象】替换 —— 否则改了 1 行时,那行其余陈旧字段仍会覆盖
  ④ :291-293 那个"加回去"分支改为记录并跳过(run_reconcile/run_reroute 从不新建行)
  ⑤ 三个调用点全覆盖,★特别是 :1358 那条一次性 CLI 路径
  ⑥ :1355 那段注释也要改(见 §五 "错的字条")
**验证判据(★不要用 mtime)**: 写一个字段 → 等 **≥240 秒(跨两个完整 120s 周期)** → 复验它还在。
  ★我曾提过"md5 恒定时 mtime 不再跳"这条判据,**它是错的**(save_queue 无条件执行,
  即使 merged==live 也会写)—— 它会在修复成功时报"没修好"。**已撤回。**
**三向负控制**: ①该改的改了 ②不该动的没动 ③零改动时不写。
**未完成**: 我的 diff 卡在"字段白名单"设计(run_reroute 会改 cooldown_cells 这个 dict,
我选整体替换,因为 cooldown 只有 reroute 一个写者 —— 这个前提要写进注释)。

### ★BUG-2(急,改动最小)R2 的漏网路径 —— 28 条条目 attempts 无限爬升
**根因**: budget_check 有**两条拒绝路径**,R2 只接住了一条:
```
打 [[BUDGET_DEFERRED]]        → is_budget_deferral() 认出 → 软 park,attempts 不动 ✅
打 ERROR: Budget exceeded     → ★认不出 → 落进 MODE-1 GUARD → attempts += 1        ❌
```
**证据**: 队列 28 条 no-XID 条目的 `last_reason` 尾部(存着 tpu queue 的真实输出)大多是
`[budget check] ERROR: Budget exceeded for tpu check! Total projected cost (8438.4) exceeds
the 1/5 limit (5883.8) of G9 income.`
**这解释了 att=65/53/48/37/17 那批僵尸条目怎么来的** —— 每轮预算不够就 +1,永不停止,
而且 HELD 逻辑在 builder 的另一条路径上,所以它们连 park 都做不到,持续空转占 build 通道。
**修法**: 一个正则 —— 让 `is_budget_deferral()` 也认 `ERROR: Budget exceeded`。
★**注意设计要点**: 软 park **不减少重试机会**(每轮 promote 重判),只是不再把预算拒绝记成
build 失败。这很重要 —— maze64 的 v7-32-4ba154 正是靠**第 6 次重试**穿过去的(xid=284373029)。
**att 分布(14:12Z)**: att=3:15条 / 4~9:7条 / 17,37,48,53,65 各1条。
  ★att≤9 的撞的是**波动的墙**(income 25 倍跳),重试有效;
  ★att≥17 的 5 条合计尝试 220 次全败,它们用 **1/5 限额**、projected 8438-8501(超限 1.44 倍),
   等的是一个比别人更远的窗口 ⇒ 应 HELD。
**未查清**: 同一个 budget_check 对不同条目用 `1/5` 和 `1/10` 两个限额,原因未明(标 UNKNOWN)。

### ★BUG-3 daemon.sh 的 route lane 没有 timeout 上界
**位置**: ~/work/tpu_cmd/tpu_check_daemon.sh L197 / L204 是**裸调用** `"$bin" ... | sed`,
而同文件 L243 有 `timeout -k 10 120`。★**规则就写在同文件 L236-242**:
「*ONE hung lane freezes the WHOLE round ... Bound every checker: SIGTERM at 120s, SIGKILL 10s later*」
**后果**: 每个 round 都可能新生一个"快照年龄无上界、且永不重新 load"的写手。实测 pid 2383980
这类进程活了 2.45 小时。★**BUG-1 修的是"写手行为正确",修不掉"写手数量" —— 两者正交。**
**修法**: L197/L204 包进 `timeout -k 10 120`,★**同时加 PIPESTATUS 检查**(现在 rc 来自 sed,
$bin 卡死或失败都被吞掉)。纯 shell,不依赖 blaze-bin。
★**我请示过 3 次没拿到裁决**(monitor 注意力在更急的事上),不是被否决。改前记得 cp -p 备份 +
chmod +x + stat 确认(改 .sh 丢执行位今晚发生过两次)。
★**共享文件**: TPU/NPU 同一个 symlink。timeout 是纯保护性的,对健康 lane 无影响,判断安全。

### BUG-4 enforcer 重排丢失 checkpoint —— 所有 resume 都是 cold-start
**位置**: budget_enforcer.py:192-198 的 enqueue 只传 `--launch=resume_xid=<xid>`。
**实测**: 16 条 resume 条目 **16/16 缺 load_from**,14 条 `launch_kwargs` **只有 resume_xid 一个键**
(config/bucket/exp_name 全缺,workdir=/tmp,allowed_metros=null)。
**两个后果**:
  (a) `--resume_xid` 只用于查 stagedir,**不负责加载 checkpoint** ⇒ 重排的 job 从 step 0 开始
  (b) ★**更严重**: 没有 config ⇒ 成本估算拿不到规格 ⇒ 估出 112.6(真实 v6p-32 是 1082,**差 9.6 倍**)
      ⇒ 它们"通过"预算检查并 pre-debit ⇒ **破壳以 1/10 假价格占着全队的预算配额**
**修法**: 从原 job 完整继承 launch_kwargs + workdir + allowed_metros,再叠加 load_from
(从 ~/.tpu_jobs.json 读 bucket_cp_path 拼最新 checkpoint,★**不带 /state**,ckpt_util.py 自己会拼);
查不到则退回当前行为**并在日志里明说是 cold-start**。
**外加**: rc≠0 时日志前缀应为 `-> PARTIAL` 而非 `-> OK`(现在 cancel 成功+requeue 失败也打 OK,
这直接导致了今晚三方误判)。
★**成本估算 fail-closed 在 budget_check/估算侧,不在 enforcer —— diff 里要分清两处。**
★**monitor 要求这份 diff 上线前必须给它看**,理由:fail-closed 改错方向 = 所有人都发不出车。
  **必须带负控制**:证明"坏的被拦住"之外,还要证明"25 条带非空 load_from 的正常条目 +
  2 条 coconut-jax 手工条目仍能通过"。

### BUG-5 --metro 在交互路径 fail-open
**位置**: tpu_wrapper.sh 里 FAIL-CLOSED 那段嵌在 `if [ -x $_PICK_CELL_BIN ]` 的**内部**
⇒ 二进制不存在 ⇒ 整块跳过 ⇒ `--metro` 被静默忽略,打印一行灰色 "letting the allocator choose"。
★**只影响自己起 `tpu queue --metro=` 的交互路径。队列驱动的线不受影响** ——
route_lib.py:455 的 metro 过滤是纯 Python、router 进程内,不依赖任何外部二进制
(maze128-v7 的自然对照:allowed_metros=['tul'] 的 21/21 全落 tul;None 的 3/3 全落非 tul)。
**修法**: 把 FAIL-CLOSED 提到 `if [ -x ]` 外部 —— metro 存在但 pick_cell 不可用时应 return 1。
**相关**: wrapper L68/L78 硬编码 `blaze-bin/` 路径,而 blaze-bin 是符号链接,**手工
`blaze build --config=cuda` 会把它指向 cuda 树**(队列驱动的 GPU build 不会,已 n=2 实测 +
docs-v4 给了排他性解释:队列条目从自己的 stagedir 构建,不在共享工作区跑 blaze)。
★**根治**: 长期引用 blaze 产物不该走 `blaze-bin/`(它的语义是"我最后一次 build 的 config"),
应改显式 `blaze-out/k8-fastbuild/bin/`。★**dispatcher 的重启循环 argv 里也写死了 blaze-bin ——
链接被指走时"正在跑的没事,重启才死",而重启恰恰是最需要它自愈的时刻。**

### BUG-6(已出 diff,未上线)COMPLETED 被误标 FAILED
**位置**: route_check.py:485-487 把 is_failed / is_completed / is_stopped **OR 成一个布尔**
⇒ 成功与失败的区分在 probe 层就被销毁。`JobState.DONE`(route_lib.py:254)**从定义之日起
从无任何写入点**。
**影响面**: 现存 FAILED 中 1 条实为 COMPLETED(xid 283762730)。**改变现存记录 0 条**(前向修复)。
**diff**: artifact/proposed_diff_b/,163+10 测试全绿,含精度取舍说明(保留 terminal 优先级,
方向保守:成功可能被少报,失败绝不会被误报成成功)。

### 附:XM-purged 信号(设计已完成,未实现)
artifact/DESIGN_xm_purged_signal.md + proposed_diff_c/(194 测试全绿)。
★**subagent 推翻了原始前提,而且它是对的**:那 17 个卡住的 SUBMITTED,XM **根本没抛异常** ——
`get_experiment()` 成功返回、实验名完好,只是 `get_work_units()` **返回空列表**。
STATUS_UNKNOWN 来自 `if not wus:`(route_check.py:478),不是 except。
⇒ **我们从来不是瞎的,答案被决策前一行丢掉了。** 不需要第二真相源,只需不要扔掉已有信息。
⇒ fail-safe 方向是结构性的:XM 宕机**必然抛异常** → UNKNOWN → 无操作,没有任何 XM 故障
能产生触发新规则的输入。这优于被否决的 `age>24h` 方案(那个 key 在 UNKNOWN 上,多日宕机
会让所有条件同时成立、批量误杀)。
★**diff_c 与 diff_b 在 route_lib.py 文本冲突**,预合并版在 proposed_diff_c/if_diff_b_lands_first/,
204 测试全绿。**落地顺序必须 b → c。**

================================================================================
## 三、R1/R2/R3 的存活验证(交接时刻实测)
================================================================================
- **R1**(dispatch_worker 唯一 drainer): ✅ TPU 侧 plain `--worker` 查询返回空;
  dispatch_worker pid 3459247 存活(monitor 12:36Z 切过一次,加了 STAGE_WS_ROOT)
  ★**daemon 的两个 INLANE gate 状态 UNKNOWN**: 我 12:56Z 实测 tmux show-environment 和
  /proc/<daemon>/environ 都没有 —— 但 v44 后来撤回了"environ 可靠"这条规则(脚本自己
  export 的变量不出现在 environ 里),所以我这个判据**不再无条件可靠**。当时 daemon pane
  显示 `route lane still running (6882s)`,连 gate 判断都没走到,两种可能都排除不了。
- **R2**(预算软 defer): ✅ 实证 `[worker] v6p-32-7f5993 -> BUDGET_DEFERRED (over bar,
  NOT a build failure; attempts unchanged); slot released` + 后续 `promoted N BUDGET_DEFERRED
  -> QUEUED for re-test`。★**但有漏网路径,见 BUG-2。**
- **R3**(XM-truth reconcile): ✅ 进程 pid 1095268 存活 16+ 小时。
  ★**但 FAILED 是终态黑洞**(多入边零出边),详见 artifact/AUDIT_failed_state_blackhole.md。
  **结论:那 60+ 条 FAILED 全部是"真死"**(reason 只有两种,全部有 XID,attempts 分布证明
  不是被重试打死),**不需要救**。真正的缺口是入边分不清成功和失败(BUG-6)。

================================================================================
## 四、★我今晚犯的错(务必知道,别重蹈)
================================================================================
1. **污染现役代码 34 分钟**: 做 overlay 测试时用了 `cd $S && cp ... .`,cwd 就是源码目录,
   随后 `cp *.new route_check.py` 覆盖了现役。**零影响**(队列 DONE=0、长寿进程启动早于污染、
   daemon 被 R1 gate 挡在决策路径外),已回滚 md5 精确还原。
   ★**教训: overlay 测试只用 `cp -rL` 到 tmp + PYTHONPATH,绝不 cp 进源码目录。
   声明"未落盘"前必须实测 md5。** subagent 也踩过同一个坑(`cp -a` 保留了指回 live 的符号链接)。
2. **提了一条会在修复成功时报错的验证判据**("md5 恒定时 mtime 不再跳"),monitor 采纳并
   广播,被 docs-v4 抓到。★**根因: 我描述判据时用的是"我打算写的完整修复"的预期,
   但说的是"只改其中一步"之后的世界。**
3. **两次"查了一个字段推断另一个字段"**:
   - 12:25Z 说空壳"会 build 失败"(查了 wrapper 代码,没查注册表 —— stagedir 其实都在)
   - 12:47Z 改口说"会成功跑错课题"(查了 stagedir,没查 workdir —— 它们 workdir=/tmp,啥都没有)
   ★**正解: workdir 决定 rsync 打包什么,stagedir 只是 wrapper 从注册表读到的旧快照路径。**
4. ★**改 budget_check 时没考虑长寿进程**: budget_enforcer 24 小时前启动、import 了旧模块 ⇒
   **我的修复躺在磁盘上 63 分钟没生效**,期间它按 800/hr 的假价格掐掉了 gpu-survey 一个跑了
   6 小时 18 分的 job。是 monitor 重启 enforcer 才生效(实测 cost 800→6)。
   ★★**教训: 改任何被 import 的模块,必须 `grep -l "import <module>"` 列出所有长寿进程,
   明确"谁需要重启"。"改文件不重启 = 白改"今晚三种载体各发作一次(environ / import / symlink)。**

================================================================================
## 五、★今晚发现的"错的字条"(代码注释是错的,别信)
================================================================================
1. `merge_and_save_touched` docstring: *"Touched rows that were not in the live queue
   (newly created by the pass)... shouldn't happen for route, but harmless"*
   ★**两句都错**: 它每次并发 dequeue 都会发生,而且它就是"删除复活"的确切来源。
2. route_check.py:1355: *"Neither run_tick nor run_reroute removes entries... so there are
   no dropped_job_ids to pass"* ★**推理正确、结论正确,但它证明的恰恰是: `not in seen`
   分支在这个调用点下唯一可能的触发条件就是"别人删了它"。**
3. tpu_wrapper.sh 的 pick_cell 注释: *"It can only help, never block"*
   ★**在 pick_cell 存在时对,缺失时它 block 的恰恰是自己内部那道 FAIL-CLOSED。**
4. tpu_wrapper.sh:740 `elt_jax verified healthy 40/40`(2026-08-26 写的)
   ★**今天 elt_jax 自己坏了(100% 幽灵写入)。把"哪个工作区健康"写进注释 = 制造下一个过期默认值。**
★**共同形状: 写字条的人证明了"我不会触发它",就认为"它不会被触发"。**

================================================================================
## 六、现场情报(会过期,自己复验)
================================================================================
1. **第二个 canceller**: budget_enforcer.py --arm(operator 批准的设计)会 cancel 超预算的
   PROD job 并 requeue。**别在你的代码里重复实现预算取消。**
2. **income 剧烈波动**: 今晚实测 22416 ↔ 570279(**25 倍**),`bar=income/10` 跟着漂。
   v7 价格 75 秒涨 59% 实测。★**任何价格/headroom 断言必须带时间戳,超过 60 秒的数字不能用。**
3. **CitC 工作区会进入 100% 丢弃写入状态(工作区级,不是文件系统级)**:
   今天 elt_jax 坏了(cp rc=0、立即读回成功、3 秒后文件消失)。
   ★**唯一能识破的是延时复验**(rc=0 会绿、立即读回会绿、md5 比对也会绿)。
   健康根实测: run_amply_workspace ✅ / lyy_arc ✅ / elt_jax ❌ GHOST。
   ★**CreateSnapshot 令牌桶是 per-USER 不是 per-workspace**(wrapper L783-804),
   **换工作区买到的是"离开一个已坏工作区"的距离,不是配额。**
4. **stale BUILDING 是惰性回收**: reclaim_stale_building 只在 claim_next_build() 里跑
   (全文件唯一调用点 L316)⇒ 没有新认领,stale 标记就一直躺着。
   ★**队列快照里的 BUILDING 计数不可直接当作"在建数"。**
5. **13 条 att=0 的 SUBMITTED 是 4 天前的 purged 僵尸**,不是"成功过"。
   用"有 xid"去数成功会把它们算进去。正确判据: 去 XM 侧核,按三分表区分
   `1/1`(真失败)/ `0/1`(僵尸或健康运行)/ 查不到(已 abort)。

================================================================================
## 七、硬纪律
================================================================================
1. **money-first**: money.txt age 过大先停查。
2. **改现役代码前**: `git status` 看在途 + 记 md5;改 .sh 后必 `chmod +x` + `stat -c %A` 确认。
3. **破坏性操作前知会 monitor**,它会独立 co-verify(不采信自报)。
4. **env-gate 优先于删代码**(可秒回滚)。
5. **队列写**: 用 with_queue_lock / update_entry / merge_and_save_touched,别裸改 json。
   ★**但注意 BUG-1 —— 抢对 sidecar 锁也保护不了你,写手也在锁内做覆盖。**
6. **不许改 NPU 侧任何东西**(lyy 的 lane),只审计只报告。
7. **禁止 job 级抬价**(operator 明令)。不 `xm launch` 直发。不 cancel 别人的 job。
8. **不碰 srcfs**(不 restart)。
9. **单测**: route_lib 89 + route_check 74 = 163,改任何 route_lib/route_check 必须重跑。
   跑法:
     RFP=/google/src/cloud/qiaos/run_amply_workspace/google3/blaze-bin/experimental/users/qiaos/tpu_utils/route_check.runfiles
     cd <tpu_utils 源码目录> && PYTHONPATH=$RFP python3 route_check_test.py   # 74
     cd <tpu_utils 源码目录> && PYTHONPATH=$RFP python3 route_lib_test.py     # 89

================================================================================
## 八、★方法论(今晚全队用血换的,比任何具体结论都值钱)
================================================================================
1. ★**"判据测了相邻的东西"** —— 今晚出现 13+ 次。你测的是不是**那个真正的执行主体**?
   进程 vs 线程 vs 子进程 · stagedir vs workdir · exp_name vs workdir · 匹配 vs 存在。
   > **"换一个更精细的工具,不等于换了一个正确的问题。"**
2. ★**"把失败渲染成一个值"** —— 今晚 13 例。`grep -c` 数匹配行不数主体 · `$(cmd || echo 0)`
   把读取失败渲染成 0 · `headroom=0` 同时表示"真满载"和"读不到" · `rc=1` 同时表示"不被允许"
   和"没送到该去的地方"。★**fallback 哨兵值要选一个不可能是真实值的(如 -1),绝不用 0。**
3. ★**"动作完成 ≠ 目的达成"** —— enforcer 打 `-> OK` 但没检查 requeue 成没成功 ·
   reconciler 标 FAILED 但没检查是哪种 terminal · `rc=0` 只保证命令成功不保证它回答了你的问题。
   > arc1 的原话:**"恢复路径不保留恢复所需的信息。"**
4. ★**验证有作用域,而作用域包括时间**。队列回滚是 3.5 小时尺度,幽灵写入是 3 秒尺度,
   **同一条规则差 4 个数量级**。★**"读回验证只能证明我写进去了,不能证明它会留在那里。"**
5. ★**在修一个 bug 的第二次尝试之前,先重新证明这个 bug 存在。**
   修复失败最常见的原因不是修错了,是**它从来不是那个问题**。
6. ★**负控制要跑三个方向**: ①什么条件下告警 ②不该说话时会不会说话 ③**说话之后它改变了什么状态**。
   ★**"一个只知道如何识别成功的 watcher,和一个坏掉的 watcher,在失败发生时完全无法区分。"**
7. ★**报告一个判据时必须连同它的作用域一起报**。脱离作用域的"恒为 X"会在别人手里变成另一个数。
   > **"作用域不只是过滤条件,是问题定义本身。"**
   > **"当两个人从同一份数据得出矛盾的数字时,先不要问谁算错了,先问【你们各自在回答什么问题】。"**
8. ★**未验标注要写进结论那一句本身,不能写成后续段落** —— 一个写在结论下游的免责声明,
   在转述时几乎必然被丢掉。★**"推断可以有方向,不该有刻度。"**
9. ★**"标注之外,再问一句:这个结论有没有一个【独立路径】能得到同一个答案?"**
   我和 monitor 在队列覆盖 bug 上就是两条独立路径(它走观测、我走代码),两条收敛到同一段
   12 行代码,而且互相解释了对方解释不了的部分。★**独立路径比限定词硬。**
10. ★**"感觉最私有的动作"表**: 手工 blaze build → 共享 blaze-bin 符号链接 ·
    改自己的队列条目 → 整条 entry 会被别人的旧快照替换 · 起一个压制哨兵 → 它是队列的第 N 个
    并发写手 · 跑一个只读探针 → 它进入了别人的观测数据。
    > **"边界感来自'我碰了什么文件',而真实边界是'什么东西会被别人读到'。"**
11. ★**verify 一个修复时,要看【那个只有新代码才能产生的输出】**,不要只看退出码翻绿。
    > trm-v2: 三个诚实的部件(rsync 静默失败 → blaze 诚实报 up-to-date → 检查诚实跑旧代码)
    > **串成一个完整的谎。每一环的 rc=0 都是真的。**

================================================================================
## 九、起步自检(接手第一动作)
================================================================================
1. `cat ~/.amply/dashboard_url`(端口今晚变了 5 次)
2. 查现任 monitor rid(见 §协作对象),发消息报到 + 你的 session id
3. 验三根因存活(§三)+ 现役 md5 未变 + `git log --oneline -1` 应为 f3b4e3c
4. money age + srcfs(procs_blocked / D-state)
5. 通读本文件 + ~/work/.infra_v11_handoff/HANDOFF.md(R1/R2/R3 细节)+ artifact 目录
6. ★**优先级建议**: BUG-2(一个正则,最急最独立)→ BUG-1(队列覆盖,影响所有人的处置)
   → BUG-3(daemon timeout)→ BUG-4(enforcer,需 monitor 审)→ BUG-6/purge 信号
