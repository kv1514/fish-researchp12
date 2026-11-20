"""torch is optional, and the code has to say so when it is missing.

The paper's reproduction section hands a reader
`py scripts4/fit_hsvalue.py 200 3`. On a clean clone that died with a bare
`ModuleNotFoundError: No module named 'torch'` raised from inside
`fish4/hsvalue.py`, because torch appears in no requirements file, no
`pyproject.toml` dependency list and no install instruction -- while a comment
in `fish4/learn/fit.py` asserted the opposite. Found by an audit of the paper.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HAVE_TORCH = importlib.util.find_spec("torch") is not None


def test_the_engine_imports_without_torch():
    """Everything that produces a strength number runs on numpy alone. If this
    ever fails, torch has become a real dependency and must be declared as one
    rather than left optional."""
    import fish4.hsvalue                                          # noqa: F401
    import fish4.agent4                                           # noqa: F401
    from fish4.registry4 import make_agent, V06_DEPLOYED
    make_agent(("fishbot4", dict(V06_DEPLOYED[1])))


@pytest.mark.skipif(HAVE_TORCH, reason="torch is installed here")
def test_the_missing_dependency_names_its_own_install():
    """A bare ModuleNotFoundError sends a reader looking for a missing file."""
    import numpy as np
    from fish4.hsvalue import fit_multinomial
    with pytest.raises(ImportError) as e:
        fit_multinomial(np.zeros((4, 2)), np.zeros(4, dtype=int), 2)
    msg = str(e.value)
    assert "requirements-learn.txt" in msg
    assert "OPTIONAL" in msg


def test_the_optional_requirements_file_exists_and_is_not_the_runtime_one():
    learn = (ROOT / "requirements-learn.txt").read_text()
    assert "torch" in learn
    assert "torch" not in (ROOT / "requirements.txt").read_text(), (
        "torch is optional; putting it in requirements.txt makes every clone "
        "and every CI run download it to produce numbers that never use it")
    assert 'learn = ["torch>=2"]' in (ROOT / "pyproject.toml").read_text()


def test_no_comment_still_claims_torch_is_declared():
    """`fish4/learn/fit.py` carried `# torch is a declared dependency`, which
    was false and is exactly the kind of comment that stops anyone checking."""
    for f in (ROOT / "fish4").rglob("*.py"):
        assert "torch is a declared dependency" not in f.read_text(), f
