"""The engine's name, in one place.

The name is user-facing and the identifiers are not, and the two must not be
confused.  ``V06_DEPLOYED`` in :mod:`fish4.registry4` and the ``"fishbot4"``
registry key are named in eight pre-registration documents, in every recorded
journal under ``results/``, and in forty job specs under ``jobs/``.  Those are
dated records: a pre-registration that names its arms before the data is worth
nothing if the arms can be renamed afterwards, so the identifiers are frozen
and this module carries the display name instead.

Renaming the bot is therefore a one-line edit here plus a run of the guard in
``tests4/test_brand.py``, which fails if the site, the handout or the paper
disagrees with these strings.
"""

#: The engine's name.  Set in caps because that is how it is set everywhere it
#: appears; ``NAME.title()`` is not a supported spelling.
NAME = "KRAKEN"

#: v1.0 is this configuration -- ``V06_DEPLOYED``, which is v0.6 plus the
#: forced exhaustive search that shipped on 2026-08-28.  The version moved
#: with the name because the thing being named is the first configuration
#: that beat Dylan's v0.7 by a margin measured over ten thousand games with
#: a bridge whose own contribution had been separately bounded.
VERSION = "v1.0"

FULL_NAME = f"{NAME} {VERSION}"

#: What it was called before 2026-08-28.  Kept so that a reader of an older
#: journal, an older commit or the pre-registration documents can tell that
#: they are looking at the same engine.
FORMER_NAME = "KV's FishBot v0.6"

#: The opponent, for symmetry: the only other named engine in this repository.
OPPONENT_NAME = "Dylan's FishBot v0.7"
