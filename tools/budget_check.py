#!/usr/bin/env python3
import datetime
import json
import re
import sys
import os

# ---- Groups EXEMPT from the G9 income/10 credit cap -----------------------
# g3 (gdm-viscam-interns-dynamic) and g5 (vqfree-xm) are separate dynamic pools
# with their OWN credit balance; they do NOT draw on G9's income, so the 1/10-
# of-G9 gate must not ration them. Two consequences, both handled below:
#   1. a NEW job whose group is g3/g5 is admitted regardless of the G9 aggregate;
#   2. an already-running g3/g5 job is NOT summed into `current_cost` (it never
#      spent G9 credit, so counting it would falsely inflate the G9 total).
# Matched against the registry's `alloc` string and the g3/g5 id/`gN` forms the
# wrapper may pass. (router._GROUP_PREF is the sibling that ROUTES here first.)
_EXEMPT_ALLOC_FRAGMENTS = ('gdm-viscam-interns-dynamic', 'vqfree-xm')
_EXEMPT_GROUP_IDS = {'3', '5', 'g3', 'g5'}


def is_exempt_group(group_or_alloc):
    """True if the group/alloc is a G9-cap-exempt pool (g3/g5).

    Accepts a bare id ('3', 'g5'), or a full alloc string
    ('group:deepmind-dynamic/vqfree-xm'). Empty/None -> not exempt (fail-closed:
    an unknown caller is treated as drawing on the capped G9 budget).
    """
    s = str(group_or_alloc or '').strip().lower()
    if not s:
        return False
    if s in _EXEMPT_GROUP_IDS:
        return True
    return any(frag in s for frag in _EXEMPT_ALLOC_FRAGMENTS)


def get_income():
    money_file = os.path.expanduser("~/.tpu_quota_cache_dir/money.txt")
    if not os.path.exists(money_file):
        return 0
    with open(money_file) as f:
        content = f.read()
    # Strip ANSI escape sequences
    content = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', content)
    mtch = re.search(r"G9\s*│[^│]*│[^│]*│\s+([\d\.]+)\s+Credits/hr", content)
    if mtch:
        return float(mtch.group(1))
    return 0


# Rows whose status never migrates out of SUBMITTED/RUNNING accumulate forever
# (2026-08-21: a sibling registry reached 588 stale rows / 814,400 credits/hr
# and the guard refused every submission). The check cache only clears rows it
# still renders, so a row ABSENT from the cache needs an age fallback. Launch
# time is derived from the timestamps embedded in the run paths; a row with no
# parseable timestamp keeps counting (fail-closed).
STALE_HOURS = 48.0
_TS8_RE = re.compile(r'_(20\d{6})_(\d{6})')
_TS6_RE = re.compile(r'_(\d{6})_(\d{6})')

def job_age_hours(info):
    for key in ('bucket_cp_path', 'stagedir', 'logdir', 'launch_log'):
        text = str(info.get(key, ''))
        m = _TS8_RE.search(text)
        fmt = '%Y%m%d%H%M%S'
        if not m:
            m = _TS6_RE.search(text)
            fmt = '%y%m%d%H%M%S'
        if not m:
            continue
        try:
            ts = datetime.datetime.strptime(m.group(1) + m.group(2), fmt)
        except ValueError:
            continue
        return (datetime.datetime.now() - ts).total_seconds() / 3600.0
    return None

def get_default_cap(tpu_type):
    arch = tpu_type.split('-')[0].lower()
    mapping = {
        'v4': 12,
        'v5p': 60,
        'v5e': 30,
        'v6e': 80,
        'v6p': 180,
    }
    return mapping.get(arch, 100)

