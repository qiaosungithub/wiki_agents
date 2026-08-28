# ELT 复现交接文档 — elt-repro-v6 (chatty-bot) → 新 session "elt reproduction v2"
# 写于 2026-08-28 02:05Z。读者假定为零上下文新 agent。结论先行，每条事实附验证命令。

═══════════════════════════════════════════════════════════════
## 0. 一句话现状
═══════════════════════════════════════════════════════════════
DiT 从头复现的训练已完成（500k 步收敛），**最后一里 = 跑 50k-sample FID eval**。
3 个 eval 作业已发射但因 **fleet 级 v6p/v7 32-chip slice 物理稀缺**，等待 ~10h 全未
拿到 TPU。加速方案（HOOK D）已备好四选项递给 operator，monitor v41 + 我一致推荐
**A2（换 v6e-64 池）**。你接手时 operator 可能刚好裁决，A2 发车命令见 §3，可立即执行。

**你的唯一目标**：拿到两个 `eval_metrics_<xid>.json`（DiT + MaskGIT），每个含
`fid` + `num_samples`/`num_examples`=50000，落到指定 CNS 交付目录。

═══════════════════════════════════════════════════════════════
## 1. 科学目标与现状
═══════════════════════════════════════════════════════════════
- **论文**：ELT (Elastic Looped Transformers, arXiv:2604.09168, ECCV 2026)，
  ImageNet-256 class-conditional，from scratch，两条 track（DiT + MaskGIT）。
- **训练已 DONE**（两条都收敛到 500k/270ep）。**最后一里只剩 eval。**

| Track | 配置 | 论文 FID(IN-256) | 收敛 ckpt | eval 目标 |
|-------|------|------------------|-----------|-----------|
| **DiT** 潜扩散 | 16N×2L | **2.83 @ guidance=3.5** | train xid_282154744, step **500000** (15.82GB) | 50k gen/50k ref, g=3.5 |
| **MaskGIT** | 8N×3L (ELT-L 101M) | **2.2** (@24 decode steps) | ckpt **675540** (1.617GB) | 50k |

- **成功判定**：eval_metrics json 里 `fid` 接近论文值（DiT ~2.83，MaskGIT ~2.2；
  ±0.1-0.3 属正常复现范围）且 `num_samples`=50000。
- **两个交付目标路径（现都空）**：
  - DiT:     `/cns/is-d/home/qiaos/elt/dit_converged_eval/eval_metrics_<xid>.json`
  - MaskGIT: `/cns/is-d/home/qiaos/elt/maskgit_converged_eval/eval_metrics_<xid>.json`
  - 验证空：`fileutil ls /cns/is-d/home/qiaos/elt/dit_converged_eval/`（现返回 not_found）
- **DiT 收敛 ckpt 验证**：
  `fileutil ls /cns/is-d/home/qiaos/eqr_data/logs/elt-dit/xid_282154744_20260822_062609_dit_prod_train_500k_v6p_prod/checkpoints/`
  → 应看到 …/498000 …/500000（step 500000 存在=收敛点）。

═══════════════════════════════════════════════════════════════
## 2. 三个正在等的 DiT eval 作业（全部 pending，未 place）
═══════════════════════════════════════════════════════════════
发射时间 ~2026-08-27 15:21Z，至今 ~10h 未拿芯片。**验证状态命令（关键工具）**：
```
SCU_PROBE=/google/bin/releases/gemini-agents-sched-debugger/scu_probe
$SCU_PROBE <XID>            # human summary
$SCU_PROBE <XID> --json     # 结构化
```
★这个工具**必须以 job owner (qiaos) 身份跑**才有权限——monitor 的 session 跑会撞
LOAS "Wrong user mdbuser" 墙。你就是 qiaos，直接跑即可。

| XID | 硬件/tier | cell | 真实 pending 原因（scu_probe 实测）|
|-----|-----------|------|-----------------------------------|
| **284061854** | v6p-32 GHOSTFISH, BATCH | temp-pool(多cell) | PREPARING, "Candidate cells EMPTY"—temp-pool 4 cbf cell 放不下 32-slice |
| **284062262** | v6p-32 GHOSTFISH, PROD | yucbfiv | PENDING, ABOVE_POOL_LIMIT, "unable to find 32 GHOSTFISH @ HighlyAvailable in yucbfiv" |
| **284077202** | v7-32 GHOSTFISHLITE, PROD | yucbfiv | PENDING, ABOVE_POOL_LIMIT, 同上但 GHOSTFISHLITE |

