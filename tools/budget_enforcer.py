#!/usr/bin/env python3
"""Dynamic budget enforcer: keep active PROD cost <= income/10 by cancelling
the fewest (= most expensive first) PROD jobs when a price rise pushes the
running aggregate over the hard cap.

Operator boss directive 2026-08-25: credit hard cap is income/10 (see
budget_check.py). budget_check gates NEW launches, but a market price rise can
push ALREADY-RUNNING jobs' aggregate cost over the cap. This daemon closes that
gap: it periodically recomputes active PROD cost and, if over cap, cancels
PROD jobs (most expensive first, so it removes the FEWEST jobs) until the
aggregate is back at/under income/10.

Policy (operator-confirmed 2026-08-25):
  * ONLY PROD jobs are candidates. BATCH draws from the free pool (0 PROD cost),
    never counted, never cancelled.
  * Delete the FEWEST jobs: sort candidates by cost DESC, cancel from the top
    until total_cost <= limit. (Cheapest set of cancellations by count.)
  * Pricing reuses budget_check.get_job_cost / chip_price -> identical basis as
    the launch gate.
  * Zombie filter: mirror budget_check -- a job absent from the live check-cache
    AND older than STALE_HOURS is a never-migrated corpse, excluded from cost.

SAFETY:
  * DRY-RUN BY DEFAULT. Cancelling is destructive (kills a running training).
    Pass --arm to actually cancel; without it, only prints the plan.
  * --once runs a single pass (for inspection); default loops every --interval s.
  * Cancels via the sanctioned `tpu cancel <xid>` path (xmanager stop + mark
    CANCELLED in the registry), never a raw kill.
  * A per-pass cap (--max-cancels) bounds how many jobs one pass may cancel, so
    a bad price spike cannot mass-cancel the whole fleet in one tick.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import budget_check as bc

WRAPPER = os.path.expanduser('~/work/tpu_cmd/tpu_wrapper.sh')


def _load_cache_status(cache_file):
    """xid -> lowercased UI status, for the zombie filter (mirrors budget_check)."""
    cache_status = {}
    if os.path.exists(cache_file):
        try:
            c = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', open(cache_file).read())
            for m in re.finditer(r'│\s*(\d{8,11})\s*│\s*([A-Za-z0-9_-]+)\s*│', c):
                cache_status[m.group(1)] = m.group(2).lower()
        except Exception as e:
            print(f"[enforcer] warn: cache parse failed: {e}", file=sys.stderr)
    return cache_status


def active_prod_jobs(jobs_file, cache_file):
    """Return (rows, prod_total, batch_total) where rows are PROD candidates
    sorted by cost DESC. Mirrors budget_check's active-job accounting."""
    cache_status = _load_cache_status(cache_file)
    prod, batch_total = [], 0.0
    try:
        data = json.load(open(jobs_file))
    except Exception as e:
        print(f"[enforcer] ERROR reading {jobs_file}: {e}", file=sys.stderr)
        return [], 0.0, 0.0
    for xid, e in data.items():
        if not isinstance(e, dict):
            continue
        if e.get('status') not in ('SUBMITTED', 'RUNNING'):
            continue
        # Count SUBMITTED-and-PENDING as well as RUNNING (operator 2026-08-27,
        # option B): a committed-but-pending job reserves budget too, so it is a
        # legitimate cancel candidate when the aggregate is over cap. Only drop
        # ZOMBIES (live check-cache state terminal, i.e. not running/pending/
        # queued) -- mirrors budget_check's launch-gate accounting.
        if xid in cache_status and cache_status[xid] not in ('running', 'pending', 'queued'):
            continue
        # g3/g5 draw on their own balance, not G9's income, so they are exempt
        # from the G9 income/10 cap this enforcer defends -- never count or
        # cancel them here (mirrors budget_check; kept pending operator's
        # separate call on the g3/g5 exemption).
        if bc.is_exempt_group(e.get('alloc', '')):
            continue
        tpu_type = e.get('tpu_type', '')
        tier = e.get('tier', 'PROD')
        # A family whose PROD auction cleared at 0.00 this cycle adds nothing
        # to the G9 bill, so cancelling it frees no credits -- it only destroys
        # work. The launch gate already knows this (budget_check.py:
        # `if _new_arch in free_pool_families(): sys.exit(0)`); this enforcer
        # did not, and priced free chips at the policy cap instead.
        #
        # The two gates disagreeing is not a cosmetic inconsistency, it is a
        # pump: the launcher admits free-pool jobs precisely because they are
        # free, they accumulate, and then the enforcer kills them for a cost
        # they do not have. It runs fastest exactly when chips are cheapest.
        # Measured 2026-08-30, v7 at 0.00: 15 running jobs cancelled in 10
        # minutes. Operator decision (lyy, 2026-08-30) to align the two sides.
        #
        # Spend stays bounded by the per-XID limit order the wrapper sets at
        # launch (tpu_wrapper.sh _tpu_limit_price_for_arch): if the family
        # stops clearing at zero, the auction pulls the job instead of letting
        # it bill unbounded. That -- not this aggregate bar -- is what protects
        # the budget for a family that is currently free.
        _arch = tpu_type.split('-')[0].strip().lower()
        if _arch in bc.free_pool_families():
            continue
        cost = bc.get_job_cost(tpu_type, tier)
        if tier.upper() == 'BATCH':
            batch_total += cost
            continue
        if xid not in cache_status:
            age = bc.job_age_hours(e)
            if age is not None and age > bc.STALE_HOURS:
                continue  # never-migrated corpse
        prod.append({'xid': xid, 'cost': cost, 'tpu_type': tpu_type,
                     'tier': tier, 'name': (e.get('exp_name', '') or '')[:40],
                     'has_ckpt': bool(e.get('bucket_cp_path')),
                     # ★Carry the PATH, not just a bool. _has_checkpoint_on_disk
                     # reads r['bucket_cp_path']; the row never had it, so its
                     # CNS probe was DEAD CODE and every pause was refused with
                     # "no bucket_cp_path in ledger" no matter what the ledger held.
                     'bucket_cp_path': (e.get('bucket_cp_path', '') or ''),
                     'has_stagedir': bool(e.get('stagedir'))})
    prod.sort(key=lambda r: r['cost'], reverse=True)
    prod_total = sum(r['cost'] for r in prod)
    return prod, prod_total, batch_total


