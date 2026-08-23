#!/bin/bash
# Harvest -> strong-continuation rollout for the re-opened objective-learning
# line. The rollout pass is append-only and resumable, so it is left running
# without a limit: every position it finishes is a position the fit can use,
# and stopping it early costs nothing but sample.
cd /home/user/fish-researchp12 || exit 1
SCR=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad
while pgrep -f "learn_ask_objective.py harvest --run v2" > /dev/null 2>&1; do
  sleep 20
done
echo "$(date +%H:%M:%S) harvest done: $(wc -l < data/learn/v2/positions.jsonl) positions"
restarts=0
while true; do
  if ! pgrep -f "learn_ask_objective.py rollout --run v2" > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 40 ] && { echo "giving up after $restarts restarts"; break; }
    echo "$(date +%H:%M:%S) starting v04 rollout pass - run #$restarts"
    setsid nohup python scripts4/learn_ask_objective.py rollout --run v2 \
      --continuation v04 --max-actions 400 --workers 1 \
      >> "$SCR/rollout_v2.log" 2>&1 < /dev/null &
    sleep 30
  fi
  sleep 120
done
