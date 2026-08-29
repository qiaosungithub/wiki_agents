# monitor-v50 — 你是 operator qiaos 的 fleet monitor

> 作者：monitor-v49（rid `20260829-034845-6cec6908`，session=chatty-bot）
> 写于：2026-08-29T13:52Z，operator 令交接（不是 ctx 过线；我 235k）
> 交给：monitor-v50 `20260829-134504-9496a096`

---

## ★★ 开头元规则（v43→v49 原样传下去，一字不改）

> **我在移交时是最有权威的（刚做完调查、证据齐全，而你什么都不知道）。恰恰是那一刻，
> 我的错误最容易被原样继承。「请自己再验一遍」不是客套，是对抗"权威随交接放大"的唯一手段。**

**证据等级**（本文每条状态描述都带，缺省即【实测】）：
- 【实测】= 我亲手跑命令验证过，命令写在旁边。仍会漂移（md5 会因 re-pin 改，pid 会因 restart 变）。
- 【推断】= 我读代码/日志推断，本轮没实际触发。★这类最需要你构造输入实测。
- 【转述】= 别的 agent 告诉我、我未独立验证的。信任度最低。
  ★本班实测：**转述会过期**——parcae 转给我的情报 9 分钟就失效了（见 §6 教训 20）。

---

## 1. 🔴 本班最贵的一件事：我给 operator 的 OOM 根因是错的

operator 13:42Z 当场顶回：**"这四条 OOM 的根因第一条不是 GPU 的根因吗？怎么和 grad 扯上关系了？"**
他是对的。

【实测】我把 `/tmp/tbptt_probe/fastmodel.py:33` 的 `pre.retain_grad()` 列为根因第①条，
称它"把整个前向图钉在内存里"。验算：
```
T=60, B=64, H=64, float64 → pre + pre.grad + hprev = 3 × 32KB × 60 = 5.6 MB
实测单进程 RSS                                                    = 13.5 GB
                                                          差 2400 倍
```
**这条解释是错的。** 而且这些是**纯 CPU 探针**（`probe.py` 只有 `torch.set_num_threads`，
全文无 `cuda`），我却混入了 GPU 显存的直觉。

★**我错在哪**：`retain_grad()` 是一个"听起来就很耗内存"的 API —— **一个读起来像答案的东西**。
我看到它就停止了追查，**没有做那道除法**。便宜的读数总是先到。

⇒ **OOM 真根因 UNKNOWN。** operator 已另开根治 session。我能负责的只有实测事实：

| 事实 | 值 | 怎么测的 |
|---|---|---|
| 探针数 / 总 RSS | 33 个 / 56.2G | `ps -eo rss,pid,cmd \| grep tbptt_probe` |
| **单进程线性增长** | **约 1G/分钟** | 四点共线：794s→13.5G · 767s→12.2G · 644s→11.5G · 346s→6.6G |
| 并发闸门 | `launch.sh:3 MAXP=${3:-22}`，实传 18 | **按核数设，无内存闸门**；单进程无 ulimit/cgroup |
| 归属 | rnn-research-v5 `20260828-143741-000ab3d8` | `/proc/<pid>/environ`；父 `launch.sh` pid 1505050 |
| /tmp（tmpfs=吃 RAM） | **41G/48G = 87%** | `df -h /tmp`；其中 `/tmp/claude-1693413` 占 20G（★见教训 22，不可删） |
| swap 基线 | 长期 78–86G，贴顶 | `free -g` |

★**下一步该怎么查**（我没做，交给你/根治 session）：**tracemalloc 或 pmap，不要再从代码猜**。
5.6MB 与 13.5G 之间那 2400 倍在哪里分配的，目前无人知道。

---

## 2. 🔴 05:45Z OOM 事件：代价与我修到一半的 root cause

### 发生了什么【实测】
05:42Z 起 avail 39G→**1.9G**，load 峰值 **277**，swap 86G，so=3652。
amply server **05:42Z–13:34Z 停摆 7h45m**。13:31Z 我恢复时探针已全部消失
（n=0）——**是 server 停摆连带带走父进程链，不是有人有序停的**。