def plan_cancellations(prod, prod_total, limit):
    """Fewest-jobs plan: cancel most-expensive first until total <= limit.
    Returns (to_cancel list, projected_total_after)."""
    to_cancel, running = [], prod_total
    for r in prod:            # already sorted cost DESC
        if running <= limit:
            break
        to_cancel.append(r)
        running -= r['cost']
    return to_cancel, running


# ★THE LEDGER IS NOT THE FLEET. `~/.tpu_jobs.json` keeps `status=SUBMITTED`
# long after a job is dead (measured 2026-08-30: 284948672 / 284838424 /
# 284364771 all NOT_RUNNING on XM, all still SUBMITTED locally with
# cost/state/last_seen = None). The two existing filters both miss it: the
# check-cache filter needs the xid to BE in the cache (these were absent, and
# the cache itself was 40h stale), and the STALE_HOURS filter needs a timestamp
# that these rows do not carry.
#
# Cancelling a corpse is not harmless: the planner counts its cost as budget
# RECLAIMED, so the pass reports success, stops early, and the job that is
# actually burning money is never touched. The kill list was, at 15:0xZ,
# three dead jobs and 1557 credits of imaginary savings.
#
# So: verify each CANDIDATE against XM before acting. Only candidates, not the
# whole active set -- one batched lookup, not 36.
XMANAGER_PAR = '/google/bin/releases/xmanager/cli/xmanager.par'


