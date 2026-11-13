#!/bin/bash
# Launch the pre-registered retake-BONUS run once the claim-threshold blocks
# land. Unconditional on what anything before it says:
# jobs/PREREGISTRATION_combined.md fixes the design, states the six prior
# nulls in this family up front, and commits a positive to a replication rather
# than to a paragraph.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/combined.log

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
jobs = json.loads(pathlib.Path('jobs/j31_combined.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j31b_combined_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PY
}

while [ "$(n_with 'RETAKE BONUS')" -lt 2 ]; do sleep 120; done
echo "$(date +%H:%M:%S) retake-bonus run finished; starting the combined-config run"
restarts=0
while true; do
  n=$(n_with 'COMBINED 480+lookahead')
  [ "$n" -ge 2 ] && { echo "both combined-config blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j31b_combined_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 12 ] && { echo "giving up at $n/2"; break; }
    echo "$(date +%H:%M:%S) starting combined-config blocks - run #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j31b_combined_resume.json 2 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 25
  fi
  sleep 60
done
echo "COMBINED RUN DONE"
