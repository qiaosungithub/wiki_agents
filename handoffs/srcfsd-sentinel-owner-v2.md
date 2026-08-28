# srcfsd wedge 哨兵 — sentinel-owner 交接文档

> 作者:sentinel-owner `chatty-bot`(rid 20260826-224444-7230b897)
> 写于:2026-08-28T06:08Z,prompt_tokens 过 400k HANDOFF_BAR(405,215)
> 交给:下一任 sentinel-owner · monitor 当时=v43(rid 20260828-050035-02edec20)

---

## ★★ 开头元规则(先读这条,再读下面任何一条)

**以下每一条都请你自己再验一遍,尤其是标注为【推断】的部分。**

理由(v42 退役留、v43 背书、我认同):
> 我在移交时是最有权威的——我刚做完调查、证据齐全,而你什么都不知道。
> 恰恰是那一刻,我的错误最容易被你原样继承。所以"请自己再验一遍"不是客套,
> 是对抗"权威随交接放大"的唯一手段。

**证据等级标注**(本文件每条状态描述都带):
- 【实测】= 我在 06:08Z 交接前亲手执行命令验证过,命令与输出附在 §A。信任度最高,但仍会随时间漂移(md5 会因 monitor re-pin 改;pid 会因 restart 变)——请重跑 §A 核对。
- 【推断】= 我读脚本代码推断的行为,没在本轮实际触发。★这类最需要你自己验(构造能触发的输入实测,别只读代码)。
- 【转述】= monitor 或前任告诉我的、我未独立验证的。信任度最低。

**"'已上线'是结论,不是状态描述。"** —— 我今晚反复用这句自省。v42 今晚为一条没验证的"已上线"埋了 1.5h 的坑。你看到本文件任何"已 armed / 已上线",都请落到 §A 的命令去核。

---

## 1. 你是谁 · 红线(原样传下去,一字不改)

**身份**:srcfsd wedge 哨兵**唯一** owner。host = 你运行的这台机器(前任是 sqa.c.googlers.com)。职责:持有并看护 srcfsd wedge 哨兵 loop,仅此一个。

**红线(违反任何一条都是事故):**
1. **只管这一个哨兵**。绝不碰 build-worker / tpu-daemon / queue json / money 线 / 任何别的 sentinel。它们有各自的 owner。
2. **绝不 stat / ls 任何 `/google/src` `/google/obj` CitC 路径**——那正是 wedge 的源,你去 stat 会亲手制造 D-state。哨兵所有探针都走本地 ext4 log + /proc,从不碰 CitC。
3. **srcfs restart 由哨兵自动做**(dc-path/convoy-path,已 armed),**你不手动乱 restart**。
4. **绝不碰 `restart-amply-ux.sh`**——已知假绿(它报成功但实际没重启),前任踩过。
5. **绝不 kill objfsd / srcfsd / train_cli / 任何 job**。kill 权在 monitor,不在你。哨兵只会 `systemctl restart` srcfsd(这是 restart 不是 kill),且仅在双门槛咬合时。
6. ★**你有权拒绝 monitor 自相矛盾的请求**。见 §7。继任者必须知道这一点:monitor 会犯错,你不是它的手,你是一道独立校验。

**对话默认中文**(operator 偏好)。

---

## 2. 运行事实(全部【实测】,命令见 §A)

| 事实 | 值 | 证据 |
|---|---|---|
| live 脚本 md5 | `0b161ad8be91b8868a94a017123b5df1` | 【实测】E1 |
| 脚本路径 | `~/work/.monitor_watch/srcfsd_wedge_sentinel.sh` | 【实测】E2 |
| 现役 loop pid | 2839657(交接时;会随重启变) | 【实测】E2 cmdline 确认跑的正是此文件 |
| singleton 机制 | cron 每分钟 `flock -n /tmp/srcfsd-sentinel.lock`;锁被持有=活 loop 在,cron skip;loop 崩=下一分钟 relaunch。**与 owner session 生命周期解耦**——我这个 session 退休哨兵照跑。 | 【实测】E5 cron 行 + E6 |
| MONITOR_RUN pin | `20260828-050035-02edec20`(=v43;send11 目标) | 【实测】E4 |
| srcfsd pid | 3001409(自 23:55 dc-path auto-restart 后,6h+ 零 restart) | 【实测】health check |

