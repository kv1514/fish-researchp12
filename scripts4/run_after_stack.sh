#!/bin/bash
# Launch the pre-registered retake-gate run once the stacking blocks land.
# Unconditional on what they say: jobs/PREREGISTRATION_retake_gate.md fixes the
# design, states the five prior failures in this family up front, and commits a
# positive result to a replication rather than to a paragraph.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/retake_gate.log

n_with() {
  python - "$1" <<'PY' 2>/dev/null || echo -1
import json, sys
key = sys.argv[1]
rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
print(sum(1 for r in rows if key in (r.get('label') or '')))
PY
}
regen() {
  python - <<'PY'
import json, pathlib
jobs = json.loads(pathlib.Path('jobs/j26_retake_gate.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j26b_retake_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PY
}

while [ "$(n_with 'STACK lookahead')" -lt 6 ]; do sleep 120; done
echo "$(date +%H:%M:%S) stacking run finished; starting the retake-gate run"
restarts=0
while true; do
  n=$(n_with 'RETAKE GATE')
  [ "$n" -ge 2 ] && { echo "both retake-gate blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j26b_retake_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 12 ] && { echo "giving up at $n/2"; break; }
    echo "$(date +%H:%M:%S) starting retake-gate blocks - run #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j26b_retake_resume.json 2 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 25
  fi
  sleep 60
done
echo "RETAKE GATE RUN DONE"
