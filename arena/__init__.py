"""A standalone duelling arena for KRAKEN and the policies it ships beside.

See ``arena/README.md``. The entry point is ``python -m arena``.
"""

from arena.roster import ROSTER, resolve, CHEATERS          # noqa: F401
from arena.tournament import run_tournament                 # noqa: F401
from arena.report import render_matrix                      # noqa: F401