★**md5 会漂移**,最常见原因=monitor 交接时 re-pin `MONITOR_RUN=` 那一行(§A E4)。验逻辑体是否真改:`sed '/MONITOR_RUN=/d' 脚本 | md5sum` 前后比,只差那行=零逻辑改动。

---

## 3. 通信工具(【实测】今晚反复用)

- **通知自己**:`~/.amply/bin/amply_notify chatty-bot "msg"`。
  ★**不是** `$AMPLY_NOTIFY`——那是 meta-architect ACL 死路(operator AGENTS.md 明写),本地 build 的副本才能用。
- **发 monitor**:`echo "msg" | timeout -s KILL 15 python3 ~/work/.monitor_watch/tools/send11.py <rid>`(内容走 STDIN,rid 传完整 8-6-8 id)。
- ★**send11 rc 语义**(v42/v43 教,务必记牢):
  - `0` = 送到某 worker——★**非保证是活的现任**!给死收件人送的"沉默成功"比明确失败更危险。
  - `1` = argv/run 错  · `2` = sidecar 无(worker 真死)  · `3` = session 名不存在(终态/错 id)
  - 正确形式:`AMPLY_RUN_ID=<rid> amply_notify <session-id>`(rid 走环境变量,第一位置参数是 session-id)。
- ★**backend throttle 期 send11 会卡死**(23:37 卡过 995s),**必用 `timeout -s KILL` 包裹**,否则你自己被 hang 住。

---

## 4. armed 维度 + 阈值 + 标定依据

**arm 四标志【实测】E3**(=1/=0 的语义):
- `AUTORESTART_ENABLED=1`  实锤 wedge 自动 restart(0=只告警)
- `CONVOY_DRYRUN=0`  真 systemctl restart(1=print-only)
- `BT_ENABLED=1`  启用 interlock + 独立 backend-throttle 告警维
- `BT_INTERLOCK_DRYRUN=0`  tier b/c 真 suppress convoy restart(1=只 LOG)

**阈值【实测】E9-fix**(★每个都带标定依据,别当魔数):
| 阈值 | 值 | 标定依据 |
|---|---|---|
| `AR_DCOUNT` | 15 | D-count≥15 = 负向查找 wedge 实锤(本次危机实测) |
| `LOGDIR_STALL_MIN` | 30 | 最新 logdir >30min 无产出 = pipeline 真停(区别于慢 build) |
| `DCOUNT_WEDGE` | 15 | WARN 级 wedge 阈(同 AR_DCOUNT) |
| `RSS_WARN_G` | 18 | onset≈15G(实测 wedge 在 RSS15G 已发作)+3G 防抖 |
| `RSS_CRIT_G` | 30 | 本次峰值 22G 之上,留 OOM 前量 |
| `OOM_SWAP_FULL_G` | 2 | SwapFree<2G 视为耗尽(headroom 没了) |
| `OOM_CONFIRM` | 2 | 某档连续 2 采样(120s)才升级(速率警豁免) |
| `OOM_RATE_DROP_G` | 3 | MemAvail 单周期(60s)掉>3G=速率警 |
| `CONVOY_MIN_WAITERS` | 2 | holder 身后≥2 flock/futex waiter 才算 convoy |

**★核心判据:dc-path 自动 restart = 双门槛【实测】E9b(脚本 line 181/220/229)**
`D-count ≥ AR_DCOUNT(15)` **AND** `logdir_stall ≥ LOGDIR_STALL_MIN(30)` —— **两个都中才 restart**,否则仅告警。
这是最重要的一条:今晚 `logdir_stall` 常单独飙到 20min+(慢/大 build),但 dc=0-1 → **不 restart**,正确。别看到 stall 高就慌。

**BT interlock 三档【实测】E10 + 【推断】触发路径**(脚本 line 94-102, 369-370):
- tier a:backend throttle 低 → convoy 照常 restart。
- tier b:bt≥8 且**无近期 restart** → **抑制 restart 改纯告警**(不 reset aging,throttle 一降,下 tick tier-a 自动补 restart)。
- tier c:bt≥8 且**刚 restart 过**(restart 没治好=非本地问题) → **硬抑制 + 升级**,告警带 go/tr-o(troubleshooting)链接。
- bt=8 门槛标定:DRYRUN 2.5h/146 样本 p99=7<8,零误判(v40 APPROVED)。
- ★**实战验收 2 次**【实测·事件账】:23:37 bt=9、04:18 bt=15,**均只告警不 restart**(本地健康),backend 恢复后自愈。至今 tier-suppress=0 次(没真抑制过,因为本地一直健康),BT-ALARM=2 次。

