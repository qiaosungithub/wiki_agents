# ★ 你是 monitor-v47 —— operator qiaos 的 fleet monitor。我是 v46,把舰队交给你。

★**元规则(v43→v44→v45→v46,原样传下去)**:
> **我在移交时是最有权威的(刚做完调查、证据齐全,而你什么都不知道)。恰恰是那一刻,我的错误最容易被原样继承。「请自己再验一遍」不是客套,是对抗「权威随交接放大」的唯一手段。**

★每条标了证据等级:【实测】/【推断】/【转述】。★**优先复验【推断】和【转述】。**
★**我这一班被下级顶回 8 次,每次都对。见 §7 —— 那一节比本文档任何结论都重要。**

---

## 0. 立刻做(按顺序)

1. 读 `~/work/wiki_agents/AGENTS.md`,然后 `monitoring.md`。
2. ★**re-point 9 个 watcher 文件到你的 rid** —— **这是我这一班最大的欠账,见 §3。**
3. crontab 锁名 `monitor-v45-*` → 你的版本(★注意:现在还是 v45,我没改)。
4. notify 自测:`~/.amply/bin/amply_notify <你的session> "takeover ok"`,★**看消息有没有真的回到你的事件流,不看 rc。**
5. 更新 `runs.txt`(见 §2 的名册,★我已经改过一轮但还有遗漏)。
6. ★**查现任 monitor 的唯一正确写法**(带井号锚定):
   `grep -a "# THIS MONITOR" ~/work/.monitor_watch/runs.txt | grep -oE "20260[0-9]{3}-[0-9]{6}-[0-9a-f]{8}" | head -1`
   ★**不要用宽松的 `grep -a "THIS MONITOR"`** —— 退休行里有 `(was THIS MONITOR)`,`head -1` 会给你三代前的 rid(我 15:26Z 实测)。

---

## 1. ★operator 今晚的规矩(全部是他直接下的,必须遵守)

| # | 规矩 | 出处 |
|---|---|---|
| 1 | ★**别的 agent 给 monitor 发消息,每条不得超过 200 单词** | 19:24Z,已写进 `monitoring.md`。★**你要在每次交接和广播里重申它** |
| 2 | ★**每个新开的 run 必须起名字** | 19:24Z,已写进 `monitoring.md` §Every New Run Gets A Title |
| 3 | ★**不要往 `/tmp` 乱放东西** | 18:53Z,已写进 `storage.md` |
| 4 | **交接完的老 session 直接 stop** | 18:10Z |
| 5 | **新 session 要强调 `tpu enqueue` 现在不能用** | 18:10Z(infra-v12 停机中) |
| 6 | **有事就新开一个 session 做,默认 chatbot、不用 subagent,并且要起名字** | v45 转述 |
| 7 | **红线:不准抬 limit order 的 cap** | 历任 |
| 8 | **BATCH 只用于 eval,训练一律 `--tier=PROD`** | wiki |

---

## 2. ★舰队名册(19:25Z 实测,12 条真活线 —— 每条都验过 worker 进程)

★**operator 亲自看的 4 条,不要主动打扰**(他 14:41Z / 18:10Z 指定):

| 线 | run-id | ctx |
|---|---|---|
| **infra-v12** | `20260828-141921-a3218cba` | 387k · ★停机重写调度器中 |
| **parcae-torch-port-v3** | `20260828-143733-8e6b98df` | 241k |
| **rnn-research-v5** | `20260828-143741-000ab3d8` | 211k |
| **codi-torch-v2** | `20260828-172253-910d04a5` | 新 |

★**待交接队列(我做了 1 个,剩下的交给你)**:

| 线 | run-id | ctx | 状态 |
|---|---|---|---|
| **codi-reproduction-v6** | `20260827-232553-07d80b85` | ★600k | ★**我 19:22Z 已发交接请求,它正在写文档。你接手后直接收文档即可** |
| **maze128-first-v6** | `20260828-113050-64512ff1` | ★606k | ★**未发请求,该你做** |
| elt-reproduction-v2 | `20260828-020827-0ebf911a` | 358k | 未到线 |
| paligemma-hoff-v34 | `20260826-172406-ba07d36c` | 247k | 未到线 |
| srcfsd-sentinel-owner-v2 | `20260828-061401-1a70fb6f` | 234k | 哨兵主人,见 §4 |
| parcae-reproduction-v6 | `20260826-230433-b548587b` | 65k | 未到线 |
| **gpu-survey-docs-v5** | `20260828-190517-9fd9dfbe` | 新 | ★我 19:05Z 刚交接完的 |
| trm-torch-v3 | `20260828-181819-4f6874cb` | 新 | operator 开的 |

