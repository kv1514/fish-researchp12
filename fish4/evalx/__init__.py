"""v0.4 evaluation infrastructure.

Four pieces, each written against a specific way the v0.3 pipeline could
mislead us:

- ``harness``   paired-deal play with optional antithetic seat rotation,
                loud timeout accounting, and a resumable result log.
- ``sequential`` always-valid stopping rules, so an experiment may stop when
                the answer is clear without inflating type-I error.
- ``ablation``  decision-for-decision identity checking, so an "ablation"
                cannot silently change two things at once.
- ``registry``  append-only, atomically-written experiment records with a
                retraction path instead of deletion.

Nothing here imports from ``fish4.counting`` / ``fish4.posterior``; the
evaluation layer is deliberately independent of the inference layer so it
can be used to judge it.
"""

from .harness import (AgentSpec, HarnessConfig, PairRecord, PairedResult,
                      VarianceReport, run_paired)
from .sequential import (BettingTest, EmpiricalBernsteinCS, SequentialDecision,
                         SequentialTest, simulate_power, simulate_type_i)
from .ablation import (AblationDivergence, IdentityReport,
                       assert_parameter_has_effect,
                       assert_reduces_to_baseline, check_parameter_has_effect,
                       check_reduces_to_baseline)
from .registry import (SCHEMA_VERSION, ExperimentRecord, load_all, record,
                       retract, summary)

__all__ = [
    "AgentSpec", "HarnessConfig", "PairRecord", "PairedResult",
    "VarianceReport", "run_paired",
    "BettingTest", "EmpiricalBernsteinCS", "SequentialDecision",
    "SequentialTest", "simulate_power", "simulate_type_i",
    "AblationDivergence", "IdentityReport", "assert_parameter_has_effect",
    "assert_reduces_to_baseline", "check_parameter_has_effect",
    "check_reduces_to_baseline",
    "SCHEMA_VERSION", "ExperimentRecord", "load_all", "record", "retract",
    "summary",
]
