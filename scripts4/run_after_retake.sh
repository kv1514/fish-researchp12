#!/bin/bash
# Launch the pre-registered second precision rung once the retake-gate blocks
# land. Unconditional: jobs/PREREGISTRATION_precision2.md fixes the design.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/precision2.log

n_with() {
  python - "$1" <<'PYEOF' 2>/dev/null || echo -1
import json, sys
key = sys.argv[1]
rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
print(sum(1 for r in rows if key in (r.get('label') or '')))
PYEOF
}
regen() {
  python - <<'PYEOF'
import json, pathlib
jobs = json.loads(pathlib.Path('jobs/j27_precision2.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j27b_precision2_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PYEOF
}

while [ "$(n_with 'RETAKE GATE')" -lt 2 ]; do sleep 120; done
echo "$(date +%H:%M:%S) retake-gate run finished; starting precision rung 2"
restarts=0
while true; do
  n=$(n_with 'PRECISION2')
  [ "$n" -ge 6 ] && { echo "all six precision2 blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j27b_precision2_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 20 ] && { echo "giving up at $n/6"; break; }
    echo "$(date +%H:%M:%S) starting precision2 blocks - run #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j27b_precision2_resume.json 3 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 25
  fi
  sleep 60
done
echo "PRECISION RUNG 2 DONE"