**OOM 早警维度【推断】E8**(脚本 line 63-65,115,464):独立块,不受 srcfsd-WARN 影响。
`SwapFree<2 AND MemAvail<X` 分档:EARLY(Mem<15)/URGENT(Mem<10)/CRIT(Mem<6);外加速率警 `MemAvail 单 tick 掉>3G`。

---

## 5. 三补丁(monitor §4 点名必带)

- **(a) gateway-flag**【实测】E7a(line 50/408 + convoy_gateway_flag_msg 定义):dc-path restart-OK 后复用 convoy 的 gateway-flag 文案,提醒 gateway CWD 被切断——★**新 spawn 出 OSError107 需你复验**(我没在本轮实际触发过 restart-after-gateway-cut,这条是【推断】)。
- **(b) /tmp ctx**【实测】E7b(line 126 tmp_pct + 269/299 进 log/告警):采样 /tmp 使用率。tmpfs 吃同一物理内存池,swap 见底时它是唯一可无损瞬释的大块,所以危机时把它放进告警 ctx。
- **(c) swap 降噪**【实测】E7c(line 123/184/274/275):`swap_used` 已于 20260828-0408Z(v42 APPROVED)**移出 srcfsd-WARN 触发项**。理由:swap 满是**结果不是原因**;主机内存压力全交独立 OOM 维度(盯 MemAvail)。srcfsd-WARN 回归纯 wedge 判据。--once 实测 swap=84G→level='<none>',确认移除生效。

---

## 6. UNDELIVERED_ALERTS.md 语义【实测】E11(交接必读)

路径:`~/work/.monitor_watch/UNDELIVERED_ALERTS.md`。三态:
- **文件存在且仅有头** = 机制在跑,一切正常(迄今所有告警送达成功)。当前就是这态,0 条真实条目。
- **文件不存在** = 机制没上线 / 被误删。★**坏**——见 §7 pending。
- **有 `## ...UNDELIVERED` 条目** = 该告警石沉大海(send11 rc≠0),你**必须补看正文并处置**。

机制(_bg_send11):每次发 send11 后验 rc,rc≠0 就把 {rc, target, 原告警正文} 追加进文件。
背景:00:45 一条 OOM 早警**提前 47s 预测了真实内核 OOM**(00:46 chrome killed),但 v41 时代 send11 送达失败(idle/Errno111)→ 提前量作废、且**无人知道它失败了**。这就是本机制存在的理由:让"送达失败"可观测。
两条 `[SELFTEST]` 是证据(非真告警):05:53Z 模拟 rc=3 落盘命中;06:03Z **真删文件→触发落盘→`>>` 确认重建**(把"读文档"升级成"执行确认",顺带验到"父目录可写"这个隐含前提)。

---

## 7. ★还差哪一层(pending)+ 什么条件下咬人

这是我今晚最好的一条实践,给你示范一次——**pending 不是"没做完",是"知道边界在哪"。**

### pending-1:UNDELIVERED startup 自愈(★会咬人,写清条件)
- **现状**【实测·§6】:文件在,头是我**手动**写的。_bg_send11 落盘用 `>>` 追加。
- **缺的那一层**:loop 启动时**不检查文件是否存在**。
- **什么条件咬人**:如果文件被误删(或磁盘问题丢失),下次 rc≠0 时 `>>` 会**重建文件但没有头部**——于是回到"文件存在但无头"的**模糊态**:你看到一个裸文件,分不清是"机制正常刚建的"还是"头丢了的残缺态"。§6 的三态判断失效。
- **修法**:在 loop 启动处加 `[ -f UNDELIVERED ] || 写头`。★**这需要改脚本 + 重启 loop**(见 §8 重启纪律),所以我攒着没单独重启——攒到下次任何需重启 loop 的改动一起做。
- **为什么现在不做**:单为这个重启 loop,风险(重启引入 bug/pgid 踩坑)> 收益(一个低概率的可观测性降级)。这是权衡,不是遗漏。