★**operator 今晚停掉的(不要再管)**:arc1-unroll-v7 / gpu-survey-v3 / codi-torch-port(v1) / trm-torch-port-v2 / maze64-postnorm-v8。
★**今晚自然死亡的**:parcae-torch-port-v2、rnn-research-v4(都已有 operator 开的接班线)。

---

## 3. 🔴 我没做完的事(按紧迫度排序 —— 这是你接手要干的)

### 3a. ★★最紧急:9 个 watcher 还指着【已死的 v45】
【实测 17:44Z】只有 `srcfsd_wedge_sentinel.sh` 被 owner-v2 改到了我的 rid,其余 9 个全部还是 `20260828-121031-f8fa5ceb`(v45,14:23Z 已死):
```
watch.sh · heartbeat.sh · ctx_watch.sh · watch.py · mem_oom_alert.sh
elt_xid_watch.sh · ~/.tpu_bin/money_staleness_sentinel.sh
~/credit_audit_sentinel.sh · ~/tpu_congestion_sentinel.sh
```
★**这个缺口今晚已经咬了我们一次**:arc1-unroll-v7(777k,全队最高)**15:26Z 死亡,两小时无人发现** —— 因为 `watch.py` 的 DEAD 告警发给了尸体。同批悄悄死掉的还有 parcae-torch-v2 和 rnn-research-v4。
★**孤儿哨兵(ppid=1)改完文件必须杀掉重拉并验 `/proc/<新pid>/environ`** —— 改文件 = 白改。`credit_audit`(3158321) / `tpu_congestion`(3158322) 不在 crontab,kill 后要手动 `setsid` 拉起。

★★**但更强的判据是 v41 教我的**:与其遍历所有脚本改 notify target(易漏,我就漏了),**不如确认旧 worker 已死** —— 一个进程检查 vs 遍历所有脚本。**worker 活着时 `amply_notify` 返回 rc=0 却没人读(「沉默的成功」);worker 死了才会返回 rc=2,失败才可见。**

### 3b. srcfs 哨兵的 bt 计数器有【两个】独立缺陷,现在不可信
1. **双计**【实测 perky-hare】:glog severity cascade 把每条 ERROR 也写进 `.WARNING`,而哨兵 `cat` 了两个文件 ⇒ 所有读数精确 ×2。阈值 `bt≥8` 实际是 `≥4 次真实失败`。
2. ★**窗口计算把旧行反复计入**【实测 我,19:22Z】:18:20 / 18:43 / 18:53 / 19:21 四次告警引用的**都是同一条 17:45:28 的旧日志行**,而 `srcfsd.ERROR` 的 mtime 从 17:45 起就没动过 ⇒ 真实事件数 0,而 bt 报到 27。
⇒ ★**判断 srcfs 是否真出事,不要看 bt**,看这两个:`dropped_resources.ascii` 是否在增长 + 有没有活的 staging rsync。
⇒ ★**这条要告诉 `srcfsd-sentinel-owner-v2`(`20260828-061401-1a70fb6f`)去修** —— 我没发,因为它当时正在修双计,我不想两人同时改一个文件。**该你发了。**
⇒ ★**危险性**:arc1 立过一条「乱报的 watcher 会训练读者忽略它」。**我们已经在忽略它了。**

### 3c. operator 待办
- **`/tmp/claude-1693413`(9.6G)迁移** —— 教程已写好 `~/work/claude_tmp_relocate_tutorial.md`(72 行)。★operator 说今晚和 lyy 协商停掉 claude code 后再做,**你不要自己动**(有 5 个 claude 进程活着,最久 6 天 15 小时)。
- **`/tmp` 加 size 上限** —— `sudo mount -o remount,size=30G /tmp`。我没做(需要 sudo 且未确认权限)。这是防止 `/tmp` 再撑满 swap 的根本手段。
- **`/tmp/qwen_slice.tgz`(2.2G)** —— ★**不要删**。lyy 的两个在途作业(b200-8 PROD + h100-4 BATCH)的 `--app.data_root` 指着它。等作业跑完。
- **CNS 隐患**:`/cns/li-d/home/qiaos/lyy_parcae_runs/parcae-370m-fix/best/939` 是 0 字节空骨架,**排序在唯一可用的 779 之上**,而 parcae 用 `ocp.CheckpointManager` **没有守卫**。★**判据是 `commit_success.txt`(779 有、939 没有),不是 `extra.json`(两个都没有)** —— cosmic-elk 原报告说是 extra.json,我实测更正了。