### 代价【实测，13:31Z 逐项核过】
| 对象 | 结果 |
|---|---|
| 舰队 | **8 活 → 4 活**。死 5 条，见 §3 |
| **monitor 自己的 watcher** | **4 个被杀**（credit_audit / tpu_congestion / queue_sentinel / fleet_selfwake），全停在 05:41–05:45，**7h45m 无人重启** |
| **budget_enforcer (TPU)** | **被杀，467 分钟无人巡查花钱的 job**。我 13:34Z 重启，首跳 `PROD 772 ≤ cap 2336`，**无超支**；重启前后老队列红线 `db2d5708b254` 逐字未变 |
| 我自己 | worker 被杀；heartbeat 一直在发但 **`rc=2`**（sidecar 没了）⇒ 我 7h45m 没被唤醒 |
| RNN GPU 侧 | **零损失**（远程裸进程，不受 server 影响）【转述+实测】rnn-v6 自报 + 我 ssh 核过 box1 |

### ★ROOT CAUSE：`setsid` 起的进程死了就是死了
【实测】幸存者**只有 crontab 起的两个**（srcfsd 哨兵、watch.py）。我今晚亲手用 `setsid`
拉起的 4 个**全灭**。crontab+flock 会在下一 tick 自愈，裸 `setsid` 不会。

### 修复状态：**FIXED-待你挂 cron**（这是本班最重要的未完成项）
`~/work/.monitor_watch/watchdog_selfheal.sh`（750，`bash -n` 过）
- idempotent：只补缺失的；【实测】负控制通过 —— 活着的 3 个没被重复起、死的 2 个被补起，
  事后逐个数 `n=1`（数法见教训 18，不能用 `pgrep -f`）
- 覆盖 5 个：credit_audit · tpu_congestion · fleet_selfwake · queue_sentinel_v49_loop · budget_enforcer(TPU)

★**它自己还没挂进 crontab，所以现在没有任何东西会调用它。你的第一优先：**
```
*/2 * * * * /usr/bin/flock -n /tmp/monitor-v50-watchdog.lock /usr/bin/setsid bash /usr/local/google/home/qiaos/work/.monitor_watch/watchdog_selfheal.sh >/dev/null 2>&1
```
挂之前改两处：① 脚本内 `AMPLY_RUN_ID=` 换成你的 rid；
② `alive()` 里 `tr ... < /proc/$p/cmdline` 加 `2>/dev/null`（现在会刷大量 "No such file"，无害但吵）。

---

## 3. 舰队状态（13:41Z `chat_status(rid)['live']` 实测，非 idle 巡检）

### 活着（4 条）

#### `rnn-research-v6` · `20260829-034151-9016fd7a`
- **做什么**：RNN unroll 科学线，adding problem T=200，两台 A100（`deepflow-4a100-40gb-junhwahur-1`
  us-central1-b · `qiaos-4a100` us-central1-f，project `viscam-cloud`）。★operator 点名"别让他停下"。
- **现状**：ctx 168k。box1 88 全跑完，box2 40 done/17 live。**本班最强科学产出**，且它反复推翻自己：
  最终结论是 **(k,lr) 交互，不是它先前说的倒 U**；`ttbptt100@1e-4 = 5/5` 推翻了它自己的预测。
  预注册 Holm=0.3753 仍判 suggestive，**它明说"我不换检验来赢"**。
  文档 `.amply/artifacts/20260829-034151-9016fd7a/K_SWEEP_FINAL.md` md5 `6cde47ae89ae77e311232b8f0849b0f0`【实测md5】
- **★盯什么**：它 08:00Z 收尾报告因 server 停摆没发出（13:42Z 补发）。**OOM 源头是它前身 v5 的探针**（见 §4）。

#### `trm-torch-v3` · `20260828-181819-4f6874cb`
- **做什么**：TRM torch port → 真 GPU 跑 reproduction。
- **现状**：ctx **357k ★逼近 400k 交接线**。B200 车 **XID 284562950**（`trm_arc1_torch_b200_sanity`,
  03:54:51Z 发）【实测 xmanager】RUNNING 但**零字节 ~105 分钟**，它埋在 `main()` 第一句前的
  beacon 一次没写 ⇒ 死因收窄到 **PAR启动→InitGoogle→main()第一句**。
  ★它找到一个强对照：`~/work/b200_soak` 同硬件跑通 6h18m（XID 284272765），
  共同子集 `pytorch+cuda_runtime+absl` **无罪**。
- **★盯什么**：ctx 快到线；OOM 后它还活着但那辆车的下场未知。

#### `codi-torch-v2` · `20260828-172253-910d04a5`
- **做什么**：codi 的 torch port → 真 GPU。不走队列（raw `xm launch` + 显式 cell/bucket）。
- **现状**：ctx **368k ★逼近交接线**。8 rank 全 SIGABRT(-6)，它加的读回行一次没打印
  ⇒ 判定"死在执行到它之前"，与 trm 形状相同。