# ---------------------------------------------------------------- market price
# WHY: the cap table below is a LIMIT-ORDER table -- a blast-radius bound, set at
# roughly 3x an observed price and deliberately generous. Reusing it to *account*
# for spend over-states every job, unevenly, and on 2026-08-21 it had the two
# chip types the operator actually chooses between ranked backwards:
#
#     accounting  v6p 180/chip  >  v7 100/chip   (v7 is not even in the table;
#     market      v6p 19.34     <  v7 30.00       it falls through to the 100)
#
# so the guard pushed work toward the more expensive chip. Over-statement ranged
# from 2.5x (v5p) to 92x (v4) -- the cheapest chip was billed the most heavily
# relative to its price. lyy asked for market-based accounting (2026-08-21).
#
# A guard must not fail open, so this is layered: market price when it can be
# read AND is fresh, otherwise the old cap. Both paths are announced, because a
# silent switch between two costing bases is the kind of thing that later reads
# as "the numbers changed for no reason".
#
# NOTE ON VOLATILITY: these are spot clearing prices and they move -- v4 went
# 0.13 -> 6.00 within two hours on the day this was written. Accounting at spot
# therefore makes admission time-dependent: the same batch can pass now and be
# refused twenty minutes later. That is a real behaviour change from the fixed
# caps, and it is the trade the caller asked for.
MONEY_CACHE = os.path.expanduser("~/.tpu_quota_cache_dir/money.txt")
MONEY_MAX_AGE_H = 6.0


def _cell(line, i):
    parts = line.split('\u2502')
    return parts[i].strip() if len(parts) > i else ''


def market_prices():
    """{'v7': 25.08, ...} PROD median credits per chip-hour, or {} if unusable.

    Parses per COLUMN, not per line: the price cell wraps onto following rows
    ("Credits/hr (median" / "25.08, n=19)"), and joining whole lines splices the
    neighbouring columns in between, which silently breaks exactly the widest
    row -- v7, whose range runs to five figures. Per-column joining was the
    difference between five families parsed and six.
    """
    try:
        age_h = (datetime.datetime.now()
                 - datetime.datetime.fromtimestamp(os.path.getmtime(MONEY_CACHE))
                 ).total_seconds() / 3600.0
        if age_h > MONEY_MAX_AGE_H:
            return {}
        raw = open(MONEY_CACHE).read()
    except OSError:
        return {}
    raw = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', raw)
    lines = raw.splitlines()
    out = {}
    for i, ln in enumerate(lines):
        if '\u2502' not in ln:
            continue
        m = re.match(r'TPU\s+(v\d+[a-z]?)$', _cell(ln, 1))
        if not m or _cell(ln, 2) != 'PROD':
            continue
        blob = " ".join(_cell(lines[j], 3) for j in range(i, min(i + 4, len(lines))))
        mm = re.search(r'median\s+([\d.]+)\s*,\s*n=(\d+)', blob)
        if mm:
            out[m.group(1).lower()] = float(mm.group(1))
            continue
        # Some families print a single median value with no "(median X, n=Y)"
        # continuation row -- e.g. v7 shows just "20.00 Credits/hr" (or a
        # "A-B Credits/hr" range). The n=-based regex above misses these, so the
        # price silently fell back to the conservative cap (100 cr/chip-hr for
        # v7 = ~5x the real price), inflating the whole fleet's projected spend
        # ~4x and refusing every new PROD job. Fall back to the first numeric
        # value in front of "Credits/hr" (the low/floor of a range, matching the
        # 'median' semantics of taking the representative low price).
        mm2 = re.search(r'([\d.]+)\s*(?:[\u2013\u2014-]\s*[\d.]+\s*)?Credits/hr', blob)
        if mm2:
            out[m.group(1).lower()] = float(mm2.group(1))
    return out


_MARKET = None


def chip_price(tpu_type):
    """(credits per chip-hour, basis) -- market when fresh, else the cap."""
    global _MARKET
    if _MARKET is None:
        _MARKET = market_prices()
    arch = tpu_type.split('-')[0].lower()
    if arch in _MARKET:
        return _MARKET[arch], 'market'
    return get_default_cap(tpu_type), 'cap'


def parse_tpu_type(tpu_type):
    parts = tpu_type.strip().split('-')
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return 0

def get_job_cost(tpu_type, tier, override=None):
    if tier.upper() == 'BATCH':
        return 0.0
    chips = parse_tpu_type(tpu_type)
    # An explicit --lo-price still wins: it is the operator saying "price this
    # one at N", and silently overriding that with the market would defeat the
    # only per-job control there is.
    if override and str(override).strip() and str(override) != "0":
        try:
            return chips * float(override)
        except ValueError:
            pass
    price, _basis = chip_price(tpu_type)
    return chips * price

