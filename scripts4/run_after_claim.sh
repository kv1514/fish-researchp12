#!/bin/bash
# Launch the pre-registered retake-BONUS run once the claim-threshold blocks
# land. Unconditional on what anything before it says:
# jobs/PREREGISTRATION_retake_bonus.md fixes the design, states the six prior
# nulls in this family up front, and commits a positive to a replication rather
# than to a paragraph.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/retake_bonus.log

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
jobs = json.loads(pathlib.Path('jobs/j30_retake_bonus.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j30b_bonus_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PY
}

while [ "$(n_with 'CLAIM THRESHOLD')" -lt 2 ]; do sleep 120; done
echo "$(date +%H:%M:%S) claim-threshold run finished; starting the retake-bonus run"
restarts=0
while true; do
  n=$(n_with 'RETAKE BONUS')
  [ "$n" -ge 2 ] && { echo "both retake-bonus blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j30b_bonus_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 12 ] && { echo "giving up at $n/2"; break; }
    echo "$(date +%H:%M:%S) starting retake-bonus blocks - run #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j30b_bonus_resume.json 2 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 25
  fi
  sleep 60
done
echo "RETAKE BONUS RUN DONE"