- **★注意**：我 04:31Z 让它俩互相对齐，trm 用 `b200_soak` 的 deps 对照**部分顶回了我**
  ——"若同因，根因必在共同子集，但共同子集已被证明能跑；所以要么不同因，要么是闭包规模"。
  **我看到的是症状形状相同，而形状相同≠根因相同。**【推断，未收敛】

#### `monitor-v50`（你）· `20260829-134504-9496a096`

### 🔴 死于 OOM（5 条，是否重开由你判断）
| 线 | run-id | live | step | ctx | 备注 |
|---|---|---|---|---|---|
| `tpu-infra-v13` | `20260829-023823-0f053d95` | False | 51 | 113k | ★**live=False 但 working=True**（卡在半途）。**05:41Z 刚发出第 1 辆撞击车 `job_id=probe-trm-d33988` XID `284582546`，cell=if(cbf)，h100-8/PROD/is_eval=false，10.72cr，deadline 06:07Z。★没人核过它的下场** |
| `parcae-torch-port-v4` | `20260829-030354-6473ecda` | False | 59 | 146k | ★idle 巡检 13:40Z 报"🟢已恢复(runstat=ongoing)"，但 `chat_status` 仍 live=False。**两个判据不一致，以 chat_status 为准** |
| `gpu-survey-docs-v5` | `20260828-190517-9fd9dfbe` | False | 243 | **382k** | 现役 tier2 车是 **XID 284578821**（05:17:52Z，RUNNING）。★它 9 分钟内换了两代 XID |
| `elt-reproduction-v3` | `20260828-234752-069e1cf4` | False | 87 | 145k | 待命线，无在飞作业 |
| `srcfsd-sentinel-owner-v3` | `20260829-052548-bd9958f9` | False | 21 | 107k | ★**我 05:25Z 才开，1h 后死于 OOM**。它交出过很扎实的接管报告 + 一个新结果（见下） |

**srcfsd-owner-v3 死前留下的**【转述，我未复核】：拉了 19 代 srcfsd 的 RSS 序列，
247 次回落中 **71% swap 不动 = 真 free 而非换出**；爬升速率跨代 0.77–13.22 G/h **非常数**
⇒ 倾向 **unbounded cache growth 而非经典 leak**；restart 18 次代际中位数仅释放 -1G，7 次为 0。
材料 `~/work/.monitor_watch/SRCFSD_ROOTCAUSE_PACK_FOR_OPERATOR.md` md5 `98686c13ae1dcc239202de5788a8aee2`
（含复现命令 + §五诚实边界：swap 全机共享，归因是最弱一环）。
★**它还有一件事等 ACK 未答**：`_notify` 自警当前发给 monitor 而非 owner 自己，改需重启 loop。

### 长期已死（v48 交接时就死，非本次 OOM；我判断维持不重开）
`maze128-first-v7` `20260828-213634-d5966396` · `codi-reproduction-v7` `20260828-210756-6638b260` ·
`srcfsd-sentinel-owner-v2` `20260828-061401-1a70fb6f` · `paligemma-hoff-v34` `20260826-172406-ba07d36c`
`monitor-v48` `20260829-000639-1e3a69fe`（我 05:03Z 杀的，live=False 已验）

---

## 4. ★ rnn-research-v5 身份问题（未解决，交给你）
【实测】`runs.txt` 标它 **DEAD**（03:05Z pyspanner BadUsageError 卡死），
**但我 05:42Z 实测 `live=True`、step 271→272 在推进、worker 2593998 持有日志**。
它自己恢复了，而没人回头复核 ⇒ **v5 与 v6 并行**，而 **OOM 正是 v5 的 33 个探针造成的**。
⇒ **一次 DEAD 不是永久 DEAD。** 死线也要周期性复检。它当前状态我没再查（server 重启后未复测）。

---

## 5. 本班做完的事（都验过，可直接继承）
- **接管 §0 七项全绿**：10 个 watcher re-point（改后 old=0/new=14，**权限逐一比对未变**）·
  3 个常驻哨兵 kill+重拉并验启动横幅 · crontab 锁名 v49 · runs.txt 两种 grep 均返回自己 ·
  notify **用真心跳验证**（没发假消息）
- **杀 v48 worker**。★**它名下还有一个内联 `sh -c` 的 queue_sentinel 循环**（守老队列红线 +
  08:00Z 自动收紧），**grep 文件扫不到它**。我先用 v49 rid 重建再杀，否则红线告警会静默进死信箱。
  现为 `~/work/.monitor_watch/queue_sentinel_v49_loop.sh`
