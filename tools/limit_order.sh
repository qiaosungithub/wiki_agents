#!/bin/bash
# limit_order.sh -- inspect and set GQM price caps (limit orders) safely.
#
# WHY THIS EXISTS
# A limit order is a maximum price per chip-hour a workload will pay. When the
# market clears above it the job is pulled from the queue BEFORE any capacity
# check, so free chips do not help. It is not a system parameter -- it is a
# number a person typed, and a teammate's GROUP-level cap silently applies to
# your jobs. "My job is pending for no reason" is frequently someone else's cap.
#
# THE THREE THINGS THIS TOOL MAKES HARD TO GET WRONG
#  1. It SHOWS before it SETS. `status` answers "is a cap even the problem?"
#     against the live clearing price, so you do not raise a cap that was never
#     firing. Measured case: a v6p probe was reported as price-capped while its
#     group had no cap row at all and the market cleared 10x under the default.
#  2. Group scope is opt-in and loud. `--mdb` changes EVERY job of EVERY member
#     of that group. This script refuses it without --i-understand-group-scope.
#  3. Dry run is the default for any write. You must pass --apply to commit.
#
# Reference: ../infra/quota_market.md (scope table, lease exemption, the rule
# that the comparison uses the POOL-WIDE price, so moving cells never unblocks
# a triggered cap).
set -uo pipefail

BIN=/google/bin/releases/brain-quota/set_limit_order/set_limit_order
MARKET="$HOME/.tpu_quota_cache_dir/market.json"
# GQM keys accelerators by numeric product id; market.json uses the same ids.
# ../tpu_reference.md owns the mapping. Only the ones we actually run.
declare -A PRODUCT=( [v4]=34 [v5e]=59 [v5p]=60 [v6e]=76 [v6p]=92 [v7]=101 )

usage() {
  cat <<'USAGE'
limit_order.sh -- GQM price caps, read-first.

  status [<accel>]              Show live price vs every cap in force.
                                <accel> one of v4 v5e v5p v6e v6p v7 (default: all)
  show-xid <xid>                What cap applies to one experiment, and the
                                price it is being compared against.
  set-xid <xid> <price>         Cap ONE experiment. Dry run unless --apply.
  clear-xid <xid>               Remove an experiment's cap (price=-1).
  set-group <mdb> <accel> <price>
                                Cap a WHOLE GROUP. Requires --apply AND
                                --i-understand-group-scope. Affects everyone.

Flags:  --apply       actually commit (default is dry run)
        --tier=PROD   resource tier for group ops (default PROD)
        --i-understand-group-scope   required for set-group

Examples:
  limit_order.sh status v6p
  limit_order.sh show-xid 278676322
  limit_order.sh set-xid 278676322 250            # dry run
  limit_order.sh set-xid 278676322 250 --apply    # commit
USAGE
}

APPLY=0; TIER=PROD; GROUP_OK=0; ARGS=()
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --tier=*) TIER="${a#*=}" ;;
    --i-understand-group-scope) GROUP_OK=1 ;;
    -h|--help) usage; exit 0 ;;
    *) ARGS+=("$a") ;;
  esac
done
set -- "${ARGS[@]:-}"
CMD="${1:-}"; [ -z "$CMD" ] && { usage; exit 1; }

# The market cache is written by the money checker each daemon round. A stale
# cache is worth saying out loud rather than silently comparing against an old
# price -- that is exactly how a frozen 31.223 was read as a live market for
# twelve hours.
price_table() {
  python3 - "$MARKET" "${1:-}" <<'PY'
import json, sys, time
path, want = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else '')
PRODUCT = {'v4': '34', 'v5e': '59', 'v5p': '60', 'v6e': '76', 'v6p': '92',
           'v7': '101'}
try:
    d = json.load(open(path))
except Exception as exc:
    print(f'  cannot read {path}: {exc}')
    print('  run:  (cd /google/src/cloud/qiaos/xm_test/google3 && '
          './blaze-bin/experimental/users/qiaos/tpu_utils/money_check)')
    sys.exit(1)
