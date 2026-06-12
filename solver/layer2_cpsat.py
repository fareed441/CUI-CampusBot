"""
Layer-2: CP-SAT Solver for Multi-Course Repeater Resolution

When Layer-1 cannot find a single-course solution or student has multiple
repeat courses, this solver finds an optimal combination of offerings.

Uses Google OR-Tools CP-SAT solver with:
- Hard constraints: no clashes among chosen offerings + existing schedule
- Soft objectives: minimize gaps, late slots; prefer same department
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from enum import Enum
import time

try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    cp_model = None

import sys
sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

from timetable_core.models import (
    Offering, Student, Course, Day, TIMESLOTS, DAYS
)
from timetable_core.bitmask import (
    offering_to_bitmask,
    student_schedule_mask,
    check_clash,
    cell_index,
    total_gaps,
    count_late_slots,
)
from timetable_core.fuzzy_match import CourseMatcher


class SolverStatus(Enum):
    """Status of solver result"""
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"
    NOT_AVAILABLE = "ortools_not_available"


@dataclass
class SolverResult:
    """Result from Layer-2 CP-SAT solver"""
    status: SolverStatus
    
    # Chosen offerings (one per course)
    chosen_offerings: Dict[str, Offering] = field(default_factory=dict)
    
    # Explanation of the solution
    explanation: str = ""
    
    # Statistics
    total_gaps: int = 0
    total_late_slots: int = 0
    objective_value: float = 0.0
    
    # Processing time
    solving_time_ms: float = 0.0
    
    # Conflicts if infeasible
    conflicts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "chosen_offerings": {
                code: off.to_dict() for code, off in self.chosen_offerings.items()
            },
            "explanation": self.explanation,
            "total_gaps": self.total_gaps,
            "total_late_slots": self.total_late_slots,
            "objective_value": self.objective_value,
            "solving_time_ms": self.solving_time_ms,
            "conflicts": self.conflicts,
        }


class RepeaterSolver:
    """
    Layer-2 CP-SAT solver for multi-course repeater resolution.
    
    Given:
    - Student's current enrolled offerings
    - List of courses to repeat (with candidate offerings for each)
    
    Find:
    - One offering per course such that no clashes occur
    - Optimize for minimal gaps and late slots
    """
    
    # Weights for objective function
    GAP_WEIGHT = 2
    LATE_SLOT_WEIGHT = 1
    DEPT_MISMATCH_WEIGHT = 3
    
    def __init__(
        self,
        all_offerings: List[Offering],
        time_limit_seconds: float = 2.0
    ):
        """
        Initialize solver with all available offerings.
        
        Args:
            all_offerings: List of all section offerings
            time_limit_seconds: Maximum solving time (default 2s)
        """
        self.all_offerings = all_offerings
        self.offerings_by_id = {o.offering_id: o for o in all_offerings}
        self.time_limit = time_limit_seconds
        
        # Index offerings by course
        self.offerings_by_course: Dict[str, List[Offering]] = {}
        for offering in all_offerings:
            code = offering.course.course_code
            if code not in self.offerings_by_course:
                self.offerings_by_course[code] = []
            self.offerings_by_course[code].append(offering)
        
        # Precompute bitmasks
        for offering in all_offerings:
            offering_to_bitmask(offering)
    
    def solve(
        self,
        student: Student,
        course_codes: List[str],
        exclude_offerings: Optional[Set[str]] = None,
        prefer_department: Optional[str] = None,
    ) -> SolverResult:
        """
        Solve multi-course repeater problem using CP-SAT.
        
        Args:
            student: The repeater student
            course_codes: List of course codes to find offerings for
            exclude_offerings: Offering IDs to exclude from consideration
            prefer_department: Preferred department for soft objective
        
        Returns:
            SolverResult with chosen offerings or failure reason
        """
        start_time = time.perf_counter()
        
        if not ORTOOLS_AVAILABLE:
            return SolverResult(
                status=SolverStatus.NOT_AVAILABLE,
                explanation="OR-Tools not installed. Run: pip install ortools"
            )
        
        exclude_offerings = exclude_offerings or set()
        
        # Step 1: Build student's fixed schedule mask
        fixed_mask = 0
        for oid in student.enrolled_offering_ids:
            if oid in self.offerings_by_id and oid not in exclude_offerings:
                fixed_mask |= offering_to_bitmask(self.offerings_by_id[oid])
        
        # Step 2: Build candidate offerings for each course
        candidates: Dict[str, List[Tuple[Offering, int]]] = {}  # code -> [(offering, mask)]
        
        for code in course_codes:
            if code not in self.offerings_by_course:
                return SolverResult(
                    status=SolverStatus.INFEASIBLE,
                    explanation=f"No offerings found for course {code}",
                    conflicts=[f"Course {code} has no available offerings"]
                )
            
            candidates[code] = []
            for offering in self.offerings_by_course[code]:
                if offering.offering_id not in exclude_offerings:
                    mask = offering_to_bitmask(offering)
                    candidates[code].append((offering, mask))
            
            if not candidates[code]:
                return SolverResult(
                    status=SolverStatus.INFEASIBLE,
                    explanation=f"All offerings for {code} are excluded",
                    conflicts=[f"No available offerings for {code}"]
                )
        
        # Step 3: Build and solve CP-SAT model
        model = cp_model.CpModel()
        
        # Variables: x[code][i] = 1 if offering i of course code is selected
        x: Dict[str, List[cp_model.IntVar]] = {}
        for code in course_codes:
            x[code] = []
            for i in range(len(candidates[code])):
                x[code].append(model.NewBoolVar(f"x_{code}_{i}"))
        
        # Constraint 1: Select exactly one offering per course
        for code in course_codes:
            model.Add(sum(x[code]) == 1)
        
        # Constraint 2: No clash with fixed schedule
        for code in course_codes:
            for i, (offering, mask) in enumerate(candidates[code]):
                if check_clash(fixed_mask, mask):
                    # This offering clashes with fixed schedule, disable it
                    model.Add(x[code][i] == 0)
        
        # Constraint 3: No clash between selected offerings
        # For each pair of courses, check all pairs of offerings
        course_list = list(course_codes)
        for c1_idx in range(len(course_list)):
            for c2_idx in range(c1_idx + 1, len(course_list)):
                code1, code2 = course_list[c1_idx], course_list[c2_idx]
                
                for i, (off1, mask1) in enumerate(candidates[code1]):
                    for j, (off2, mask2) in enumerate(candidates[code2]):
                        if check_clash(mask1, mask2):
                            # These two offerings clash, can't both be selected
                            model.Add(x[code1][i] + x[code2][j] <= 1)
        
        # Objective: minimize gaps + late slots + department mismatches
        # We'll use auxiliary variables to track the combined schedule
        
        # Calculate objective coefficients for each offering
        objective_terms = []
        
        for code in course_codes:
            for i, (offering, mask) in enumerate(candidates[code]):
                # Compute this offering's contribution to objectives
                # Note: gaps calculation with combined mask is complex, 
                # so we use individual offering contributions as approximation
                gaps = total_gaps(mask)
                late = count_late_slots(mask)
                dept_match = 0 if (prefer_department and 
                    offering.teacher.department == prefer_department) else 1
                
                cost = (gaps * self.GAP_WEIGHT + 
                        late * self.LATE_SLOT_WEIGHT + 
                        dept_match * self.DEPT_MISMATCH_WEIGHT)
                
                objective_terms.append(cost * x[code][i])
        
        model.Minimize(sum(objective_terms))
        
        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit
        
        status = solver.Solve(model)
        solving_time = (time.perf_counter() - start_time) * 1000
        
        # Process result
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            chosen = {}
            total_mask = fixed_mask
            
            for code in course_codes:
                for i, (offering, mask) in enumerate(candidates[code]):
                    if solver.Value(x[code][i]) == 1:
                        chosen[code] = offering
                        total_mask |= mask
                        break
            
            result_status = SolverStatus.OPTIMAL if status == cp_model.OPTIMAL else SolverStatus.FEASIBLE
            
            # Build explanation
            explanation_parts = []
            for code, offering in chosen.items():
                explanation_parts.append(
                    f"- {offering.course.course_name}: "
                    f"{offering.batch_section} ({offering.teacher.name})"
                )
            
            return SolverResult(
                status=result_status,
                chosen_offerings=chosen,
                explanation="Selected offerings:\n" + "\n".join(explanation_parts),
                total_gaps=total_gaps(total_mask),
                total_late_slots=count_late_slots(total_mask),
                objective_value=solver.ObjectiveValue(),
                solving_time_ms=solving_time,
            )
        
        elif status == cp_model.INFEASIBLE:
            # Try to identify conflicts
            conflicts = self._analyze_infeasibility(
                student, course_codes, candidates, fixed_mask
            )
            return SolverResult(
                status=SolverStatus.INFEASIBLE,
                explanation="No feasible combination of offerings exists",
                solving_time_ms=solving_time,
                conflicts=conflicts,
            )
        
        else:  # UNKNOWN or other (likely timeout)
            return SolverResult(
                status=SolverStatus.TIMEOUT,
                explanation=f"Solver timed out after {self.time_limit}s",
                solving_time_ms=solving_time,
            )
    
    def _analyze_infeasibility(
        self,
        student: Student,
        course_codes: List[str],
        candidates: Dict[str, List[Tuple[Offering, int]]],
        fixed_mask: int
    ) -> List[str]:
        """Analyze why no solution exists."""
        conflicts = []
        
        # Check if any course has all offerings clashing with fixed schedule
        for code in course_codes:
            all_clash = True
            for offering, mask in candidates[code]:
                if not check_clash(fixed_mask, mask):
                    all_clash = False
                    break
            if all_clash:
                conflicts.append(
                    f"All offerings of {code} clash with existing schedule"
                )
        
        # Check if any pair of courses has mutually exclusive offerings
        course_list = list(course_codes)
        for c1_idx in range(len(course_list)):
            for c2_idx in range(c1_idx + 1, len(course_list)):
                code1, code2 = course_list[c1_idx], course_list[c2_idx]
                
                # Get offerings that don't clash with fixed schedule
                valid1 = [(o, m) for o, m in candidates[code1] 
                         if not check_clash(fixed_mask, m)]
                valid2 = [(o, m) for o, m in candidates[code2] 
                         if not check_clash(fixed_mask, m)]
                
                if not valid1 or not valid2:
                    continue
                
                # Check if any pair is compatible
                any_compatible = False
                for off1, mask1 in valid1:
                    for off2, mask2 in valid2:
                        if not check_clash(mask1, mask2):
                            any_compatible = True
                            break
                    if any_compatible:
                        break
                
                if not any_compatible:
                    conflicts.append(
                        f"All valid {code1} offerings clash with all valid {code2} offerings"
                    )
        
        return conflicts


def solve_multi_course_repeater(
    student: Student,
    course_queries: List[str],
    all_offerings: List[Offering],
    course_matcher: Optional[CourseMatcher] = None,
    time_limit: float = 2.0,
    exclude_offerings: Optional[Set[str]] = None,
) -> SolverResult:
    """
    High-level function to solve multi-course repeater problem.
    
    Args:
        student: Repeater student
        course_queries: List of course queries (can be fuzzy)
        all_offerings: All available offerings
        course_matcher: Optional fuzzy matcher
        time_limit: Solver time limit in seconds
        exclude_offerings: Offering IDs to exclude
    
    Returns:
        SolverResult with chosen offerings
    """
    # Initialize matcher if needed
    if course_matcher is None:
        course_matcher = CourseMatcher()
        course_matcher.register_courses_from_offerings(all_offerings)
    
    # Resolve course queries to codes
    course_codes = []
    for query in course_queries:
        matches = course_matcher.search(query)
        if not matches:
            return SolverResult(
                status=SolverStatus.INFEASIBLE,
                explanation=f"Could not find course matching '{query}'",
                conflicts=[f"Unknown course: {query}"]
            )
        course_codes.append(matches[0].course_code)
    
    # Solve
    solver = RepeaterSolver(all_offerings, time_limit)
    return solver.solve(student, course_codes, exclude_offerings)
