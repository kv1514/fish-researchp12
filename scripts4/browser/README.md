# Browser checks for the public table

These are not in `tests4/`. They need a running server and a real browser, so
they do not belong in a suite that has to pass anywhere. They exist because the
two worst UI bugs in this project were both invisible to everything else:

- **"Declare a set" was dead.** A global rename left a local shadowing the card
  renderer. Every Python test passed; no test had ever clicked the button.
- **The declare form defaulted every unheld card to *you*.** Not a crash: the
  team list is sorted, so seat 0 came first in every dropdown, and declaring
  without changing all six voided the set — which is exactly the "why is there a
  void" the site's first user reported. A test that only checked the dialog
  *opens* would have passed.

So the rule is: a change to `public/` gets driven in a browser before it ships,
and the check asserts what the control *does*, not that it exists.

## Running them

```bash
FISH_SECRET=devsecret_at_least_16_bytes_long py scripts4/devserve.py 8455 &
py scripts4/browser/play_full_game.py      # a whole game, scores, voids, log
py scripts4/browser/check_declare.py       # what the dialog pre-selects
py scripts4/browser/check_score_panel.py   # the per-term score breakdown
py scripts4/browser/check_signed_terms.py  # the negative-term layout branch
```

They print assertions rather than raising, because the useful output is the
*values* — "1/6 defaulted to you" is the finding; "passed" would not be.

`check_signed_terms.py` calls `renderWhy` directly with a fabricated move. That
is deliberate: negative terms do not occur at an opening position, so the branch
that draws costs to the left of the centre line is otherwise unreachable from a
real game, and an unreachable branch is one that breaks silently.

Chromium is at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome` in this
environment. Against a deployed URL rather than localhost, the sandbox's HTTPS
proxy has to be passed to `chromium.launch(proxy=...)`, and even then the
connection may be reset — the deployed checks in this session were done with
`curl` against the served assets and the JSON API instead.

## Last run

A full game played out 5–4 with **zero voided sets** and no console errors. The
declare dialog opened on the posterior MAP: five of six cards pre-selected to
the teammate the engine thought most likely at 20% each, the sixth to `you ·
100%` because that is the card actually held, and every option carrying its
probability.
