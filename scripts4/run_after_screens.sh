#!/bin/bash
# Launch the pre-registered at-ask run once the five screens have recorded.
# Unconditional on what they say: see jobs/PREREGISTRATION_at_ask.md. Gating a
# confirmatory run on a favourable screen conditions its result on that screen,
# which inflates it invisibly -- the published run would look unselected.
cd /home/user/fish-researchp12 || exit 1
LOG=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/at_ask_confirm.log

count() {
  python - <<'PY' 2>/dev/null || echo -1
import json
rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
print(sum(1 for r in rows
          if 'SCREEN at_ask' in (r.get('label') or '')
          or 'SCREEN gamma 1.0' in (r.get('label') or '')))
PY
}
regen() {
  python - <<'PY'
import json, pathlib
jobs = json.loads(pathlib.Path('jobs/j24_at_ask_confirm.json').read_text())
done = {json.loads(l).get('label') for l in
        open('results/v04_duels.jsonl') if l.strip()}
todo = [j for j in jobs if j['label'] not in done]
pathlib.Path('jobs/j24b_at_ask_resume.json').write_text(json.dumps(todo, indent=1))
print(f"{len(todo)} block(s) still to run")
PY
}

while [ "$(count)" -lt 5 ]; do sleep 120; done
echo "$(date +%H:%M:%S) five screens recorded; starting the pre-registered run"
restarts=0
while true; do
  n=$(python - <<'PY' 2>/dev/null || echo -1
import json
rows = [json.loads(l) for l in open('results/v04_duels.jsonl') if l.strip()]
print(sum(1 for r in rows if 'AT_ASK g1.0' in (r.get('label') or '')))
PY
)
  [ "$n" -ge 6 ] && { echo "all six at_ask blocks recorded"; break; }
  if ! pgrep -f "duel.py jobs/j24b_at_ask_resume" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 12 ] && { echo "giving up at $n/6"; break; }
    echo "$(date +%H:%M:%S) starting at_ask blocks - run #$restarts"
    regen
    setsid nohup python scripts4/duel.py jobs/j24b_at_ask_resume.json 3 \
      >> "$LOG" 2>&1 < /dev/null &
    sleep 25
  fi
  sleep 60
done
echo "AT_ASK CONFIRMATORY RUN DONE"