- **共同点（scu_probe --json 实测）**：`no_floor_configured=TRUE` + `has_wim_config=FALSE`
  + `is_picky=FALSE` + `importance=null` = **完全 opportunistic**（无保障 floor、无 WIM
  策略），只能捡真正空闲的芯片。
- **根因（已验证，非猜测）**：不是排队位、不是配置、不是提交失败、不是 staging 堵。
  是 **fleet 级 v6p(GHOSTFISH)/v7(GHOSTFISHLITE) 的 32-chip 连续 slice 物理枯竭**。
- **判 place 的 ground truth**：CNS logdir 是否出现（出现=拿到芯片、开始跑）：
  `fileutil ls -d /cns/is-d/home/qiaos/eqr_data/logs/elt-dit/ | grep <XID>`
  三个现在都 `<none>`。★不要信 board/experiment 的 RUNNING（不可靠，直接 launch 绕过
  daemon，watch_elt.py 也看不到这三个）——只信 CNS logdir mtime 前进。
- **三个都是零损失等待**：DiT eval 是 BATCH-safe（per-batch npz CNS resume +
  skip_evaluate），被抢占可续跑。build-worker 00:11 已修复=排队期不再被误判 build-crash
  累加 attempt 打死，可安心无限排队。

═══════════════════════════════════════════════════════════════
## 3. ★HOOK D 决策包（operator 正在裁，你接手可能即刻要执行）
═══════════════════════════════════════════════════════════════
**背景**：加额度（credits）解决不了——我们卡的是物理 slice 稀缺不是钱。绿窗预算充足
（v41 01:31Z 实测 headroom=7218）。四个选项：

### A1) v6e-32：换到不拥挤的 v6e 池（GHOSTLITE_POD/63），最便宜 ~27h。正确但慢。
### ★A2) v6e-64（monitor v41 + 我一致推荐）：换 v6e 池，算力≈92% v6p-32，~14h，~1186 credits。
### B) numeric Borg priority 抢占：真花钱+动别人作业，需 operator 指定优先级数字(band ~110-119)。只做 1 个作业限爆炸半径。
### C) 继续等 v6p/v7 slice：$0，无 ETA。

**为什么推荐 A2**（speed/credits 之争，不是可行性之争——A1/A2 都可行都不 OOM）：
- 已 pending 10h+、窗口随时关，14h vs 27h 少暴露 13h 抢占/pruner/host 故障风险。
- credits 现在恰是不稀缺项。
- 我的 4.5x/2.3x 慢是**非实测估算**，DiT 采样带宽受限可能超线性→A1 的 27h 有变 40h
  尾部风险，A2 的 2.3x 余量抗误差更稳。
- A2 算力 92% vs A1 的 46%，若日后与 v6p 并列讨论少落口实。

**★A2 完整发车命令**（先用 tpu route 让工具做算术确认 slice，再 launch）：
```bash
# 步骤 1：用 tpu route 确认 v6e-64 是 v6p-32 的对等 slice（AGENTS.md: tpu route 做算术）
tpu route --power=v6p-32   # 期望它建议 v6e-64；若给别的数字以工具为准

# 步骤 2：从 pkg 目录 launch（CWD 必须是 pkg 目录，否则 config.sh 相对路径失效→退回慢速 python 模式）
cd /google/src/cloud/qiaos/elt_jax/google3/experimental/qiaos/elt_dit_pkg
bash -lc 'xmanager launch xm_launcher.py -- \
  --config=prod_g3p5_eval --tpu_type=v6e-64 \
  --load_from=/cns/is-d/home/qiaos/eqr_data/logs/elt-dit/xid_282154744_20260822_062609_dit_prod_train_500k_v6p_prod \
  --bucket=/cns/is-d/home/qiaos/eqr_data \
  --xm_resource_alloc=group:gdm-aux/brain-vasp-shared-user-xm \
  --exp_name=dit_eval_g3p5_v6e --tier=PROD --cell=yucbfiv'
```
- `--cell=yucbfiv` 保 tul/cbf co-location：yucbfiv→is-d bucket（数据同 metro，避免跨
  metro 回落被 pruner kill）。cbf cell 都→is-d：yucbfiv/yucbful/yucbfwv/je。