age = (time.time() - d.get('generated_unix', 0)) / 60
flag = '' if age < 5 else '   <-- STALE, refresh before trusting'
print(f'  market cache age: {age:.1f} min{flag}')
caps = d.get('limit_orders', {})
print()
print(f"  {'accel':<6} {'tier':<6} {'price':>10} {'group':<40} {'cap':>10}  verdict")
for accel, pid in PRODUCT.items():
    if want and accel != want:
        continue
    for tier in ('PROD', 'BATCH'):
        pr = d.get('prices', {}).get(f'deepmind-dynamic-pool|{pid}|{tier}')
        if not pr:
            continue
        price = pr.get('global')
        rows = [(k, v) for k, v in caps.items()
                if f'|{pid}|{tier}' in k]
        if not rows:
            print(f'  {accel:<6} {tier:<6} {price:>10} {"(no cap anywhere)":<40} '
                  f'{"-":>10}  cap cannot fire')
            continue
        for k, v in rows:
            grp = k.split('|')[1]
            cap = v['cap']
            # Strict greater-than: clearing exactly at the cap is affordable.
            verdict = ('BLOCKING' if price is not None and price > cap
                       else 'ok')
            print(f'  {accel:<6} {tier:<6} {price:>10} {grp:<40} {cap:>10}  '
                  f'{verdict} (set by {v["user"]})')
PY
}

case "$CMD" in
  status)
    echo "== live clearing price vs every limit order in force =="
    price_table "${2:-}"
    echo
    echo "  Reminder: the comparison uses the POOL-WIDE price, not a per-cell"
    echo "  one, so moving a job to a cheaper cell never unblocks a cap."
    ;;

  show-xid)
    XID="${2:?need an xid}"
    echo "== what the server thinks applies to XID $XID =="
    # --dry_run resolves pool / mdb / resource type FROM THE XID and prints the
    # payload without writing. That resolution is the useful part: it names the
    # group and accelerator the cap would attach to.
    timeout 120 "$BIN" --xid="$XID" --price=999999 --dry_run 2>&1 |
      grep -vE '^go/debugonly|^$' | sed 's/^/  /'
    echo
    echo "  (price=999999 above is a probe value for resolution only -- nothing"
    echo "   was written. Compare the group it names against 'status'.)"
    ;;

  set-xid)
    XID="${2:?need an xid}"; PRICE="${3:?need a price}"
    if [ "$APPLY" != "1" ]; then
      echo "== DRY RUN: cap XID $XID at $PRICE credits/chip-hour =="
      timeout 120 "$BIN" --xid="$XID" --price="$PRICE" --dry_run 2>&1 | sed 's/^/  /'
      echo
      echo "  Nothing was written. Re-run with --apply to commit."
    else
      echo "== APPLYING: cap XID $XID at $PRICE credits/chip-hour =="
      timeout 120 "$BIN" --xid="$XID" --price="$PRICE" 2>&1 | sed 's/^/  /'
    fi
    ;;

  clear-xid)
    XID="${2:?need an xid}"
    if [ "$APPLY" != "1" ]; then
      echo "== DRY RUN: REMOVE the cap on XID $XID (price=-1) =="
      timeout 120 "$BIN" --xid="$XID" --price=-1 --dry_run 2>&1 | sed 's/^/  /'
      echo "  Nothing was written. Re-run with --apply to commit."
    else
      timeout 120 "$BIN" --xid="$XID" --price=-1 2>&1 | sed 's/^/  /'
    fi
    ;;

  set-group)
    MDB="${2:?need an mdb group}"; ACCEL="${3:?need an accel}"; PRICE="${4:?need a price}"
    PID="${PRODUCT[$ACCEL]:-}"
    [ -z "$PID" ] && { echo "unknown accelerator '$ACCEL'"; exit 1; }
    # A group cap is the one genuinely dangerous operation this tool exposes:
    # it applies to every job of every member, including production training
    # somebody else is depending on right now.
    if [ "$APPLY" != "1" ] || [ "$GROUP_OK" != "1" ]; then
      echo "== DRY RUN (group scope): $MDB / $ACCEL / $TIER at $PRICE =="
      timeout 120 "$BIN" --mdb="$MDB" --resource_pool=deepmind-dynamic-pool \
        --resource_type=GHOSTFISH --resource_tier="$TIER" \
        --price="$PRICE" --dry_run 2>&1 | sed 's/^/  /'
      echo
      echo "  REFUSED to commit. A group cap changes EVERY job of EVERY member"
      echo "  of '$MDB'. To really do it, pass BOTH:"
      echo "      --apply --i-understand-group-scope"
      exit 0
    fi
    echo "== APPLYING GROUP CAP: $MDB / $ACCEL / $TIER at $PRICE =="
    timeout 120 "$BIN" --mdb="$MDB" --resource_pool=deepmind-dynamic-pool \
      --resource_type=GHOSTFISH --resource_tier="$TIER" --price="$PRICE" 2>&1 |
      sed 's/^/  /'
    ;;

  *) usage; exit 1 ;;
esac
