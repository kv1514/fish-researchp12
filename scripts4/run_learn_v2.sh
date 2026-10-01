#!/bin/bash
# Harvest -> strong-continuation rollout for the re-opened objective-learning
# line. The rollout pass is append-only and resumable, so it is left running
# without a limit: every position it finishes is a position the fit can use,
# and stopping it early costs nothing but sample.
cd /home/user/fish-researchp12 || exit 1
SCR=/tmp/claude-0/-home-user-fish-researchp12/993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad
# proc_alive.py, not pgrep -f, for the reason spelled out at the restart check
# below: pgrep matches any process whose command line merely mentions the job.
while python scripts4/proc_alive.py learn_ask_objective.py harvest --run v2 \
      > /dev/null 2>&1; do
  sleep 20
done
echo "$(date +%H:%M:%S) harvest done: $(wc -l < data/learn/v2/positions.jsonl) positions"
# Width is decided at each restart rather than fixed once. While the duel queue
# occupies three of this machine's four cores the rollout gets one; when the
# queue drains it should get three, and a pass that is append-only and resumable
# can simply be restarted wider. scripts4/widen_rollout.sh does the restarting.
width() {
  # Any duel at all, not a filename prefix. This used to match
  # "duel.py jobs/j2", which covered j24-j28 and silently stopped covering
  # anything the moment the queue reached j30 -- the same staleness that
  # scripts4/queue_state.py exists to prevent one level up. A prefix that
  # encodes today's job numbering is a bug with a delay fuse.
  if pgrep -f "scripts4/duel.py" > /dev/null 2>&1; then echo 1; else echo 3; fi
}
restarts=0
while true; do
  # NOT pgrep -f. That matches the full command line of EVERY process, so a
  # shell one-liner written to WATCH this pass -- one containing the very
  # string being searched for -- made this supervisor believe the pass was
  # alive and stop restarting it. The pass stayed dead for as long as the
  # watcher ran. scripts4/proc_alive.py asks /proc and counts only a python
  # interpreter whose own argv carries these tokens.
  if ! python scripts4/proc_alive.py learn_ask_objective.py rollout --run v2 \
       > /dev/null 2>&1; then
    restarts=$((restarts + 1))
    [ "$restarts" -gt 40 ] && { echo "giving up after $restarts restarts"; break; }
    w=$(width)
    echo "$(date +%H:%M:%S) starting v04 rollout pass - run #$restarts, $w worker(s)"
    setsid nohup python scripts4/learn_ask_objective.py rollout --run v2 \
      --continuation v04 --max-actions 400 --workers "$w" \
      >> "$SCR/rollout_v2.log" 2>&1 < /dev/null &
    sleep 30
  fi
  sleep 120
done
