#!/bin/bash
# Launch the pre-registered claim-threshold run once precision rung 2 lands.
# Unconditional: jobs/PREREGISTRATION_claim_threshold.md fixes the design.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/claim_threshold.log

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
jobs = json.loads(pathlib.Path('jobs/j28_claim_threshold.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j28b_claim_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PYEOF
}

while [ "$(n_with 'PRECISION2')" -lt 6 ]; do sleep 120; done
echo "$(date +%H:%M:%S) precision rung 2 finished; starting the claim-threshold run"
restarts=0
while true; do
  n=$(n_with 'CLAIM THRESHOLD')
  [ "$n" -ge 2 ] && { echo "both claim-threshold blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j28b_claim_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 12 ] && { echo "giving up at $n/2"; break; }
    echo "$(date +%H:%M:%S) starting claim-threshold blocks - run #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j28b_claim_resume.json 2 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 25
  fi
  sleep 60
done
echo "CLAIM THRESHOLD RUN DONE"
