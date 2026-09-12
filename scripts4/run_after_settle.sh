#!/bin/bash
# Wait for the pre-registered settling run to finish, then run the follow-on
# screens. Chained rather than parallel because the box has 4 cores and the
# settling run owns 3 of them; starting the screens now would slow the run whose
# power was computed in advance, which is the one thing that must not move.
cd /home/user/fish-researchp12
while [ "$(python - <<'PY'
import json
rows=[json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
print(sum(1 for r in rows if 'SETTLE' in (r.get('label') or '')))
PY
)" -lt 6 ]; do sleep 60; done
echo "settle complete; starting follow-on screens"
python scripts4/duel.py jobs/j21_screen_followon.json 3
echo "FOLLOW-ON SCREENS COMPLETE"