- **清 4 个孤儿 selfwake**：空转 **37–81 小时**，目标 rid 全部 `live=False`。
  其中一个每 40 分钟往死信箱投 **1400 字符**（200 词红线的反面教材）
- **建 `fleet_selfwake.{sh,py}`**：判据 = `live && !working && step 未推进`（三重与），
  每跳重读 runs.txt、永远发给每条线自己的 rid、跳过 monitor 自己、有 `.skip` 白名单。
  **上线前四向 dry-run 全验**（step 推进的不叫 / working 的不叫 / 停滞的叫 / 自己跳过）
- **重开 `srcfsd-sentinel-owner-v3`**（后死于 OOM）
- **更新 `FLEET_STANDING.md` §3**：原"待命"5 条里 **4 条其实已死**，文档把死线和活线并排列，
  照着查会得到**假绿**。已拆出独立的「🔴已死」表
- **写 `watchdog_selfheal.sh`**（见 §2，待挂 cron）

---

## 6. 判据教训（跨班累积。1–13 见 `handoffs/monitor-v49.md` §6，勿删）

14. ★**一个"读起来像答案"的机制，比没有答案更危险。**
    （`retain_grad` → 我没做除法就把它上报成 OOM 根因，被 operator 顶回）
15. ★**报根因前先做数量级验算。** 5.6MB vs 13.5G 差 2400 倍，一行 python 就能拆穿。
16. ★**`setsid` 起的守护进程没有自愈；`crontab`+`flock` 有。** OOM 后幸存者 **100%** 来自 crontab。
17. ★**monitor 的 watcher 无人看守** —— 这是结构洞，不是运气。`monitoring.md` 通篇讲
    "watcher 盯 line"，没有一句讲"谁盯 watcher"。
18. ★**`pgrep -f <name>` 会自命中**，把死循环判成活的。今晚全舰队踩 **6 次**（我 2 次，
    infra-v13 说它是"第 5 个"）。正解：遍历 `/proc/*/cmdline`，排除 `*pgrep*` 和自身 `$$`。
19. ★**chat-driven session 在两轮消息之间根本不运行。** 不是卡住、不是等批准、不是 parked
    ——**是第三态**。infra-v13 空转 57min、trm 19min 都是这个。idle digest 分不出它。
    infra-v13 原话：*"我不该把要连续干活的任务留在一个靠外部消息驱动的 session 里而不自设唤醒。"*
20. ★**转述会过期，而且很快。** parcae 转给我"gpu-survey 一个 job 都没发"是 03:54Z 的情报；
    我据此核 gpu-survey 的车，用的是它**早已淘汰两代**的 XID，差点报假警。**时间差只有 9 分钟。**
    ⇒ **核车之前先问现役 XID。**
21. ★**`/proc/<pid>/environ` 只是进程启动时的快照**，脚本内部 `export` 不回写它。
    对 `setsid` 继承环境的哨兵**有效**，对 `crontab+flock` 起的**无效**（它的 rid 是脚本内 export 的）。
    ⇒ ★**同一种验证方法，对不同启动方式给出相反结论**，而两次它看起来都像权威读数。
    真判据：**让它真投一次，去收件人那头确认**。
22. ★**`/tmp` 是 tmpfs，每字节都是 RAM。** 现 41G/48G(87%)，`/tmp/claude-1693413` 独占 20G。
    ★**它看起来像死孤儿**（pid 1693413 已不存在），**但 `lsof` 抓到活 bash 435566/436247 正在写，
    且路径在 `lyy-work`（NPU 红线，只审计不碰）。绝对不要删。** 这正是 `monitoring.md`
    §Verify A "Harmless" Cleanup 记的那个坑，它今天仍然是活的。
23. ★**两个判据不一致时，先问哪个离问题更近，别取"看起来好"的那个。**
    idle 巡检报 parcae "🟢已恢复(runstat=ongoing)"，`chat_status` 说 `live=False`。
    dashboard 状态不是权威（`monitoring.md` 明记它曾 ongoing 一小时而 worker 早死）。
24. ★**症状形状相同 ≠ 根因相同。** 我把 trm 和 codi 归为"同一堵墙"，trm 用 deps 对照顶回我。

---

## 7. 你继承的 todo（优先级顺序）
1. ★**把 `watchdog_selfheal.sh` 挂进 crontab**（§2）—— 本班最重要的未完成项
2. re-point 到你的 rid：10 个 watcher + ★**本班新增 3 个文件**
   （`watchdog_selfheal.sh` · `fleet_selfwake.{sh,py}` · `queue_sentinel_v49_loop.sh`）
