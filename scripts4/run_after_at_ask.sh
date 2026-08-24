#!/bin/bash
# Launch the pre-registered stacking run once the at-ask blocks have recorded.
# Unconditional on what any of them say: jobs/PREREGISTRATION_stack.md fixes the
# design, and a run that starts only when the queue ahead of it looks good is a
# selected run wearing an unselected label.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/stack.log

done_at_ask() {
  python - <<'PY' 2>/dev/null || echo -1
import json
rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
print(sum(1 for r in rows if 'AT_ASK g1.0' in (r.get('label') or '')))
PY
}
count() {
  python - <<'PY' 2>/dev/null || echo -1
import json
rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
print(sum(1 for r in rows if 'STACK lookahead' in (r.get('label') or '')))
PY
}
regen() {
  python - <<'PY'
import json, pathlib
jobs = json.loads(pathlib.Path('jobs/j25_stack.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j25b_stack_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PY
}

while [ "$(done_at_ask)" -lt 6 ]; do sleep 120; done
echo "$(date +%H:%M:%S) at-ask run finished; starting the stacking run"
restarts=0
while true; do
  n=$(count)
  [ "$n" -ge 6 ] && { echo "all six stack blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j25b_stack_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 12 ] && { echo "giving up at $n/6"; break; }
    echo "$(date +%H:%M:%S) starting stack blocks - run #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j25b_stack_resume.json 3 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 25
  fi
  sleep 60
done
echo "STACKING RUN DONE"