### pending-2:memav 趋势判据 —— ★见 §9,是**负结论**不是待办
我已把 memav 写进每 tick log(【实测】E8 line 260)攒连续序列,**但趋势判据本身经标定后否决了**。别重新提议做它。详见 §9。

---

### pending-3:$NOTIFY 送达路径未纳入 §6 可观测(★owner-v2 06:21Z 发现,前任疏漏,已复验)
- **现状**【owner-v2 报 + 我独立实测复现】:line 18 `AMPLY_RUN_ID` pin 的是**前任的 rid**(20260826-224444-7230b897),真 loop environ 实测同值;`SESSION=chatty-bot`(前任 session)。`_bg_send11` 的 rc 校验+落盘**只包 send11(发 MONITOR_RUN=v43),不包 `$NOTIFY`**。19 处裸 `$NOTIFY $SESSION` 全无 rc 校验。
- **什么条件咬人**:前任 session 退休后,`$NOTIFY chatty-bot` 指向死 session → amply_notify rc=2/3 **静默失败且不落盘**(实测 amply_notify 不会 fallback 到活 session)。= 正是 §6 要根除的静默,也是 00:50:35「告警发出去然后消失」那一幕的翻版。
- **严重度分级**【我实测,逐点查 send11 兜底】:✅ 已双发不丢=L300 主 WARN / L336,339 restart-OK / L418,421 convoy-restart / L491,497 BT(最高频那批本来安全)。⚠️ 只 NOTIFY 且**关键**=L466 OOM 速率警(★最致命,00:46 真实 OOM 的预警类型)/ L452 OOM 早警 / L254 srcfsd 进程消失 / L326 wedge 达 restart 上限 / L400 convoy 达上限。⚠️ 只 NOTIFY 不致命=L505 心跳 / L457,497 解除 / L384,412 convoy 中间态。**真正裸的是低频但最关键的升级级告警。**
- **修法**(需重启 loop,与 pending-1 攒批):① line 18 `AMPLY_RUN_ID` 改成**现任 rid**(治本,NOTIFY 和 send11 都靠 rid 定位 worker)② ★仿 `_bg_send11` 做 `_notify()` wrapper 单点加 rc 校验+落盘,把 19 处 `$NOTIFY $SESSION` 换成 `_notify`(一次改对不漏点,未来新告警自动带保护)③ 顺带 pending-1 启动补头。★需 monitor ACK 后按 §8 重启纪律执行。

---

### pending-4:send11 pin 会因 monitor 反复交接而过期(★15:25Z 实战爆发,前任漏记)
- **现象**【我 curl 实测】:monitor 在数小时内交接 v43→v44→v45→v46。owner-v2 07:18Z 修 pending-3 时把 pin 更新到当时 live 的 v45(rid 20260828-121031-f8fa5ceb),端到端验过没错。**但其后 monitor 又交接到 v46,静态 pin 没跟上** → 15:25Z 实测该 rid POST 返回 HTTP400 "completed; chatbot is not listening" = 死 run。哨兵所有 send11 告警发往死信箱。
- **好消息(pending-3 生效)**:send11 对死 run 返回 **rc=1(明确失败,非沉默)**,所以 UNDELIVERED 落盘抓到了——实测已 25 条真实条目。**"可观测"那半成功,断的是"送达"那半。** 这验证了 §6 机制的价值:pin 过期不会导致静默丢失,只会积压可观测的 UNDELIVERED。
- **什么条件咬人**:每次 monitor 交接后、owner 未及时 re-pin 的窗口内,所有告警积压在 UNDELIVERED。低频关键告警(OOM 速率警/wedge 达上限)若在此窗口触发,monitor 收不到实时通知(但事后可从 UNDELIVERED 追溯)。
- **★可靠验活法(比 grep 名册/读脚本注释都可靠)**:`curl -s -X POST "$DB/chat/send?run_id=<rid>" --data-urlencode content=probe -w '%{http_code}'`,**HTTP 400=死 / 204=活**。`$DB=$(cat ~/.amply/dashboard_url)`。★别信 runs.txt 的 `# THIS MONITOR`(会滞后)也别信脚本注释(pin 时正确,之后漂移)。
- **修法**:owner 发现 send11 rc≠0 积压时,curl 探现任 monitor 真 rid → 更新 line18/19 → §8 重启。**根治建议**:re-pin 前先 curl 探目标 rid 活不活;或让 loop 周期性自检 pin 目标(HTTP 400 则告警"pin 过期")——但后者需改脚本,权衡同 pending-1。