def live_status(xids, timeout_s=180.0):
    """{xid: Status} from XManager for the given xids. Missing key = unknown.

    Absolute path on purpose: `xmanager` is a shell function and `xmanager.par`
    is not on PATH, so a bare name exits 127 -- which, behind a pipe, is
    indistinguishable from 'the experiment does not exist'.
    """
    xids = [str(x) for x in xids if str(x).isdigit()]
    if not xids:
        return {}
    try:
        p = subprocess.run(
            [XMANAGER_PAR, 'list', '--experiment_id=' + ','.join(xids),
             '--archived=no', '--columns=ID,Name,Status'],
            capture_output=True, text=True, timeout=timeout_s)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"[enforcer] {_ts()} WARN: XM status lookup failed ({e}); "
              f"treating every candidate as UNKNOWN (fail-safe: no cancels).",
              file=sys.stderr)
        return {}
    out = {}
    for ln in (p.stdout or '').splitlines():
        f = ln.split()
        if len(f) >= 3 and f[0].isdigit():
            out[f[0]] = f[-1]
    return out


def drop_dead_candidates(to_cancel):
    """(live, skipped): candidates XM still reports as running, and the rest.

    FAIL-SAFE DIRECTION: a job we cannot get a status for is treated as DEAD
    (skipped), never cancelled on a guess. Cancelling the wrong job destroys
    work; skipping one only defers enforcement to the next pass.
    """
    if not to_cancel:
        return [], []
    status = live_status([r['xid'] for r in to_cancel])
    live, skipped = [], []
    for r in to_cancel:
        st = status.get(str(r['xid']))
        if st and st.upper() == 'RUNNING':
            live.append(r)
        else:
            r['_skip_reason'] = st or 'no XM status'
            skipped.append(r)
    return live, skipped


def cancel_job(xid, jobs_file, dry_run):
    """Cancel one xid via the sanctioned `tpu cancel` path (xmanager stop +
    mark CANCELLED). Returns (ok, output)."""
    if dry_run:
        return True, f"[dry-run] would: tpu cancel {xid}"
    script = (f'export TPU_JOBS_FILE={json.dumps(jobs_file)}; '
              f'source {json.dumps(WRAPPER)} >/dev/null 2>&1; '
              f'tpu cancel {xid}')
    try:
        p = subprocess.run(['bash', '-c', script], capture_output=True,
                           text=True, timeout=300)
        return p.returncode == 0, (p.stdout or '') + (p.stderr or '')
    except subprocess.TimeoutExpired as e:
        return False, f"tpu cancel {xid} TIMED OUT: {e}"


# Same-geometry arch family for a resume: a checkpoint sharded for one mesh can
# only resume onto the SAME geometry. The 3-D torus family (v4/v5p/v6p/v7)
# shares geometry at every legal size, so a v6p-32 (2x4x4) resume also accepts
# v7-32 (2x4x4). We list the cheap-and-compatible families so the router can
# place the resume wherever it is cheapest within the same mesh.
_ARCH_FAMILY = {
    'v4': ['v6p', 'v7', 'v5p', 'v4'],
    'v5p': ['v6p', 'v7', 'v5p'],
    'v6p': ['v6p', 'v7'],
    'v7': ['v7', 'v6p'],
    'v6e': ['v6e'],   # 2-D mesh family: keep it to itself (different geometry)
    'v5e': ['v5e'],
}


def _archs_for(tpu_type):
    arch = tpu_type.split('-')[0].lower()
    return _ARCH_FAMILY.get(arch, [arch])


