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


def pause_and_requeue(r, jobs_file, dry_run, local_queue_file=None):
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
    # 2) re-enqueue as a resume so it re-launches when cheap again
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
        print(f"[enforcer] {_ts()} OK: PROD {prod_total:.0f} <= cap {limit:.0f}; nothing to pause.")
        return
    to_cancel, projected = plan_cancellations(prod, prod_total, limit)
    print(f"[enforcer] {_ts()} OVER by {over:.0f}. Plan: PAUSE {len(to_cancel)} most-expensive "
          f"PROD job(s) -> projected {projected:.0f} <= {limit:.0f} (pauses the fewest jobs; "
          f"each is cancelled + re-queued as a resume, relaunched from checkpoint when cheap):")
    for r in to_cancel:
        print(f"[enforcer]     - xid={r['xid']} cost={r['cost']:.0f} {r['tpu_type']} {r['tier']} {r['name']}")
    if len(to_cancel) > args.max_cancels:
        print(f"[enforcer] {_ts()} SAFETY: plan wants {len(to_cancel)} pauses > --max-cancels="
              f"{args.max_cancels}; capping to {args.max_cancels} this pass (rest next pass).")
        to_cancel = to_cancel[:args.max_cancels]
    if not args.arm:
        print(f"[enforcer] {_ts()} DRY-RUN: no jobs paused. Re-run with --arm to enforce.")
        return
    for r in to_cancel:
        ok, out = pause_and_requeue(r, args.jobs_file, dry_run=False,
                                    local_queue_file=args.local_queue_file)
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
    ap.add_argument('--local-queue-file', default=None,
                    help='Local queue to re-enqueue paused resumes into. MUST match '
                         'the agent (npu: ~/lyy-work/.npu_local_queue.json). If unset, '
                         'resumes land in the default tpu queue -- only correct for tpu.')
    args = ap.parse_args()

    if args.once:
        one_pass(args)
        return
    print(f"[enforcer] start {_ts()} interval={args.interval}s arm={args.arm} "
          f"max_cancels={args.max_cancels} jobs_file={args.jobs_file}")
    while True:
        try:
            one_pass(args)
        except Exception as e:
            print(f"[enforcer] {_ts()} pass error (continuing): {e}", file=sys.stderr)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
