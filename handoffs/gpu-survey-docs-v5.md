# ★你是 gpu-survey-docs-v5 —— GPU survey 的 docs / intel 车道

**你是谁**：这条线的第 5 代。前任 `gpu-survey-docs-v4`（run `20260828-041705-7917563e`）context 到了 636k，由 monitor-v46 主持交接。**下面整篇是它自己写的**，比任何人从外面转述都准。

**谁在看你**：monitor-v46（run `20260828-142407-0fac97e6`，session `chatty-bot`）盯你的健康和 context。有事直接在本会话说，它会看到。

**★你不是 GPU 主线**：主线（h100/gb200/b200 真实硬件作业提交）曾属于 `gpu-survey-v3`，**而 v3 已被 operator 于 18:10Z 停止**。你这条是 **docs / intel 车道**，产出文档与判据。★**在 operator 明确授权之前，不要接管提交权** —— 如果你认为主线需要有人接，先报告 monitor，不要自己开始提交。

**从哪读起**：§0 的元规则和 §0b 的操作禁令**先读**，那是立即生效的。然后 §1 起通读一遍。

**★三条今晚全队通用的纪律**（不在下面的正文里，但同样适用）：
1. 发多行消息用 `<<'EOF'`（**引号包住定界符**）。今晚两条线踩了同一个坑：未加引号的 heredoc 让反引号被 shell 执行、变量未展开，**而 send 仍然 rc=0 报 SENT**，对方收到的是残缺内容。
2. **不要往 `/tmp` 放大东西**。`/tmp` 是 tmpfs = 物理内存；今晚它涨到 47G 把 swap 撑满，险些 OOM 整机。大文件放 `~/work/` 下自己的目录。
3. **srcfs 哨兵的 `bt` 计数当前不可信**（已实测：既双计，又会把一小时前的旧日志行反复计入「最近 600 秒」）。判断 srcfs 是否真出事，看 `dropped_resources.ascii` 是否在增长、以及有没有活的 staging `rsync` 进程。

---

# HANDOFF — GPU-survey DOCS / INTEL lane (gpu-survey-docs-v4 → successor)

## 0. ★READ THIS FIRST — the meta-rule, pass it on verbatim

> **我在移交时是最有权威的**(刚做完调查、证据齐全,而你什么都不知道)。**恰恰是那一刻,我的错误最容易被原样继承。**「请自己再验一遍」不是客套,是对抗「权威随交接放大」的唯一手段。

今晚这条线**证实过这句话至少 5 次**:每次我顶回上级的结论,都是因为我自己跑了一遍;而我自己被顶回 3 次,每次都是因为我**没有**验自己的前提。**优先复验标了【推断】和【转述】的每一条。**

## 0b. 🔴 立即生效的操作禁令

**`tpu enqueue` / `tpu queue` / 任何写队列的操作,全部禁止。**
infra-v12(run `20260828-141921-a3218cba`)已于 **15:28Z 停机**,正在 operator 授权下重写调度器的 job 记录结构与 resume 机制。停机期间队列不派发、新提交不被处理。
★**已在 XM 里跑的作业完全不受影响,没有任何东西被 cancel。**

- ⇒ 不要 `tpu enqueue`、不要写 `~/.tpu_local_queue.json`,直到 infra-v12 发出**开机通告**。
- ⇒ ★**不要给 infra-v12 发回执或状态更新** —— 它 15:43Z 明确要求全队静默,只在「**正在发生的、会造成实际损失的事**」时才联系它。
- ⇒ ★**但 `xm launch` 是被 operator 明确授权的例外**(17:16Z),它绕过调度器。NCCL smoke 就是这么发的。**用它之前先读 §6 的红线。**

## 1. ★我是谁 — 我不是 gpu-survey-v3 的下一代

**最容易被误读的一点,monitor 今天差点误判,所以放在最前面:**

| 线 | run-id | 车道 | 提交权 |
|---|---|---|---|
| **gpu-survey-docs-v4**(=我) | `20260828-041705-7917563e` | **docs / intel / reports** | ★**无**。我不做真实硬件作业提交 |
| **gpu-survey-v3** | `20260828-012259-578e0f6c` | **GPU 主线** | ★**独占** h100 / gb200 / b200 的提交权(含 PROD 重发) |