# --- ledger <-> queue pairing (added 2026-08-31, lyy) ---
# resume 在两处都按 $TPU_JOBS_FILE 查,而那个变量由**排这条队列的 worker**的环境
# 决定,不是入队时的环境:
#   tpu_wrapper.sh:1163-1177  查 stagedir(查不到 -> return 1 -> 没有 XID -> 3 次后 HELD)
#   xm_launcher.py:1678-1691  查 bucket_cp_path
# 所以把 lyy 的 XID 排进 sqa 的队列必然 HELD。实测 08-30 10:10Z-14:11Z 有 14 条
# 这样的行,last_reason 全是 "a resume must re-run the original snapshot"。
_LEDGER_TO_QUEUE = {
    os.path.abspath(os.path.expanduser('~/.tpu_jobs.json')):
        os.path.abspath(os.path.expanduser('~/.tpu_local_queue.json')),
    os.path.abspath(os.path.expanduser('~/lyy-work/.npu_jobs.json')):
        os.path.abspath(os.path.expanduser('~/lyy-work/.npu_local_queue.json')),
}

# 被 pause 但无法忠实 resume 的作业记在这里,等人处理。原子替换写(先写 .tmp 再
# os.replace),因为满盘时 open(w) 会先把文件截成 0 字节。
_PENDING_RESUMES = os.path.expanduser('~/lyy-work/.npu_pending_resumes.json')


