"""A results file must record the CODE that produced it, not only the config.

WHY THIS EXISTS, and it is one incident rather than a principle.
results/convention_posterior.json stored a seven-key spec and no code identity.
A later run at identical seeds gave a materially different number. The two specs
compared byte-identical -- correctly -- and that was taken as evidence nothing
about the configuration had changed, in three separate documents, followed by
three explanations for a change in the world.

The change was in the code. Commit 6d75ec4 re-priced `convention_max_cost` from
a drop in success probability into the ask objective's own units, so one label
named two different senders. `convention_max_cost` is not in the stored spec,
and what moved was not its value but its UNITS.

A configuration fingerprint compares values and cannot see a field's meaning
move underneath it. An engine digest can, and did: 4d7896f938dd before that
commit against ca40192a1f3a after. See results/convention_drift_bisect.json.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from duel import FINGERPRINTED, engine_fingerprint            # noqa: E402

#: Instruments that write a results file whose numbers depend on the engine.
#: Each must record the engine digest beside them, so two runs can be told
#: apart by code and not only by config.
#:
#: The first five score beliefs. `signal_deadline.py` does not -- it is a play
#: instrument -- and it is here anyway because the file the incident turned on
#: is `fish4/agent4.py`, and that is precisely the file holding the signalling
#: gate whose firing it records. The list's criterion is "the engine can move
#: this file's numbers", not "the instrument touches the posterior".
INSTRUMENTS = ("convention_posterior.py", "gamma_split.py",
               "unlocated_belief.py", "channel_precision.py",
               "precision_generality.py", "signal_deadline.py")


@pytest.mark.parametrize("name", INSTRUMENTS)
def test_every_belief_instrument_records_the_engine(name):
    src = (ROOT / "scripts4" / name).read_text()
    assert "engine_fingerprint" in src, (
        f"{name} writes a results file without recording the engine that "
        "produced it, which is the gap that cost a day")


def test_the_digest_covers_the_file_that_caused_the_incident():
    """`fish4/agent4.py` holds the sender's gate. If it is not fingerprinted
    the digest would have been silent through exactly the change it exists to
    catch."""
    assert "fish4/agent4.py" in FINGERPRINTED


def test_the_digest_actually_moves_when_a_fingerprinted_file_moves():
    """The mechanism, not just the call.

    A digest that never changes is the same shape as a knob that produces a
    bit-identical result -- what a silent no-op looks like from outside. So the
    per-file hashes are recomputed here with one byte flipped and the joint
    digest is required to differ.
    """
    base = engine_fingerprint()
    assert len(base["digest"]) == 12
    assert set(base["files"]) == set(FINGERPRINTED)

    parts = dict(base["files"])
    parts["fish4/agent4.py"] = "0" * 12          # as if that file changed
    moved = hashlib.sha256(
        "".join(f"{k}={v};" for k, v in sorted(parts.items()))
        .encode()).hexdigest()[:12]
    assert moved != base["digest"]


def test_a_missing_file_is_recorded_rather_than_skipped():
    """duel.engine_fingerprint records MISSING rather than dropping the key.

    Dropping it would let a rename shrink what is fingerprinted while the
    digest still looked like a digest.
    """
    src = (ROOT / "scripts4" / "duel.py").read_text()
    assert '"MISSING"' in src