★**我们是两条并行的线,不是前后代。** 我名字里带 `docs` 但版本号是 v4,纯属命名巧合。
★**v3 已于 17:21Z 完成交接、准备退休**,它的交接文档在 `~/.amply/artifacts/20260828-012259-578e0f6c/HANDOFF_nccl_smoke.md`(197 行,md5 `ba22c8af6c5daa192450ab8fbad29fe9`)。
★**v3 退休后,GPU 提交权归属需要 monitor 重新裁定** —— 不要默认它归了我。

## 2. 这条线做什么(direction first)

**科学目标**:回答 operator 的三个问题 —— GPU 能不能拿到卡、能持有多久、多卡通信能不能用。
**我这条车道的产出**:把其它 GPU 线的一手发现,转成 `~/work/wiki_agents/` 里**不会过期的规则**,供全队和未来的 session 读。**我产出文档,不产出实验。**

**给谁用**:`~/work/wiki_agents/gpu_on_borg.md` 是任何人在 Borg 上跑 GPU 的第一读物。
**分支 `google-internal-migration`,远端 `git@github.com:qiaosungithub/wiki_agents.git`。**
★**17:47Z 我已 push,远端 HEAD = `5dae5ee` = 本地 HEAD,ahead 归零。** 在此之前 52 个 commit 只在本机。

## 3. ★三个问题的当前答案(全部【实测】除非标注)

| 问题 | 答案 | 判据 |
|---|---|---|
| 能拿到卡吗 | ✅ **能**。B200 真机 `device_count==8`,`NVIDIA B200 / sm10.0` | job 自写 CNS |
| 能持有多久 | ✅ **6 小时 18 分零抢占**,期间 3 次 Borg 迁移(各 ~9 分钟)自动续跑 | 同上 |
| **多卡 NCCL** | 🔴 **UNTESTED**(不是 FAILED)—— **从来没有成功执行过一次集合通信** | 见 §5 |
| GB200 / GB300 | 🔴 **operator 的老板明令禁止使用**(15:26Z)。**不要发、不要建议发** | operator 直接指示 |

**已排除、不用再查的**:
- B200 **不需要 IMEX 授权**(那是 GB200/GB300 才有的墙)——【实测 + 源码】
- 三条 torch 线(parcae/trm/codi)**都不需要 flash_attn**,全用 `F.scaled_dot_product_attention`
- **staging root 定为 `run_amply_workspace`**(见 §4)

## 4. ★torch 版本 / workspace:已定案

**选 `/google/src/cloud/qiaos/run_amply_workspace/google3`,三条线统一。**【实测】

```
run_amply_workspace  → torch 2.13.0      ★当前健康的 staging root
elt_jax              → torch 2.15.0a0    ★★已 DRAINED(幽灵写入:rc=0、立即读回成功、几秒后消失)
查法: grep -A2 'version:' <WS>/google3/third_party/py/torch/METADATA
```

★**为什么能统一**:三份代码 BUILD 里都是裸的 `//third_party/py/torch:pytorch`,**零版本 pin**;用到的 API 全是稳定核心(SDPA / `rms_norm` / `cuda.*` / autocast / compile / `init_process_group`),**2.13 和 2.15 都有**(`F.rms_norm` 连行号都一样:`nn/functional.py:2998`)。
★**为什么值得统一**:共用一个 root 让「同样的代码、不同的行为」在**结构上不可能**发生,而不只是不太可能。
⚠️ ★**别读 `third_party/py/torch/torch_version.py` 比对 workspace** —— 它是模板,两个 workspace md5 完全相同,**会给出一个自信的「没差别」**。我自己先踩了这个坑。

## 5. 🔴 NCCL:唯一未决,现在正在验

**当前状态(18:13Z)**:subagent `fresh-sloth` 已用 `xm launch` 发出 **XID 284429699**(b200-8 / PROD),正在等第一条 CNS 行。★**它用实测基线判断「还没到该担心的时候」**:soak-v3 从 launch 到第一行用了 13.1 分钟,它现在 7.5 分钟。**这个纪律要继承 —— 首次运行没有基线时,「感觉慢」不是证据。**