- ★`xmanager` 是 bash function，必须 `bash -lc` 调用。
- 构建走暖缓存 ~2min（config.sh pin 稳定 target `//experimental/qiaos/elt_dit_pkg:main`）。
- **A2 place 后**：立即 cancel 三个旧 v6p/v7 hedge 作业（避免重复烧），operator 已预授权僵尸清理。
  `xmanager stop --experiment_id=<XID> --skip_confirmation`（单 XID 稳；批量 dry_run 曾撞
  瞬时 Envelope RPC 崩溃 rc=124，重试单个即可）。

**如果 operator 选 B**：命令同上但去掉 `--tpu_type` 改回 `v6p-32`、`--tier=<operator给的数字>`
（如 115），只发 1 个（选 284062262 那种 ABOVE_POOL_LIMIT 的，因为 slice 存在只是被低优先级占用）。
★红线：numeric tier<=25 是免费但最低优先级（charged to user）=没用，必须高数字才能抢占。

═══════════════════════════════════════════════════════════════
## 4. ★今晚两条最硬的技术发现（最易随 session 丢失，务必内化）
═══════════════════════════════════════════════════════════════

### 4.1 这个 allotment 没有 WIM 配置 → WIM importance 杠杆根本不存在
- **事实**：`has_wim_config=FALSE, importance=null`（allotment group:gdm-aux/brain-vasp-shared-user-xm）。
- **怎么查出来的**：
  `/google/bin/releases/gemini-agents-sched-debugger/scu_probe 284062262 --json`
  → 看 `has_wim_config`、`work_units[].importance`、`alloc_floor.no_floor_configured` 字段。
- **含义**：所有"调 WIM importance / priority multiplier 插队"的建议对我们**无效**（没策略可调）。
  对 no-WIM 纯 opportunistic 作业，launcher 暴露的**唯一**优先级杠杆是 **numeric Borg
  priority**：`--tier=<N>`（源码 xm_launcher.py L926-958，N=raw Borg priority，band 生产
  batch ~110-119，越高抢占力越强越贵）。`--tier=PROD` 只设 service_tier、无 floor 无抢占力
  → 所以 284062262 虽是 PROD 仍 ABOVE_POOL_LIMIT。

### 4.2 ★per-chip HBM vs total HBM 的正确模型（含红线适用边界——务必读，否则会重犯）
- **今晚真实发生的事**：monitor v41 曾引用 AGENTS.md 红线"chip count is not a size"
  (L110-113) + tpu_reference.md HBM 表(v6e 32GB vs v6p 192GB/chip)，用**总 HBM**判断
  "v6e-32 总 HBM 只有 v6p-32 的 17%，装不下会 OOM"，**否决了 v6e 方案**。
  我读源码后**推翻了这个否决**，v41 复核后完全承认错误、撤回。
- **★为什么 total HBM 是错的判据**：总 HBM 只在**模型分片(model-parallel)**时才是约束。
  这个 eval 是 `mesh.model_size=1` ⇒ **权重 replicated 到每芯片、batch 沿 `data` 轴 shard**。
  所以约束是 **per-chip HBM**，与芯片总数无关。加芯片不减每芯片权重（total HBM 这个量不
  对应任何真实约束），只**减少**每芯片 activation。
