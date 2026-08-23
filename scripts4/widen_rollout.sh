#!/bin/bash
# Restart the v04 rollout pass wider once the duel queue stops competing for
# cores. The pass is append-only and skips every position already recorded, so
# stopping it costs at most the one position in flight; run_learn_v2.sh notices
# the process is gone and restarts it, choosing the width itself.
cd /home/user/fish-researchp12 || exit 1

queue_done() {
  python - <<'PYEOF' 2>/dev/null || echo 0
import json, pathlib
want = set()
for f in ('j24_at_ask_confirm.json', 'j25_stack.json',
          'j26_retake_gate.json', 'j27_precision2.json',
          'j28_claim_threshold.json'):
    p = pathlib.Path('jobs') / f
    if p.exists():
        want |= {j['label'] for j in json.loads(p.read_text())}
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
print(1 if want and want <= done else 0)
PYEOF
}

while [ "$(queue_done)" != "1" ]; do sleep 180; done
echo "$(date +%H:%M:%S) duel queue drained"
# Give any straggler worker a moment to exit before deciding the width.
sleep 60
pid=$(pgrep -f "learn_ask_objective.py rollout --run v2" | head -1)
if [ -n "$pid" ]; then
  echo "$(date +%H:%M:%S) stopping rollout $pid so it restarts wider"
  kill "$pid"
else
  echo "$(date +%H:%M:%S) no rollout running; run_learn_v2.sh will start it wide"
fi
echo "WIDEN DONE"