**两次历史失败,都不是关于 NCCL 的证据**:

| XID | torch | 死在哪 |
|---|---|---|
| 284272765 (soak-v2) | 2.15.0a0 | **fan-out** —— `torch.multiprocessing` 被 g3 打补丁,`get_context("fork")` 直接 assert。**根本没进 NCCL** |
| 284369343 (soak-v3) | 2.13.0 | ★**未知,而且是结构性不可知** —— 探针只在跑完后写结果,所以「卡在里面」和「死在前一行」产生**逐字节相同**的证据 |

★★**torch 版本假说已降级为「一个没被控制的变量」,不是诊断。**【v3 自己降的,我独立同意】
理由:探针的完整 API 面(`dist.{init_process_group,all_reduce,barrier,destroy_process_group}` + `torch.cuda.*`)**在两个版本里都存在**。而且两次运行**代码和库同时变了** ⇒ 对照被混淆,不存在「同一份代码在两个版本上」的数据点。
⚠️ ★**干净的 A/B 现在做不了**:`elt_jax`(torch 2.15 那个 root)已 DRAINED。

**subagent 已做的关键改造**(`~/work/b200_soak/main.py`,备份 `main.py.bak.v3_hang_20260828`):

1. **心跳线程在探针【之前】启动** ⇒ 卡住时仍写 `alive`,沉默就真的意味着进程没了
2. **每个阻塞步骤【进入】前落盘**,子进程各写各的文件(8 个并发 appender 写同一个 CNS 对象是第二个故障源)
3. **整个探针一个总 deadline**(默认 240s),替代 `q.get(timeout=300)`×8 = 最坏 40 分钟
4. **显式 `init_process_group(timeout=90s)`** —— torch 默认是 10 分钟,比整个探针预算还长
5. ★**TIER 0:单进程 NCCL**(`torch.cuda.nccl.all_reduce` 直接跨 8 卡),**删掉 rendezvous / TCP store / rank 握手** ⇒ 让「协调 bug」不能伪装成「NCCL 结论」。**先证明 tier 0,再谈 tier 1**
6. 结果走 `os.pipe()` 不走 `mp.Queue`

★**它还推翻了自己的主要假说**:在真 PAR 里实测 `mp.Queue` **没坏**(8/8 children,0.25s),并明确标注这个测试**在 CPU host 上跑的,不覆盖 GPU host 上 `torch.cuda` 被碰过之后的情形**。

## 6. 🔴 红线(违反会造成真实损失,全部有今晚的实例)

```
禁 GB200 / GB300                    operator 老板明令(15:26Z)
禁 tpu enqueue / 写队列              infra-v12 停机中(§0b)
禁 xmanager.par stop                 ★本环境会崩(envelope control stream 断),用 `tpu cancel <xid>`
禁 xmanager.par list 批量传多 XID    会 segfault,一次一个
禁 BATCH 跑训练                      operator 17:16Z 重申
禁 dequeue 队列条目                  ★结构上不收敛,旧快照会把它加回来
git add 只按文件名,绝不 git add -A   树里长期躺着别人 6 个脏文件(budget_check.py 等)
不改 ~/work/{parcae-jax,trm-torch,codi-torch}  别人的 lane
```

## 7. ★我今晚抓到的判据(已被全队采纳,附出处和适用边界)

**(a) 超时常数的参照系是「这里的沉默多久会没人过问」,不是「这个操作技术上要多久」**
出处:v3 的探针按「NCCL 最慢要多久」设了每 rank 300s × 8 = 40 分钟,而这个 fleet **5–10 分钟**就会来问。⇒ 它一生中大部分时间被读成已死,**而它的行为完全符合设计**。
★**边界**:这条只在**有人在巡检**的环境成立。单机调试时不存在这个约束。
★**并且要按整个探针编制预算,不是按 rank** —— per-rank 的写法在代码里看起来完全合理,**而它藏着那个乘法**。
落点:`gpu_on_borg.md` commit `d61be44` + `66c62a4`。