def main():
    if len(sys.argv) < 3:
        print("Usage: budget_check.py <new_tpu_type> <new_tier> [new_lo_price]")
        sys.exit(1)
        
    new_tpu_type = sys.argv[1]
    new_tier = sys.argv[2]
    new_lo_price = sys.argv[3] if len(sys.argv) > 3 else None
    # Optional 4th arg (or TPU_NEW_GROUP env) = the new job's group/alloc. Lets
    # the gate exempt a g3/g5 launch (own balance, not the G9 cap). Optional and
    # forward-compatible: absent -> treated as capped G9 (fail-closed), so the
    # gate is unchanged until the wrapper is taught to pass it.
    new_group = (sys.argv[4] if len(sys.argv) > 4
                 else os.environ.get('TPU_NEW_GROUP', ''))

    income = get_income()
    if income <= 0:
        print("\033[33m[budget check] Warning: Could not read G9 income, skipping budget limit check.\033[0m")
        sys.exit(0)
        
    # Credit hard cap = 1/10 of G9 income (operator 2026-08-25: tightened from
    # 1/5 to 1/10 per boss directive to further reduce credit usage; was 1/3
    # before that -- applies to BOTH the tpu and npu/lyy agents since both run
    # through this same gate, so qiaos and lyy are each capped at 1/10).
    limit = income / 10.0
    jobs_file = os.environ.get('TPU_JOBS_FILE', os.path.expanduser('~/.tpu_jobs.json'))
    agent_name = "npu" if "npu" in jobs_file else "tpu"
    
    current_cost = 0.0
    cache_file = os.environ.get('TPU_CHECK_CACHE_FILE', os.path.expanduser('~/.tpu_check_cache.txt'))
    cache_status = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cf_content = f.read()
                cf_content = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', cf_content)
                for m in re.finditer(r'│\s*(\d{8,11})\s*│\s*([A-Za-z0-9_-]+)\s*│', cf_content):
                    cache_status[m.group(1)] = m.group(2).lower()
        except Exception as e:
            print(f"\033[33m[budget check] Warning: Error parsing {cache_file}: {e}\033[0m")

    if os.path.exists(jobs_file):
        try:
            with open(jobs_file, 'r') as f:
                jobs = json.load(f)
                stale_rows, stale_cost = 0, 0.0
                for xid, info in jobs.items():
                    # Only count active jobs (SUBMITTED or RUNNING)
                    if info.get('status') in ['SUBMITTED', 'RUNNING']:
                        # Count SUBMITTED-and-PENDING as well as RUNNING against
                        # the bar (operator 2026-08-27, option B): a job the
                        # scheduler has committed to the XM queue reserves budget
                        # even before its Borg gang is RUNNING, so the drainer
                        # cannot flood the queue with an unbounded backlog of
                        # pending jobs that each look free. The reroute lane
                        # (pending > 600s -> auto-cancel + requeue) bounds how
                        # long any one pending job can hold that reservation, so
                        # it can never occupy the bar permanently. We still drop
                        # ZOMBIES: a row whose live check-cache state is terminal
                        # (not running/pending/queued) is no longer real load.
                        if xid in cache_status and cache_status[xid] not in ['running', 'pending', 'queued']:
                            continue
                        # g3/g5 draw on their own balance, not G9's income, so a
                        # job there never spends the budget this gate protects --
                        # exclude it from the G9 aggregate. (Kept from the earlier
                        # change; operator has not revisited the g3/g5 exemption.)
                        if is_exempt_group(info.get('alloc', '')):
                            continue
                        cost = get_job_cost(info.get('tpu_type', ''), info.get('tier', 'PROD'))
                        if xid not in cache_status:
                            age = job_age_hours(info)
                            if age is not None and age > STALE_HOURS:
                                # Absent from the live cache AND older than any real
                                # job here runs: a never-migrated corpse, not load.
                                stale_rows += 1
                                stale_cost += cost
                                continue
                        current_cost += cost
                if stale_rows:
                    print(f"\033[33m[budget check] Warning: excluded {stale_rows} stale registry row(s) "
                          f"(status never migrated, >{STALE_HOURS:.0f}h old, absent from check cache) "
                          f"worth {stale_cost:.1f} credits/hr -- reconcile the registry.\033[0m")
        except Exception as e:
            print(f"\033[33m[budget check] Warning: Error parsing {jobs_file}: {e}\033[0m")
                
    new_cost = get_job_cost(new_tpu_type, new_tier, new_lo_price)
    total_cost = current_cost + new_cost
    
    _p, _basis = chip_price(new_tpu_type)
    print(f"\033[36m[budget check] pricing basis: {_basis} "
          f"({new_tpu_type.split('-')[0]} @ {_p:.2f} cr/chip-hr)"
          + ("" if _basis == 'market' else "  [market cache missing or >6h old; using the conservative cap]")
          + "\033[0m")
    print(f"\033[36m[budget check] {agent_name} agent current cost: {current_cost:.1f} credits/hr\033[0m")
    print(f"\033[36m[budget check] new job cost: {new_cost:.1f} credits/hr\033[0m")
    print(f"\033[36m[budget check] total projected: {total_cost:.1f} (Limit: {limit:.1f} = 1/10 of G9 income {income:.1f})\033[0m")

    # A g3/g5 launch draws on that pool's OWN credit balance, not G9's income,
    # so the 1/10-of-G9 cap does not apply to it. Admit regardless of the G9
    # aggregate (mirrors the BATCH/CPU hatches below). Only fires when the group
    # is actually known -- an unknown/absent group falls through to the capped
    # G9 path (fail-closed). The wrapper passes it as argv[4] / TPU_NEW_GROUP.
    if is_exempt_group(new_group):
        print(f"\033[32m[budget check] new job group '{new_group}' is g3/g5 "
              f"(own balance, exempt from the G9 income/10 cap) -- admitted "
              f"regardless of the G9 aggregate.\033[0m")
        sys.exit(0)

    # A BATCH-tier job draws from the free BATCH pool (clears at 0) and does NOT
    # consume the PROD income/10 budget this gate protects, so it must never be
    # refused on account of the PROD aggregate. Without this, a zero-cost BATCH
    # submission is still blocked whenever PROD is already over budget -- exactly
    # when BATCH is the correct escape hatch. `new_cost` is already 0 for BATCH
    # (get_job_cost), so admit it regardless of current_cost.
    if new_tier.upper() == 'BATCH':
        print(f"\033[32m[budget check] new job is BATCH (free pool, 0 PROD cost) -- "
              f"admitted regardless of PROD aggregate.\033[0m")
        sys.exit(0)

    # A CPU-ONLY ask has no chips, so it cannot consume the budget this gate
    # protects. The limit is 1/10 of G9 *chip* income and every cost above is
    # chips x clearing price; `npu money` reports G8 -- the pool these run in --
    # as a Static Pool with 0.0 bidding power and no credit balance at all. This
    # is the same situation the BATCH branch exists for: a zero-cost submission
    # refused on account of a PROD aggregate it does not contribute to. That
    # hatch keys on tier, and CPU jobs are submitted with no tier, so they
    # arrive here as PROD and fall through it.
    #
    # WHY THIS IS A POSITIVE TEST AND NOT `if new_cost == 0`. parse_tpu_type
    # splits on '-' and returns 0 chips for anything that is not
    # "<name>-<digits>", so new_cost is ALREADY 0 for every type it fails to
    # parse -- a typo like "v7_32", or any future naming scheme. Bypassing on
    # cost==0 would wave all of those through, turning a parser miss into an
    # unbounded spend path: fail-open, in the one place that has to fail closed.
    # Naming the CPU case explicitly keeps unrecognised TPU types on the
    # refusing side. (Added 2026-08-26 at lyy's request, after four CPU corpora
    # on the free pool were refused by a G9 credit budget they cannot spend.)
    if new_tpu_type.strip().lower().startswith('cpu'):
        print(f"\033[32m[budget check] new job is CPU-only ({new_tpu_type}) -- no chips, "
              f"does not draw on the G9 chip budget; admitted regardless of aggregate.\033[0m")
        sys.exit(0)

    if total_cost > limit:
        print(f"\033[31m[budget check] ERROR: Budget exceeded for {agent_name} check! Total projected cost ({total_cost:.1f}) exceeds the 1/10 limit ({limit:.1f}) of G9 income.\033[0m")
        sys.exit(2)
        
    sys.exit(0)

if __name__ == '__main__':
    main()