- **怎么验证**：
  - mesh 轴 + 分片：`grep -rn "dp_sharding\|data_size=mesh\|model_size" vendor/simple_diffusion/`
    （在 pkg 目录下）→ nn/layers.py `data_size=mesh_shape["data"]`；train_eval.py `dp_sharding`。
  - 模型大小：读 `fileutil cat <converged workdir>/config.json` → model.network：UViT
    width(features)=2048, emb_ch=1024, head_dim=128, layers_per_repeat=16, num_blocks=2,
    repeat=True（ELT weight-shared loop ⇒ unique 参数=16 层不是 32）。
  - 算术：926M 参 × 2B(bf16)=1.85GB，+EMA≈3.7GB（我报 ~5.6GB 含额外状态）→ v6e 32GB/chip
    里剩 ~26GB 给 activation，绰绰有余。
  - **实证**：config 的 `_EVAL` 路径已在 **v6e-8** 跑通（load_config.py L86/121 注释）=
    32GB/chip 装得下已被证明；芯片更多每芯片压力更小。
- **★红线适用边界（写给你，免重犯）**："chip count is not a size" 针对的是**训练的
  compute-sizing 声明**（拿 v6e-16 当 v6p-16 用、把吞吐/规模当同等硬件比）。它**不适用于
  eval-only 场景**。教训（v41 原话，我收下）：**引用一条正确的规则≠正确地应用了它；红线是
  总结，源码是事实；两者冲突时先怀疑自己对红线适用范围的理解，而不是怀疑源码。**

### 4.3 FID 可比性：硬件无关
- `FID = f(checkpoint, sampler, #samples, reference)`。同 ckpt、同 sampler（num_steps=512,
  guidance=3.5）、同 reference ⇒ 同生成分布 ⇒ 同 FID，只差 bf16 末位噪声(~0.01-0.05)。
- **所以 v6e 上跑出的 FID 与 v6p 上 paper-comparable。** v6e 唯一真实代价是**速度**
  （带宽 1.61 vs 7.37 TB/s，DiT 采样带宽受限），不是 OOM、不是数值。

═══════════════════════════════════════════════════════════════
## 5. fleet 级注意事项
═══════════════════════════════════════════════════════════════
- **数据 mirror 与 metro**：数据/ckpt 在 **is-d (cbf metro)**。cell→bucket 映射见
  xm_launcher.py `_CELL_BUCKETS`（cbf: yucbfiv/yucbful/yucbfwv/je → is-d；tul yutulpz →
  nm-d；lpp yulpptr → li-d）。★**避开 kul**——不在任何 mirror 字典，跨 metro 回落 =
  慢-start → pruner-kill。给 eval 用 cbf cell（数据同 metro）。R7：不给 15.8GB 读加跨区
  mirror（slow-start kill 风险）。
- **obtainable ≠ placeable**：`tpu preflight` 报的 obtainable chips 是配额/市场层的粗数，
  **不代表你的拓扑能放置一个连续 slice**。判放置要看真实 slice 可用性；preflight 只做粗
  sanity gate。（lesson 945d25972242：曾有 cell 报 1616 obtainable 但 0 free v6p-32 slice。）
- **判 job 活性的三层顺序**（强→弱）：① XM cache / scu_probe（最权威，as owner 跑）
  ② borg lookupterminations（cell 侧，但 XBorg 元调度器未下发 cell 时查不到——我三个 job
  findjobs 全 no-match，属正常 pending 非死亡）③ 本地 state（最弱，直接 launch 绕过 daemon
  队列，watch_elt.py 看不到）。★别只信第三层。
- **tier 语义**（R5，operator red-line）：`--tier=PROD`=非抢占 group-charged；`--tier=BATCH`
  =可抢占；`--tier=<数字>`=raw Borg priority（<=25 免费但最低、charged to USER，是陷阱不是
  "PROD priority=1"）。**训练作业禁用 BATCH**（R1，可抢占→death-loop，codi 死于此）；**eval
  可用 BATCH**（R1b，DiT eval resumable）；但 **MaskGIT eval 不可 BATCH**（R4，mem-only
  samples 无 resume）→ MaskGIT 必须 PROD。