**(b) 当 N 个人独立同意时,先问「是不是用了同一份清单」—— 如果是,那是 1 个证据不是 N 个**
出处:monitor + 我 + trm-v2 + parcae **四个人独立**算出「进程 2383980 可以 kill」,全部漏查子进程;maze128-v7 一个人查了 `ps --ppid` 就拦下了 —— **它不是更聪明,是用了不同的清单**。
★**推论**:**冗余检查的价值不在人数,在清单的差异度。**
★**边界**:这条针对「独立同意」,不针对「转述链」。
落点:`AGENTS.md` commit `c9aadc0`。

**(c) 限定词限定的是【你的姿态】,不是【那个数】**
出处:arc1 给了一个「粗估、带时间戳、不主张精确」的 2.1 小时,**实际错了 4.5 倍**(真值 9–10 小时),根因是它用了一段**瞬态**斜率去外推稳态。★**而那些限定词让它读起来更可信,不是更不可信。**
★**修法**:**用第二条独立路径重新推一次**;只有一条时,**限定【数值范围】而不是姿态**。
落点:`AGENTS.md` commit `17b1ab6`。

**(d) 限定词放在下一段就等于没写**
出处:gpu-v3 把「未验」写在结论的下一段,monitor 转述时只复制了结论段 ⇒ 标签丢失,而我读到那个确定语气**没有回原文核对** ⇒ **上游删标签 + 下游不回溯 = 完整的失真机制。**
★**修法**:**把两个分支写进同一个句子**,复制走哪半都带着另一半。
落点:`AGENTS.md` commit `a9dc456`。

**(e) 据转述行动前,回一趟原始来源** — `AGENTS.md` commit `c9aadc0`。

## 8. ★我自己的错误清单(新 session 最难自己获得的东西)

**我今晚自己写错 4 次,形状各不相同,但根子是同一个:我没有验我自己的前提。**

| # | 我做了什么 | 为什么会错 |
|---|---|---|
| 1 | 用 `git status --short \| head -6` 看树,报告「某个 .bak 文件消失了」 | 完整输出正好 6 行,**新文件把旧的挤出了窗口**。★**一个「消失」只有在你知道总数之后才是证据** |
| 2 | 写了「`export STAGE_WS_ROOT` 换个健康 workspace」这条规则 | ★**对队列驱动的线完全无效** —— 打包的是长驻 build-worker,用它自己启动时冻结的环境。**我写了一条读者照做也没用的规则** |
| 3 | 固化 config 四步判法时写「在**你自己的** checkout 里 `ls`」 | ★**那正是 arc1 刚推翻自己的同一个错**。**而我是在【把别人的判法写成规则】时引入的缺陷** |
| 4 | 从 `Ss`/`do_wait`/`PGID==PID` 三个状态**推断**「kill 哨兵最坏要等一个轮询周期」 | ★三个状态观测全对,**推出的行为是错的**(实测 kill 后 **7 毫秒**就死了)。**「在等」不蕴含「信号要排队」** |

★★**共同形状**:**我推翻别人时查得比查自己严。**
★**#3 最贵** —— 因为一条判法进了 wiki,**它的缺陷会被每个照做的人复制一遍**。
★**由此给我自己的规则**:**把一条判法写进共享文档前,先问「它在【谁的目录 / 谁的环境 / 谁的时刻】执行」。**

★**另一条**:「**当你在别人的东西上『补充』时,你已经默认了它的地基是对的。而『补充』这个动作本身不会触发对地基的检验 —— 它看起来是协作,实际是继承。**」

## 9. ★commit 索引(它在 git 里不会随我死掉)

**全部在 `~/work/wiki_agents/`,分支 `google-internal-migration`,已 push。**

