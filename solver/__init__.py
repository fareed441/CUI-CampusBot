# Solver Module
# Layer-1 (fast suggestion) + Layer-2 (CP-SAT) for repeater clash resolution

from .layer1_suggest import (
    RepeaterSuggester,
    SuggestionResult,
    find_alternative_offerings,
)
from .layer2_cpsat import (
    RepeaterSolver,
    SolverResult,
    solve_multi_course_repeater,
)

__all__ = [
    "RepeaterSuggester",
    "SuggestionResult",
    "find_alternative_offerings",
    "RepeaterSolver",
    "SolverResult",
    "solve_multi_course_repeater",
]
