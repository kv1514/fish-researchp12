#!/bin/bash
# Restart the v04 rollout pass wider once the duel queue stops competing for
# cores. The pass is append-only and skips every position already recorded, so
# stopping it costs at most the one position in flight; run_learn_v2.sh notices
# the process is gone and restarts it, choosing the width itself.
cd /home/user/fish-researchp12 || exit 1

queue_done() {
  # Delegates to scripts4/queue_state.py, which keeps the list of job files
  # being waited on and REFUSES to pass when a job file with pending blocks is
  # in neither its wait list nor its excluded list. The list used to live here
  # as five hard-coded filenames and had already gone stale once: j30 was
  # queued after it was written, so widening would have fired while 2000
  # pre-registered pairs were still to play.
  n=$(python scripts4/queue_state.py --wait-labels 2>/dev/null | wc -l)
  if ! python scripts4/queue_state.py > /dev/null 2>&1; then
    echo 0            # undeclared job file: refuse to widen rather than guess
    return
  fi
  [ "$n" -eq 0 ] && echo 1 || echo 0
}

while [ "$(queue_done)" != "1" ]; do sleep 180; done
echo "$(date +%H:%M:%S) duel queue drained"
# Give any straggler worker a moment to exit before deciding the width.
sleep 60
# Same reason as in run_learn_v2.sh: pgrep -f would happily hand back the PID
# of a shell that merely mentions the job, and this line KILLS what it finds.
pid=$(python scripts4/proc_alive.py learn_ask_objective.py rollout --run v2 | head -1)
if [ -n "$pid" ]; then
  echo "$(date +%H:%M:%S) stopping rollout $pid so it restarts wider"
  kill "$pid"
else
  echo "$(date +%H:%M:%S) no rollout running; run_learn_v2.sh will start it wide"
fi
echo "WIDEN DONE"
