#!/usr/bin/env bash
# Runs inside the Android emulator job (.github/workflows/android.yml): install
# the debug build, launch it, wait for the first screen to DRAW, then open a
# fish://watch link -- a whole game the bots play, on the live server -- and
# wait for the table. Screenshots land in the working directory.
set -euo pipefail
APK="$1"; PKG="$2"; PY="$3"; FRAC="$4"

adb install -r "$APK"
adb shell am start -W -n "$PKG/.MainActivity"

shoot() { adb exec-out screencap -p > "$1"; }
wait_for() {   # $1 file, $2 colour (blue|felt), $3 threshold, $4 seconds
  local waited=0 f
  while [ "$waited" -lt "$4" ]; do
    sleep 4; waited=$((waited + 4))
    shoot "$1" || continue
    f=$("$PY" "$FRAC" "$1" "$2")
    echo "t=${waited}s $2=$f"
    if "$PY" -c "import sys; sys.exit(0 if float('$f') >= $3 else 1)"; then
      sleep 2; shoot "$1"; echo "$waited"; return 0
    fi
  done
  return 1
}

# The welcome screen's sky-blue "Create account" button (or Quick Play for a
# returning player). The launch screen is dark navy and a blank web view is
# flat, so 1% separates a drawn screen from both.
if ! wait_for home.png blue 0.01 180; then
  echo "::error title=Android app did not draw its first screen::no sky-blue button after 180s"
  exit 1
fi

# The fish:// link, as an invite or a sign-in return would arrive.
adb shell am start -W -a android.intent.action.VIEW -d "fish://watch" "$PKG"
if ! wait_for game.png felt 0.10 180; then
  echo "::error title=fish://watch did not open a game::no table after 180s"
  exit 1
fi
sleep 20; shoot game.png
echo "::notice title=Android app installed, launched, drew its first screen, and opened a game from a fish:// link::$(adb shell getprop ro.build.version.release | tr -d '\r') emulator"