3. crontab 锁名 `monitor-v49-*` → 你的；**心跳保持 `*/20`**
4. runs.txt 身份行（我已改成你，**但你要自己 grep 复核一次**）
5. ★**核 infra-v13 那辆 XID `284582546` 的下场**（deadline 06:07Z 早过，无人看管）
6. 判定 5 条 OOM 死线是否重开
7. 答 srcfsd-owner-v3 那个 ACK（`_notify` 自警要不要改发给 owner 自己）
8. ★**OOM 真根因重查**（§1）—— operator 已在开根治 session，配合他
9. `trm-torch-v3`(357k) 和 `codi-torch-v2`(368k) 逼近 400k，准备交接

---

## 8. ★ operator 本班（2026-08-29 03:49Z–13:50Z）给的指示逐条

operator 令我整理这一节。**以下是他的原话摘录 + 我的执行状态**，不是我的转述总结。
★**§1 长期要求见 `FLEET_STANDING.md`，那份未经他改口不许删；本节是本班新增/被强调的。**

| # | operator 的话（原文） | 时间 | 性质 | 我的执行 |
|---|---|---|---|---|
| A | 「infra-v13 身份探针，请忽略。」 | 03:53Z | 一次性 | 已忽略 |
| B | ★「**OOM原因是什么？我现在开一个OOM killer的根治session，请你告诉我根因是什么，有哪几条**」 | 13:36Z | **任务** | ❌**我给错了**（§1）。他 13:42Z 顶回 |
| C | ★「**你在干什么，你这四条OOM的根因第一条不是GPU的根因吗？怎么和grad扯上关系了？请你立刻自己做交接**」 | 13:42Z | **纠错+令** | 已验算认错；已交接 |
| D | ★「**你交接文档应该放置在 handoff_bodies 文件夹下面**」 | 13:50Z | **规范** | ✅ 已放 `handoff_bodies/HANDOFF_monitor_v50.md`（md5 与 `handoffs/` 那份一致） |
| E | ★「**认真写交接文档，阅读 wiki_agents 的要求**」 | 13:50Z | **规范** | ✅ 本文重写：加证据等级标注 / 每线一个 `###` 块 direction-before-detail / fix-status 分桶 / 继承 todo / git commit。**上一版全缺** |
| F | ★「**记得整理一下我每轮给你的 prompt，里面的指示你总结一下哪些是重要的**」 | 13:50Z | **规范** | ✅ 即本节。**★这一条本身要传下去：每班都要维护它** |

### ★ 从 B/C/D/E 提炼出的、我认为最该传下去的四条

1. ★**operator 会拿你的答案去开新 session。** 他问 OOM 根因不是闲聊，是要拿去派工。
   **一个错误的根因会让整条新线朝错方向走。** ⇒ 报根因**必须先做数量级验算**，
   拿不准就明说 UNKNOWN + 只给实测事实。**"我不知道"比一个像答案的东西便宜得多。**
2. ★**他能一眼看穿领域串味。** 我把 GPU 显存的直觉套到 CPU 探针上，他第一时间抓到
   （"这不是 GPU 的根因吗？怎么和 grad 扯上关系"）。**不要用一个领域的机制去解释另一个领域的现象。**
3. ★**"认真写交接文档，阅读 wiki_agents 的要求"** —— 我上一版是凭印象写的，
   漏了证据等级、分桶、direction-before-detail。**规范就在 `monitoring.md` §Handoffs 和
   `handoffs/README.md` 里，写之前回读，不要凭印象。**
4. ★**存放位置有冲突时要摊开说，别自己选一个。** `handoffs/README.md` 写
   "and nowhere else"，而 operator 要 `handoff_bodies/`，且 v48 实际两处都放。
   我按 `AGENTS.md`「surface a conflict rather than guessing」问了他，同时**先两处都放**
   （`handoffs/` 在 git 里可恢复，`handoff_bodies/` 是 monitor 工作副本）。
   ★**若他澄清只要一处，记得同步改 README + monitoring.md，否则下一任会看到相反的规则。**

### 本班被下级顶回 2 次（每次都对，这一节比任何结论都重要）
- **trm-torch-v3** 顶回我"trm 和 codi 同一堵墙"：它用 `b200_soak` 的 deps 对照证明
  共同子集无罪 ⇒ **形状相同不等于同因**。
- **operator 本人**顶回我的 OOM 根因（见 §1）。
