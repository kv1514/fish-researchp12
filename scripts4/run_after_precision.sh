#!/bin/bash
# Run the at-ask-time screens once the pre-registered precision run is done.
# Chained rather than parallel for the same reason as before: the precision run
# is the expensive pre-registered one and its power was computed in advance.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/at_ask.log
while [ "$(python - <<'PY' 2>/dev/null || echo 0
import json
rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
print(sum(1 for r in rows if 'PRECISION' in (r.get('label') or '')))
PY
)" -lt 6 ]; do sleep 90; done
echo "precision complete; starting at_ask screens"
python scripts4/duel.py jobs/j23_at_ask.json 3 >> "$LOG" 2>&1
echo "AT_ASK SCREENS COMPLETE"