**GPU 硬件事实**
```
2084043  B200 IMEX-exempt 从推断升为实测(device_count==8 来自运行中的 job)
1595159  删掉 GB200 per-cell 容量快照,换成规则句
c9600b8  ★GPU 上最大的存活威胁是【被错误计价】,不是抢占
2ccc4c0  那个错误价格来自 stale import(表在磁盘上对了一小时)
8d79249  PROD 挡抢占但不挡迁移,而迁移在所有状态查询里都是隐形的
2ee1464  PROD 迁移没有可规划的间隔
1585333  ★PROD 是「更耐用」不是「免疫」
```
**启动期陷阱(§The Startup Contract 这一整节是我建的)**
```
99b41f9  ★建立 §The Startup Contract
481938c  一个有默认值的 flag 是「不失败地失败」的启动阶段
2e88146  config 检查要在【条目的 workdir】里做
0db9a52  标注哪一格已有解法,并给「必死」加保质期
f0d734d  ★命名那个空格子:RUNNING 但零产出(明确【不发明判据】)
ccda13d  XM 的 RUNNING 和队列的 RUNNING 是两个不同的断言
35b6611  队列历史能区分「在等卡」和「被覆盖」;给阻塞步骤记录【进入】
d61be44  per-rank timeout 会相乘
66c62a4  ★超时常数的参照系是巡检节奏
```
**证据与观测**
```
c781da8  ★证据文件必须只追加;uptime ≠ hold time
3c5cfff  依赖版本跟着 staging workspace 走;FlashAttention 的两个条件
46c0691  ★三条 torch 线都不 pin 版本,一个 staging root 就够
5dae5ee  ★NCCL 探针从「失败」变成「卡住」;torch 版本不是诊断
0364c51  配额是按 allocation 给的
8554368  headroom=0 可能是「读不到」
```
**工具与共享状态**
```
d26af16 → 11d283e → ec2cc91   ★同一条改了三版:CUDA build 会重指 blaze-bin
2e99524  staging hatch 只对你自己的 shell 有效
fb98917  /proc/environ 只显示父进程交给它的(正负控制验过)
bb1d79e  等价的算力不等于等价的价格
70c4877  srcfs:先找本地写者再怪 backend
743c8a6  monitoring:每个 run 都要有标题,并验证它落地了
```
**方法论(`AGENTS.md`,★v45 已定「到此为止」)**
```
e66f30a  ★时间维度的陷阱 + | head 吞内容 + 失败复现要复现条件
a9dc456  限定词写进被限定的句子里
c9aadc0  据转述行动前回原始来源 + 数方法不数人
17b1ab6  ★对数值 hedge 范围而不是姿态
```

## 10. 待办 / 未决

| # | 事项 | 卡在什么上 | ★什么会证伪当前判断 |
|---|---|---|---|
| 1 | **NCCL 8 卡** | 正在验(XID 284429699) | ★心跳里出现 `nccl_all_ok: true` ⇒ 通了。**只认这个** |
| 2 | **删除 GB200/GB300 选项** | 已转 infra-v12,**等开机** | ★**陷阱**:`tpu_wrapper.sh:171-172` 是**价格上限表**,删掉 = 从「有 20 的上限」变成**没有上限**。要的是 enqueue 入口**硬拒绝** |
| 3 | GB200 IMEX 授权信 | 已写好在 v3 的 artifact | ★**老板已禁 ⇒ 大概率不用发** |
| 4 | flash_attn | ★**已结案:不需要** | 将来若要用:visibility 限制在 friends 包组,experimental target 会在 analysis 阶段失败 |
| 5 | 队列覆盖 bug | infra-v12 重写中 | ★根因在 `merge_and_save_touched` + `run_reroute` 的 `return entries` |
| 6 | v3 退休后的 GPU 提交权 | ★**需要 monitor 裁定** | 不要默认它归了我 |

## 11. 我名下的活物

```
job / 队列条目 / crontab:  ★全部 0
后台进程:                  ★0
subagent:                  ★fresh-sloth(NCCL smoke,ongoing)· sunny-pelican(BATCH,已完成)
未提交的改动:              ★0(树里 6 个脏文件是别人的,一字未碰)
```
★**我全程只读、零队列写入。这不是纪律,是 lane 边界的副产品** —— 请诚实地这样理解它。

## 12. 一句给接手者的话

★**这条线最大的价值不是写了多少文档,是【顶回了多少条不该照做的指令】。**
今晚 monitor 换了 4 任,我顶回上级 5 次、被顶回 3 次,**每一次都让结论更准**。
★**如果新来的指令和你实测到的东西冲突,先停下报告,不要照做。**