#!/bin/bash
# Keep the pre-registered precision run alive until all six blocks are recorded.
# Same contract as the settling run's supervisor: the resume file is regenerated
# from the results each time, so only blocks that produced NOTHING are re-run,
# always with the seeds fixed in jobs/j22_precision.json. A block that has
# written a number is never re-rolled -- doing so after seeing it would turn an
# unselected run into a selected one.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/precision.log

count() {
  python - <<'PY' 2>/dev/null || echo -1
import json
try:
    rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
    print(sum(1 for r in rows if 'PRECISION' in (r.get('label') or '')))
except Exception:
    print(-1)
PY
}

regen() {
  python - <<'PY'
import json, pathlib
jobs = json.loads(pathlib.Path('jobs/j22_precision.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j22b_precision_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PY
}

restarts=0
while true; do
  n=$(count)
  [ "$n" -ge 6 ] && { echo "all six precision blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j22b_precision_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    if [ "$restarts" -gt 12 ]; then
      echo "giving up after $restarts restarts at $n/6"; break
    fi
    echo "$(date +%H:%M:%S) starting precision blocks - run #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j22b_precision_resume.json 3 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 25
  fi
  sleep 60
done
echo "PRECISION SUPERVISOR DONE"
