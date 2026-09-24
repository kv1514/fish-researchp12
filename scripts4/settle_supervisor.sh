#!/bin/bash
# Keep the pre-registered settling run alive until all six blocks are recorded.
#
# The run has already been lost once with no partial record and no error, which
# on an append-only design costs whatever the interrupted block had played. The
# resume is safe to repeat because it is regenerated from the results file each
# time: only blocks that produced NOTHING are re-run, with the base and agent
# seeds fixed in jobs/j20_lookahead_settle.json. A block that has already written
# a number is never re-run, which is the line that matters -- re-rolling a block
# whose result you have seen would turn an unselected run into a selected one.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/settle_resume.log

count() {
  python - <<'PY' 2>/dev/null || echo -1
import json
try:
    rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
    print(sum(1 for r in rows if 'SETTLE' in (r.get('label') or '')))
except Exception:
    print(-1)
PY
}

regen() {
  python - <<'PY'
import json, pathlib
jobs = json.loads(pathlib.Path('jobs/j20_lookahead_settle.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j20b_settle_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PY
}

restarts=0
while true; do
  n=$(count)
  [ "$n" -ge 6 ] && { echo "all six blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j20b_settle_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    if [ "$restarts" -gt 12 ]; then
      echo "giving up after $restarts restarts at $n/6 blocks"; break
    fi
    echo "$(date +%H:%M:%S) workers gone at $n/6 - restart #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j20b_settle_resume.json 3 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 20
  fi
  sleep 45
done
echo "SUPERVISOR DONE"
