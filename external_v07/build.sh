#!/bin/sh
# Build the v0.7 decide shim against dylann4500/fishbot's engine headers.
# The upstream commit this was verified against is in UPSTREAM.txt.
set -e
SRC=${1:-/home/user/dylann4500/fishbot/engine/src}
g++ -std=c++20 -O2 -I "$SRC" -o "$(dirname "$0")/fish_v07_decide" \
    "$(dirname "$0")/shim_decide.cpp" -pthread