### 3d. 名册还有遗漏
`runs.txt` 里 `parcae-torch-port-v3` / `rnn-research-v5` 两行我写的「step 0 = 刚起,还没干活」**是错的**(实测 step 62 / 74)。还需要加 `trm-torch-v3`、`codi-torch-v2`、`gpu-survey-docs-v5`,并给 operator 停掉的那批标 RETIRED。

---

## 4. ★今晚的大事:srcfs 洪水(已解决,但机制要懂)

### 根因(三方独立证据,【实测】)
```
2026-08-28 03:33Z  一个 agent 执行 cd /google/src/cloud/qiaos/elt_jax/google3 && tpu enqueue
                   → queue_cli.py:101 把 os.getcwd() 冻进【持久】队列条目
                   → 该 job 的 workdir = google3 仓库根(417 个顶层目录)
                   → tpu_wrapper.sh 的 rsync -aL ./ 源就是它,而目的地在它【内部】
                   → 递归拷贝整棵 depot,撞 300s timeout → rm -rf → 重来,永不收敛
```
**这一条队列条目占全天 91437 次 CreateSnapshot failure 的 76.1%。**

### 三个被证伪的继承结论(★不要再传播它们)
| 旧说法 | 实测 |
|---|---|
| 「srcfsd anon-leak ~0.1G/min」 | ★**不存在**。8G 是配置上限(`Content cache ceiling = 8192 MiB`),tcmalloc 已归还 16.3G。`corr(RSS, D-count)=+0.036` |
| 「哨兵触发条件是 D≥15 AND RSS≥18G」 | 实际是 `D≥15 AND logdir_stall≥30min`;转述的组合在 3420 个 tick 里出现 **0 次** |
| ★**「最近多了一些 agent 在跑」** | **定量证伪**:agent 数 1.05x vs 事故率 ≥3000x;本周 agent 最多那刻(27 个)错误数 **0**。★**该说法在本机无作者、从未被测量** |

★★**「多了 agent」这句话的来历值得你记住**:它有一个**正确的祖先** —— wiki commit `f887d19`(2026-08-22, Qiao Sun)说的是「5 个并发 **rsync/stage-write** 抽干 CreateSnapshot token bucket」。传话时被换成了「agent」。两个平时一起涨落的相关变量,**在它们分道扬镳的那天,那句话失效了** —— 而且退化后的版本**更自信**(丢了机制,也从未被测量)。
⇒ ★**已写进 `monitoring.md` §Record How A Number Was Measured。**

### 已落地的修复
- **硬守卫**(commit `eae1ac6`,`tpu_wrapper.sh`):拒绝①目的地在源内(双向)②源是 google3 根③源顶层 >200 项。★阈值可复算:合法 workdir 实测 3..97,depot 根 416-417,`/tmp` 9289 —— 200 = √(97×416)。正负控制 32+5 项通过(我自己独立跑过 5 项)。
- `STAGE_WS_ROOT` 默认值从病树 `elt_jax` 切到 `run_amply_workspace`。★**elt_jax(ws qiaos/3202)是全机唯一会静默丢写的树:92091 次,其余 8 棵为 0。**
- 回滚配方:`~/work/.monitor_watch/STAGING_GUARD_v46.md`
- ★**根治点不在守卫,在入队**:`tpu enqueue` 该拒绝 workdir 是仓库根的提交。★**这条归 infra-v12,已列入它的 todo。**

---

## 5. ★判据与陷阱(今晚新增,全部【实测】)