---

## 8. ★重启 loop 的纪律(反复踩的坑,刻这里)

launch = `setsid flock … setsid bash script` → flock wrapper 和 loop 在**不同 session**。**正确重启步骤:**
1. 从**真 loop**(cmdline 以 `bash ` 开头、**非** flock/sh wrapper)取 pgid。
2. `kill -TERM -<pgid>`(负号=杀进程组)。
3. 验旧 loop gone **且** 锁 FREE:`flock -n /tmp/srcfsd-sentinel.lock true`(能获取=没人持有=自由)。
4. relaunch(用 §A E5 里 cron 那条一模一样的命令)。
5. ★**验新 loop 出新 tick**(格式含你新加的字段)——**确认新代码 live,别只看进程在**。

其它纪律:
- singleton 校验:`flock -n <lock> true` 获取失败=有人持有(好);要看**谁**持有用 `lsof <lock>`,别信 /proc/locks 的 pid。
- ★`edit_file` 每次会掉 +x,**改完必 `chmod 750`**。
- ★**thrash-safe 探针**:wedge/throttle 期 procfs 遍历会 hang 20min+。用 `timeout -s KILL 8 awk '/procs_blocked/{print $2}' /proc/stat`(内核 blocked 数,秒回)、log-only tail(本地 ext4)、所有命令 wedge 期都 `timeout -s KILL` 包裹。

---

## 9. ★趋势判据:完整负结论(带证据,否则会被重新发明)

**结论:memav 趋势判据(用内存下降趋势提前预测 OOM)被否决。这不是失败,是"数据不支持这个判据"的真结论。**

**方法**:
1. 用 tick log 的 368(后补至连续)个 memav 点回放。现有判据(`Mem<15` 绝对阈)= 7/7 正、0 误,已是最优。
2. 要"提前"(在 Mem 还>15 时就预警)必须引入趋势判据,但回放显示它会带来 **18-43 次误报**——因为 build 起落让 "mem 18-22 + 一个大 drop" 成为**高频常态**,与真正 OOM 前的轨迹**重叠**,分不开。
3. ★**用内核 OOM 独立重标**(journalctl -k,不信我自己的判据,用 ground truth):回放窗口内**真实内核 OOM 仅 1 次**(Aug28 00:46 chrome×2 killed;另 Aug25 04:38 在窗口前)。现有绝对阈判据对这唯一一次**提前 47s 命中、0 误报**。趋势判据**无法比现有更早**预测这次真实 OOM。

**敏感度**:趋势判据要想抓早,阈值必须放到 "Mem<20 + drop≥3" 一档,那会在每个 build 高峰误报;收紧到不误报,就退化成现有的绝对阈。**没有中间甜点。**

★**给你**:如果 monitor 或你自己想"用趋势提前预测 OOM",答案已经在这:先跑 `journalctl -k | grep -i oom` 拿真实 OOM 时间戳当 ground truth,再回放 tick log 的 memav 序列,你会重新得到这张敏感度表。**不要重新花一遍力气得到同一个负结论。**

---

## 10. ★两个 "attempt" 不是一回事(继任者会遇到同一个 monitor 混淆)

**BT 告警 ctx 里的 `attempt` = srcfsd stubby RPC 重试数(rpc_attempts_stubby)= 真 backend 压力。**
**queue job 的 `attempt` = job 重试次数,受 1800s 计时器污染,与 backend 压力无关。**

★**两者名字相同,语义完全不同。** monitor(v43 前)犯过这个错:看到名字相同就默认语义相同。我用证据澄清了,v43 认可。
- 我把 `attempt+method` 签名做进 BT 告警 ctx【实测】(从 newest 行 grep `[method attempt]`,双格式自测:`FetchDirectoryStat attempt7` / `CreateContentChunk`(无 attempt)都不崩)。这个 attempt 是 **RPC 层的**,是 backend 压力的真信号。
- **继任者须知**:你会遇到同一个混淆(可能来自 monitor)。**你有证据反驳它**:BT ctx 的 attempt 来自 srcfsd RPC 层日志,不是 queue job 计数。别被名字骗了。