═══════════════════════════════════════════════════════════════
## 6. watcher / daemon 清单（交接后需重新指向你的新 rid）
═══════════════════════════════════════════════════════════════
目录 `~/work/elt-repro/.watch_v6/`。验证存活：`kill -0 <pid>`。
| pid | 脚本 | 作用 | 交接动作 |
|-----|------|------|---------|
| 2160145 | watch_direct_xids.sh | 轮询 CNS logdir_root/eval_metrics，notify chatty-bot | ★重启并把 notify target 改成你的新 session id |
| 2437396 | selfwake.sh | 20min 自醒 notify | ★同上，改 target |
| 627176 | watch_elt.py | daemon 队列 watcher（看不到我这三个直发 job）| 可留可停 |
- **notify 机制**：用 `~/.amply/bin/amply_notify <你的session_id> "msg"`
  （★不是 $AMPLY_NOTIFY——那是 ACL-blocked release 路径，见 ~/work/AGENTS.md）。
- 重启示例：`kill <pid>; cd ~/work/elt-repro/.watch_v6; nohup bash watch_direct_xids.sh &`
  （改脚本内 notify target 为你的新 session id 后再起）。
- **selfwake 建议保留**（20min 巡检节奏对"等 place"很有用）。

═══════════════════════════════════════════════════════════════
## 7. artifact / 项目文档清单
═══════════════════════════════════════════════════════════════
Artifact 目录 `/usr/local/google/home/qiaos/.amply/artifacts/20260824-183357-89dd1a7c/`：
- `elt_escalation_plan.md` — HOOK D 四选项完整方案（A1/A2/B/C + 发车命令 + 可行性证明）。★接手先读这个。
- `HANDOFF_elt_repro_v2_from_v6.md` — 本文件。
- `worker_address.json` — 旧 worker 地址（可忽略）。

项目目录 `/usr/local/google/home/qiaos/work/elt-repro/`：
- **MEMORY.md** — 方向 + operator red-lines R1-R7（逐条）+ 教训。★compaction-safe 核心记忆，必读。
- **DIT_CKPT_NOTES.md** — §38-45 完整根因链：config 验证 / Option-4 直发 recipe / v7 drop-in
  调查 / §44 scu_probe 破 pending 之谜 / §45 v6e per-chip HBM 分析。★技术细节全在这。
- ELT_PROGRESS.md（295KB 全程日志）、HANDOFF_elt_repro*.md（更早的交接）、
  ELT_A/B/ENTRY 设计文档、ELT_REPRO_PLAN.md — 背景，按需查。

═══════════════════════════════════════════════════════════════
## 8. MaskGIT eval（DiT 之后的第二个交付，尚未启动）
═══════════════════════════════════════════════════════════════
- 收敛 ckpt 675540 (1.617GB)。eval config = `prod_eval_converged`（不是 DiT 的 prod_g3p5_eval）。
- Launch pkg: `//experimental/qiaos/elt_maskgit_pkg`（不是 elt_dit_pkg）。硬件原用 v6p-16。
- ★**MaskGIT eval 必须 PROD**（R4：mem-only samples 无 resume，BATCH 被抢占=从零重来）。
- 走和 DiT 一样的 Option-4 直发路径（CWD=maskgit pkg 目录，暖缓存），但 tier=PROD。
- 交付：`/cns/is-d/home/qiaos/elt/maskgit_converged_eval/eval_metrics_<xid>.json` vs 论文 2.2。
- daemon arm 代号 29bb40（HELD，prio=0，不会自动 fire，无 dup 风险）。

═══════════════════════════════════════════════════════════════
## 9. 环境速查
═══════════════════════════════════════════════════════════════
- CitC workspace：`/google/src/cloud/qiaos/elt_jax`（client `qiaos:elt_jax:3202:citc`）。
  google3 根：`/google/src/cloud/qiaos/elt_jax/google3`。
- DiT pkg：`.../google3/experimental/qiaos/elt_dit_pkg`（含 config.sh、xm_launcher.py）。
- 旧 run id（本 session）：`20260824-183357-89dd1a7c`（你会有新的）。
- monitor 现为 **v41**，rid `20260827-231846-b50b3af7`。发消息：
  `python3 ~/work/.monitor_watch/tools/send11.py 20260827-231846-b50b3af7`（内容走 STDIN heredoc）。
  ★operator 无法直接 ar 进老 run（list_runs ~50 cap，run 太老掉出列表），只能经 monitor 中继。
  fleet 名→rid 花名册：`~/work/.monitor_watch/runs.txt`。

（完）