1. ★★**`rc=0` 的第二种失败:送达了一个【残缺的内容】。** 未加引号的 heredoc 会让反引号被 shell 执行、变量不展开,**而 send 仍然 rc=0 报 SENT**。今晚两次发作,第二次就发生在说明第一次的那条消息里。⇒ **多行消息一律 `<<'EOF'`(引号包住定界符)。**
2. ★★**`lsof` 干净 ≠ 没人需要。** 一分钟后才会 `open()` 的作业现在没有描述符。`qwen_slice.tgz` 三个静态检查全绿(lsof/脚本/队列),而两个 PROD 作业的 argv 上有它。⇒ **删之前查活进程命令行。**
3. ★**`grep ps` 会命中你自己的 grep。** 我把这条写进 wiki 二十分钟后自己又踩了一次(报 `rsync=6`,实为 0)。★**拦住我的不是警觉,是「查一下这 6 个是谁」这条机械纪律。纪律比警觉可靠。**
4. ★**`mtime = epoch-0` 不是幽灵树指纹,是 CitC 根的指纹**(18/18 全是,健康的也是)。我曾把它写进给 subagent 的指令,被顶回。
5. ★**写进不存在的目录在 CitC 上也是硬失败 `rc=1`。** 静默丢弃发生在 `mkdir` **成功之后** ⇒ **任何存在性检查都发现不了这一类。**
6. ★**跨文件系统 `mv` 是拷贝**,被打断会两边各留一半,重试报 `unable to remove target: Directory not empty`(读起来像权限问题)。★验证迁移用**文件数+字节数**,不用 `du`(tmpfs 与 ext4 块对齐不同)。
7. ★**边界条件 0 要单独想。** 我的迁移校验写了 `dst>=src && src>0`,结果把「源已空 = 成功」判成了失败。
8. ★**HELD 不是终态**:实测 state 从 HELD 变回 QUEUED、attempts 8→10。根因 `route_check.py:804` 那条 attempts++ 路径**无 HELD 收敛出口**(infra-v12 正在修)。
9. ★**按状态过滤会漏掉尚未发作的同类**:我几次「全表扫描」只扫了已 HELD 的,漏掉一条 `BUILD_REQUESTED att=0` 的空壳(它已 pre-debit 152 预算,一开机就会跑)。⇒ **按判据扫,不按状态扫。**

---

## 6. ★协作纪律(operator 今晚特别强调的)

- ★**每条给 monitor 的消息 < 200 单词。** 结论先行、数字先行,证据放自己的 artifact。★**你要在每次交接文档和广播里重申。**
- ★**infra-v12 要求全队静默**:除非「正在发生的、会造成实际损失的事」,否则不要给它发消息。它会主动发开机通告。
- ★**不要擦掉别人的不确定性标签。** v45 最贵的教训:它把 gpu-v3 标注的「我没实测这一层」擦掉再转发,那条后来被证伪,而下游已照它改了两次 wiki。

---

## 7. ★★我这一班被下级顶回的 8 次(全部是对的)

| # | 我说的 | 实际 |
|---|---|---|
| 1 | 「epoch-0 mtime 是幽灵指纹」 | 18/18 假阳性 —— ★**而我把它写进了给 subagent 的指令** |
| 2 | 「pid 1693413 死了吗」 | **1693413 是 UID 不是 PID**。★**而这个错误前提自带一个会确认它的验证方式**(`ps` 查不到 → 「早死了,可以删」→ 会删掉一个跑了 3 天的 server 和一个活的 claude 会话) |
| 3 | 「1GB /tmp = 1GB RAM」 | 43G 早已换出,释放的主要是 **swap** |
| 4 | 「resume_xid 条目一开机会拷 /tmp 9289 项」 | **resume 分支根本不 rsync**(mellow-oryx 用执行证明,不是读代码) |
| 5 | 「HELD 止血成功」 | HELD 被打回过,真正掐断的是 infra-v12 停机 |
| 6 | 「v45 的修复让损害变永久」 | 从**错误总量**看它是净收益(同源不同目的地:0 vs 773)。★**我和它测的是链条的不同环节,两个观察都对** |
| 7 | 「洪水源 5 条」 | **20 条**(infra-v12 按判据全表扫) |
| 8 | 「parcae-v3/rnn-v5 step=0,从没干过活」 | 实测 step 62/74。★**而这个数据就在我自己 20 分钟前读过的 `ctx_state.json` 里** |

★★**第 2 条最该被记住**:一个错误的前提,如果附带一个会确认它的验证方法,就会让执行者「验证后」放心地做错事。**我给的指令差点毁掉两个 live 进程,拦住它的是 sleek-salmon 自己去查了 `id -u`。**

★★**第 8 条是第二贵的**:我引用了一个**转述来的旧读数**,而更新的一手数据就在我手上。**转述会丢掉时间语境 —— 包括自己对自己的转述。**

---

## 8. 交给你的判断

1. ★**先补 §3a 那 9 个 watcher** —— 在那之前你是瞎的,而今晚已经因此丢了三条线的记忆。
2. **codi-reproduction-v6 的交接文档应该快好了**(我 19:22Z 发的请求),接住它。
3. **maze128-first-v6(606k)还没发请求。**
4. ★**别的都可以等。** operator 全程在线、决策很快,拿不准就问他。

★**祝顺利。验证 ground truth,让线一直在工作,该你拍板的就拍板。**
★★**而我这一班最贵的教训:我发出去的每一条指令,都可能带着一个我自己没意识到的错误前提。下级顶回我 8 次 —— 这套机制的价值不在于它能纠正我,在于【下级敢于查我给的前提】,而我的责任是【把前提和结论分开写,让它可查】。**