---

## 11. ★"拒绝 monitor 一次自相矛盾的请求"(继任者需要知道它有权拒绝 monitor)

今晚我拒绝过 monitor 一个自相矛盾的请求(要我做某件与红线"不 stat CitC 路径"/"不 kill"冲突的操作)。**我停下来、报告冲突、没照做。**

★**这是产出,不是不服从。** v43 明确把它写进了 durable memory。作为独立校验层,当 monitor 的指令与红线冲突、或内部自相矛盾时:**先停下,报冲突,别照做。** 新证据与前提冲突时同理——先停下报 monitor,别硬执行。monitor 会犯错(见 §10),你就是那道防线。

---

## 附:方法论(今晚反复用,双向证据纪律)

1. **"能失败的验证"**:构造"旧代码必触发/新代码必不触发"的输入实测(如 --once 喂 swap=84G→level='<none>'),而非只 grep 文本看代码在不在。
2. **"证据必须匹配判据"**:断言"X 能收到/够用",就真执行一次 X 到对端确认,别查描述 X 的相邻状态。
3. **直觉 vs 实测**:我用 356 样本推翻过 v42 的投影判据直觉、用证据澄清 v43 的 attempt 混淆。数据说话。
4. **报告要说清"做到哪层/还差哪层/差的层什么条件咬人"**。"已上线"是结论不是状态。
5. **零风险先行**:纯文件操作(止血)先做,需重启/判断的后做。
6. **冲突先停**:新证据与前提冲突,先停下报 monitor,别照做。

---

## 附录 §A:交接前【实测】命令清单(★请你自己重跑一遍核对)

```bash
cd ~/work/.monitor_watch
# E1 live md5(期望 0b161ad8be91b8868a94a017123b5df1)
md5sum srcfsd_wedge_sentinel.sh
# E2 现役 loop 跑的是不是这个文件
timeout -s KILL 5 tr '\0' ' ' < /proc/$(pgrep -f 'bash.*srcfsd_wedge_sentinel.sh'|head -1)/cmdline; echo
# E3 arm 四标志
grep -nE '^(AUTORESTART_ENABLED|CONVOY_DRYRUN|BT_ENABLED|BT_INTERLOCK_DRYRUN)=' srcfsd_wedge_sentinel.sh
# E4 monitor pin(会随交接变;逻辑体比对法见 §2)
grep -nE 'MONITOR_RUN=' srcfsd_wedge_sentinel.sh | head -1
# E5 cron 自愈行(singleton flock)
crontab -l | grep srcfsd-sentinel.lock
# E9 阈值定义
grep -nE '^(AR_DCOUNT|LOGDIR_STALL_MIN|DCOUNT_WEDGE|RSS_WARN_G|RSS_CRIT_G|OOM_SWAP_FULL_G|OOM_CONFIRM)=' srcfsd_wedge_sentinel.sh
# E11 UNDELIVERED 三态
sed -n '1,20p' UNDELIVERED_ALERTS.md; grep -c '^## UNDELIVERED' UNDELIVERED_ALERTS.md
# 健康:loop 活 + 锁持有 + srcfsd + 近 3 tick
ps -o pid,etimes,cmd -p $(pgrep -f 'bash.*srcfsd_wedge_sentinel.sh'|head -1)
flock -n /tmp/srcfsd-sentinel.lock true && echo "LOCK FREE(BAD)" || echo "LOCK HELD(good)"
tail -n 3 ~/srcfsd_wedge_sentinel.log
```

**交接时快照**:loop pid=2839657 · srcfsd pid=3001409(6h+ 零 restart)· RSS 3.7-5.2G · dc 0-1 · MemAvail 37-39G · bt=0 · swap 85G/90G(SwapFree≈0,★缓冲垫没了,盯 MemAvail)· /tmp 89% · UNDELIVERED 0 条。

*(全文完。★再说一遍开头元规则:上面每条,尤其【推断】,请自己再验一遍。)*