def _record_pending_resume(r, jobs_file):
    """把一条待人工重投的记录追加到持久文件。返回 (ok, path_or_err)。"""
    rec = {'xid': r.get('xid'), 'tpu_type': r.get('tpu_type'), 'tier': r.get('tier'),
           'name': r.get('name'), 'cost': r.get('cost'), 'jobs_file': jobs_file,
           'cancelled_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'reason': 'paused by budget_enforcer; auto-resume withheld (no faithful config)'}
    try:
        cur = []
        if os.path.exists(_PENDING_RESUMES):
            with open(_PENDING_RESUMES) as f:
                cur = json.load(f) or []
        cur.append(rec)
        tmp = _PENDING_RESUMES + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(cur, f, indent=1)
        os.replace(tmp, _PENDING_RESUMES)
        return True, _PENDING_RESUMES
    except Exception as e:
        return False, f'{type(e).__name__}: {e}'


# CNS ".../logs" roots to search for a run dir by XID when a row carries no
# bucket_cp_path. A cross-cell wildcard (/cns/*-d/...) does NOT parse -- fileutil
# rejects a wildcard cell -- so a fallback must try each concrete cell in turn.
# Seeded static, then augmented from every distinct root the ledger already
# records, so adding a cell needs no edit here.
_CNS_LOG_ROOTS_SEED = (
    '/cns/el-d/home/qiaos/eqr_data/logs',
    '/cns/is-d/home/qiaos/eqr_data/logs',
    '/cns/oi-d/home/qiaos/eqr_data/logs',
    '/cns/si-d/home/qiaos/eqr_data/logs',
    '/cns/go-d/home/qiaos/eqr_data/logs',
)


def _known_cns_log_roots(jobs_file):
    """Static seed plus every distinct '.../logs' root the ledger records, so a
    new cell is picked up automatically."""
    roots = set(_CNS_LOG_ROOTS_SEED)
    try:
        data = json.load(open(jobs_file))
        for e in data.values():
            if not isinstance(e, dict):
                continue
            m = re.match(r'(/cns/[^/]+/.+/logs)/', (e.get('bucket_cp_path') or '').strip())
            if m:
                roots.add(m.group(1))
    except Exception:
        pass
    return sorted(roots)


def _find_run_dir_by_xid(xid, jobs_file):
    """Reconstruct a run's CNS dir from its XID when the ledger row has no
    bucket_cp_path (e.g. not backfilled yet) -- the case that used to blind the
    enforcer. Globs each known log root for '*/xid_<XID>_*'. Returns the path or
    ''."""
    xid = str(xid)
    if not xid.isdigit():
        return ''
    for root in _known_cns_log_roots(jobs_file):
        try:
            p = subprocess.run(['timeout', '60', 'fileutil', 'ls', '-d',
                                f'{root}/*/xid_{xid}_*'],
                               capture_output=True, text=True, timeout=90)
        except Exception:
            continue
        if p.returncode == 0:
            for ln in (p.stdout or '').splitlines():
                ln = ln.strip()
                if f'/xid_{xid}_' in ln:
                    return ln
    return ''


def _has_checkpoint_on_disk(r, jobs_file=None):
    """物理校验 CNS 上真有 checkpoint。查不到 -> 不该 pause(砍了就回不来)。
    返回 (verdict, detail);verdict: True=有 / False=确定没有 / None=查不了。

    ★台账缺 bucket_cp_path 不再等于"没有 checkpoint"。行里没有路径时(未回填),
    先用 XID 在已知 CNS 根目录里兜底找 run 目录,再校验 —— 而不是直接判 False
    把每个作业都当成不可 pause(那正是 enforcer 从不真正 pause 的旧 bug)。"""
    b = (r.get('bucket_cp_path') or '').strip()
    if not b:
        b = _find_run_dir_by_xid(
            r.get('xid', ''), jobs_file or os.path.expanduser('~/.tpu_jobs.json'))
        if not b:
            return False, 'no bucket_cp_path in ledger and none found on CNS by xid'
    try:
        p = subprocess.run(['timeout', '120', 'fileutil', 'ls', b],
                           capture_output=True, text=True, timeout=150)
    except Exception as e:
        return None, f'fileutil failed to run: {type(e).__name__}'
    if p.returncode != 0:
        err = ((p.stderr or '') + (p.stdout or ''))
        if 'not_found' in err or 'No parent directory' in err:
            return False, f'CNS says not found: {b}'
        return None, f'fileutil rc={p.returncode} (CNS unreachable?)'
    return True, b


def pause_and_requeue(r, jobs_file, dry_run, local_queue_file=None,
                      unsafe_blind_resume=False):
    """PAUSE a job instead of killing it: cancel the XID (frees chips, stops
    billing) then re-enqueue it as a QUEUED resume (launch=resume_xid=<xid>),
    so the reroute daemon re-launches it FROM ITS CHECKPOINT once the price
    drops enough to fit under income/10 again (budget_check gates the launch).
    A QUEUED job costs nothing (PENDING is free), so the pause itself never
    violates the cap. Returns (ok, output).

    Requires the job to have a recorded stagedir (code snapshot) so the resume
    can re-use the ORIGINAL source; bucket_cp_path (checkpoint) lets it continue
    rather than restart. If stagedir is missing we fall back to a plain cancel
    (nothing to resume from) and say so.
    """
    xid = r['xid']

    # 闸 1:台账与队列必须配对。未传就按表自动补(修好而不是拒绝);
    # 传了但不配对 = 唯一还能真出事的情形,拒绝;未知台账,拒绝。
    _jf = os.path.abspath(os.path.expanduser(jobs_file))
    _want_q = _LEDGER_TO_QUEUE.get(_jf)
    if _want_q is None:
        return False, (f"REFUSED to pause {xid}: 未知台账 {jobs_file},"
                       f"无法确定 resume 该进哪个队列(配对表: "
                       f"{sorted(_LEDGER_TO_QUEUE)})。不动这个作业。")
    if not (local_queue_file or ''):
        local_queue_file = _want_q
    elif os.path.abspath(os.path.expanduser(local_queue_file)) != _want_q:
        return False, (f"REFUSED to pause {xid}: 台账 {jobs_file} 的 resume 必须进 "
                       f"{_want_q},当前 --local-queue-file={local_queue_file}。"
                       f"错配会让排那条队列的 worker 用错台账查 stagedir,必然 HELD。")

    # 闸 2:pause 的前提是"以后能从 checkpoint 接着跑"。CNS 上没有 checkpoint 就
    # 不是 pause,是永久丢进度 —— 方向必须是"查不到就不砍"。
    if not dry_run:
        _ck, _ckdetail = _has_checkpoint_on_disk(r, jobs_file)
        if _ck is not True:
            return False, (f"REFUSED to pause {xid}: checkpoint 未确认 "
                           f"({_ckdetail})。砍了就回不到 {r.get('name')} 的进度,"
                           f"不动它;预算这一轮少停一个作业。")

    if not r.get('has_stagedir'):
        ok, out = cancel_job(xid, jobs_file, dry_run)
        return ok, f"[no stagedir -> plain cancel, cannot auto-resume] {out}"
    power = r['tpu_type']
    archs = ','.join(_archs_for(power))
    tier = r.get('tier', 'PROD')
    # priority -1: a resumed pause goes BEHIND fresh work, so the enforcer's own
    # re-queue never jumps the line ahead of what the operator newly enqueues.
    # TPU_LOCAL_QUEUE_FILE must match the AGENT's own local queue, or the resume
    # leaks into the default (tpu) queue and the wrong build-worker tries it.
    lq = local_queue_file or ''
    lq_prefix = f'export TPU_LOCAL_QUEUE_FILE={json.dumps(lq)}; ' if lq else ''
    if dry_run:
        return True, (f"[dry-run] would: tpu cancel {xid}; then "
                      + (f"TPU_LOCAL_QUEUE_FILE={lq} " if lq else "")
                      + f"tpu enqueue "
                      f"--power={power} --archs={archs} --tier={tier} "
                      f"--priority=-1 --launch=resume_xid={xid}"
                      + ("" if r.get('has_ckpt') else "  (no checkpoint: restarts from step 0)"))
    # 1) cancel the running XID
    ok, cout = cancel_job(xid, jobs_file, dry_run=False)
    if not ok:
        return False, f"cancel failed, NOT re-queued (job left as-is): {cout}"
    # 2) 本来这里 re-enqueue 成 resume。**默认不再这么做。**
    # 原因:enforcer 造的队列条目 launch_kwargs 只有 {resume_xid},没有 config。
    # 而 xm_launcher.py:25-26 是 _CONFIG = DEFINE_string('config', 'remote_run', ...)
    # —— 空壳 resume 会用 **remote_run** 这个默认配方跑,落在原 XID 的 checkpoint
    # 前缀上。台账里没有 config 字段,launch_log 里也没有,今天没有任何代码路径
    # 能补上它。所以这样的 resume 一旦真跑起来就是拿错配方覆盖真 checkpoint,
    # 比卡在 HELD 更糟。改为:记一条待办,让人拿正确的 config 重投。
    if not unsafe_blind_resume:
        ok2, where = _record_pending_resume(r, jobs_file)
        if ok2:
            return True, (f"cancelled; auto-resume WITHHELD (blind resume would run "
                          f"config=remote_run over this checkpoint). NEEDS MANUAL RESUME "
                          f"-> recorded in {where}")
        return True, (f"cancelled; auto-resume WITHHELD, and FAILED to record the "
                      f"pending-resume note ({where}) -- NEEDS MANUAL RESUME, xid={xid}")
    enq = (f'export TPU_JOBS_FILE={json.dumps(jobs_file)}; '
           f'{lq_prefix}'
           f'source {json.dumps(WRAPPER)} >/dev/null 2>&1; '
           f'tpu enqueue --power={power} --archs={archs} --tier={tier} '
           f'--priority=-1 --launch=resume_xid={xid}')
    try:
        p = subprocess.run(['bash', '-c', enq], capture_output=True,
                           text=True, timeout=120)
        if p.returncode == 0:
            return True, f"cancelled + re-queued as resume (power={power} archs={archs})"
        return True, (f"cancelled OK but re-enqueue rc={p.returncode} "
                      f"(job stopped, MANUAL re-enqueue needed): {_tail((p.stdout or '')+(p.stderr or ''))}")
    except subprocess.TimeoutExpired as e:
        return True, f"cancelled OK but re-enqueue TIMED OUT (manual re-enqueue needed): {e}"


# --- sustained-over debounce state (added 2026-08-30, lyy) ---
# income 会在几分钟内抖动 2 倍(实测 19845 -> 45059),cap=income/10 随之摆动,
# 于是 cost 几乎没变也会瞬时"超额"。原来的逻辑一超额就取消正在训练的作业 ——
# 一个不可逆动作绑在一个抖动阈值上。实测 13:35:57 超额 43 就砍了 cost=211 的
# 作业,而 13:38:16 自己就回到 1905 <= 1984 了。
# --sustained-over-seconds N:必须连续 N 秒都处于超额才动手;中间任何一次
# 回到 cap 以内就清零重新计时。默认 0 = 完全保持原行为(对未传该参数的实例零影响)。
_OVER_SINCE = {}


def one_pass(args):
    income = bc.get_income()
    if income <= 0:
        print(f"[enforcer] {_ts()} WARN: cannot read G9 income; skipping pass (fail-safe: no cancels).")
        return
    limit = income / 10.0
    prod, prod_total, batch_total = active_prod_jobs(args.jobs_file, args.cache_file)
    over = prod_total - limit
    mode = "DRY-RUN" if not args.arm else "ARMED"
    print(f"[enforcer] {_ts()} [{mode}] income={income:.0f} cap(income/10)={limit:.0f} | "
          f"PROD active={len(prod)} cost={prod_total:.0f} | BATCH cost={batch_total:.0f} (ignored)")
    if prod_total <= limit:
        if _OVER_SINCE.pop(args.jobs_file, None) is not None:
            print(f"[enforcer] {_ts()} back under cap; sustained-over timer reset.")
        print(f"[enforcer] {_ts()} OK: PROD {prod_total:.0f} <= cap {limit:.0f}; nothing to pause.")
        return
    sustained = float(getattr(args, 'sustained_over_seconds', 0) or 0)
    if sustained > 0:
        now = time.time()
        since = _OVER_SINCE.get(args.jobs_file)
        if since is None:
            _OVER_SINCE[args.jobs_file] = now
            print(f"[enforcer] {_ts()} OVER by {over:.0f}, but --sustained-over-seconds="
                  f"{sustained:.0f}: starting timer, no action this pass "
                  f"(must stay over for {sustained:.0f}s).")
            return
        held = now - since
        if held < sustained:
            print(f"[enforcer] {_ts()} OVER by {over:.0f} for {held:.0f}s < "
                  f"{sustained:.0f}s; holding off (transient income/cap swing?).")
            return
        print(f"[enforcer] {_ts()} OVER by {over:.0f} SUSTAINED {held:.0f}s "
              f">= {sustained:.0f}s; proceeding to pause.")
    to_cancel, projected = plan_cancellations(prod, prod_total, limit)
    print(f"[enforcer] {_ts()} OVER by {over:.0f}. Plan: PAUSE {len(to_cancel)} most-expensive "
          f"PROD job(s) -> projected {projected:.0f} <= {limit:.0f} (pauses the fewest jobs; "
          f"each is cancelled + re-queued as a resume, relaunched from checkpoint when cheap):")
    for r in to_cancel:
        print(f"[enforcer]     - xid={r['xid']} cost={r['cost']:.0f} {r['tpu_type']} {r['tier']} {r['name']}")

    # ★Verify against XM before acting: the ledger keeps dead jobs SUBMITTED,
    # and cancelling one books its cost as savings that never materialise.
    to_cancel, skipped = drop_dead_candidates(to_cancel)
    for r in skipped:
        print(f"[enforcer]     ~ SKIP xid={r['xid']} cost={r['cost']:.0f} {r['name']}: "
              f"XM says {r['_skip_reason']}, not RUNNING -- cancelling it would "
              f"free nothing and would hide the job that is actually spending. "
              f"(ledger still says SUBMITTED; stale row)")
    if skipped and not to_cancel:
        print(f"[enforcer] {_ts()} every candidate was already dead; nothing to pause "
              f"this pass. The overage is an accounting artefact of the stale "
              f"ledger, not live spend.")
        return
    if skipped:
        freed = sum(r['cost'] for r in to_cancel)
        print(f"[enforcer] {_ts()} after XM verification: pausing {len(to_cancel)} live "
              f"job(s), freeing {freed:.0f} (skipped {len(skipped)} dead).")
    if len(to_cancel) > args.max_cancels:
        print(f"[enforcer] {_ts()} SAFETY: plan wants {len(to_cancel)} pauses > --max-cancels="
              f"{args.max_cancels}; capping to {args.max_cancels} this pass (rest next pass).")
        to_cancel = to_cancel[:args.max_cancels]
    if not args.arm:
        print(f"[enforcer] {_ts()} DRY-RUN: no jobs paused. Re-run with --arm to enforce.")
        return
    for r in to_cancel:
        ok, out = pause_and_requeue(r, args.jobs_file, dry_run=False,
                                    local_queue_file=args.local_queue_file,
                                    unsafe_blind_resume=args.unsafe_blind_resume)
        tag = "OK" if ok else "FAILED"
        print(f"[enforcer] {_ts()} pause {r['xid']} -> {tag}. {_tail(out)}")


def _tail(s, n=200):
    s = (s or '').strip().replace('\n', ' ')
    return s[-n:]


def _ts():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%SZ')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--arm', action='store_true',
                    help='Actually cancel jobs. WITHOUT this, dry-run only (default).')
    ap.add_argument('--once', action='store_true', help='Single pass then exit.')
    ap.add_argument('--interval', type=float, default=120.0, help='Loop period seconds (default 120).')
    ap.add_argument('--max-cancels', type=int, default=3,
                    help='Max jobs cancelled per pass (safety throttle, default 3).')
    ap.add_argument('--jobs-file', default=os.path.expanduser('~/.tpu_jobs.json'),
                    help='Registry to enforce (default ~/.tpu_jobs.json; point at npu/lyy for that agent).')
    ap.add_argument('--cache-file', default=os.path.expanduser('~/.tpu_check_cache.txt'),
                    help='Check-cache for the zombie filter.')
    ap.add_argument('--unsafe-blind-resume', action='store_true',
                    help='DANGEROUS. Restore the old behaviour of re-enqueueing a '
                         'bare --launch=resume_xid=<XID> after pausing. That entry '
                         'carries no --config, so xm_launcher falls back to its '
                         'default (remote_run) and writes over the original '
                         "checkpoint prefix with the wrong recipe. Default off: "
                         'the pause is recorded for manual resume instead.')
    ap.add_argument('--sustained-over-seconds', type=float, default=0.0,
                    help='Only pause after PROD cost has stayed OVER the cap for this '
                         'many CONSECUTIVE seconds (any pass back under cap resets the '
                         'timer). Guards against transient income/cap swings. '
                         'Default 0 = original behaviour (act on the first over pass).')
    ap.add_argument('--local-queue-file', default=None,
                    help='Local queue to re-enqueue paused resumes into. MUST match '
                         'the agent (npu: ~/lyy-work/.npu_local_queue.json). If unset, '
                         'resumes land in the default tpu queue -- only correct for tpu.')
    args = ap.parse_args()

    if args.once:
        one_pass(args)
        return
    print(f"[enforcer] start {_ts()} interval={args.interval}s arm={args.arm} "
          f"max_cancels={args.max_cancels} jobs_file={args.jobs_file} "
          f"sustained_over={args.sustained_over_seconds:.0f}s "
          f"blind_resume={'ON(DANGEROUS)' if args.unsafe_blind_resume else 'off(records pending)'} "
          f"local_queue={args.local_queue_file or '<UNSET -- resumes leak to default tpu queue!>'}")
    while True:
        try:
            one_pass(args)
        except Exception as e:
            print(f"[enforcer] {_ts()} pass error (continuing): {e}", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
