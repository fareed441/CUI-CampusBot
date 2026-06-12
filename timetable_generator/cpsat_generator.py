"""
CP-SAT Timetable Generator

Uses Google OR-Tools CP-SAT solver to generate clash-free timetables.

Hard Constraints:
1. No teacher overlap in same day+slot
2. No batch/section overlap in same day+slot
3. No room overlap in same day+slot (if rooms assigned)
4. Lab sessions must be consecutive slots (not crossing break)
5. Each session scheduled exactly once

Soft Constraints (Optimized):
- Minimize gaps per batch
- Minimize late slots (slot 6)
- Spread classes across days
"""
import time
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional, Any
from enum import Enum
from collections import defaultdict
import sys

sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False
    cp_model = None

from timetable_generator.csv_parser import ClassSession, ParsedData
from timetable_core.models import (
    Day, DAYS, Meeting, Offering, Course, Teacher, Room,
    OfferingType, RoomType, TIMESLOTS
)


class SolverStatus(Enum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"
    NOT_AVAILABLE = "ortools_not_available"


@dataclass
class ScheduledSession:
    """A session with its assigned day and slot(s)"""
    session: ClassSession
    day: Day
    day_idx: int
    slot_start: int  # 1-6
    slot_end: int    # slot_start or slot_start+1 for labs
    room_code: str = ""
    
    @property
    def slot_span(self) -> int:
        return self.slot_end - self.slot_start + 1
    
    @property
    def is_lab(self) -> bool:
        return self.slot_span == 2
    
    def to_dict(self) -> Dict:
        return {
            "batch_section": self.session.batch_section,
            "course_name": self.session.course_name,
            "teacher": self.session.teacher_name,
            "day": self.day.name,
            "day_display": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][self.day_idx],
            "slot_start": self.slot_start,
            "slot_end": self.slot_end,
            "slot_span": self.slot_span,
            "room": self.room_code,
            "type": "LAB" if self.is_lab else "LEC",
        }


@dataclass
class GeneratorResult:
    """Result from timetable generation"""
    status: SolverStatus
    scheduled_sessions: List[ScheduledSession] = field(default_factory=list)
    schedule_by_batch: Dict[str, List[ScheduledSession]] = field(default_factory=dict)
    
    # Statistics
    total_sessions: int = 0
    total_scheduled: int = 0
    total_gaps: int = 0
    total_late_slots: int = 0
    objective_value: float = 0.0
    solving_time_seconds: float = 0.0
    
    # Diagnostics
    conflicts: List[str] = field(default_factory=list)
    explanation: str = ""


class TimetableGenerator:
    """
    Generates clash-free timetables using CP-SAT solver.
    """
    
    # Days and slots
    NUM_DAYS = 5  # Monday to Friday
    NUM_SLOTS = 6  # 6 slots per day
    
    # Valid start slots for 2-slot labs (cannot cross break between slot 3 and 4)
    LAB_START_SLOTS = [1, 2, 4, 5]  # Slots 1,2 (morning) or 4,5 (afternoon)
    
    # Objective weights
    GAP_WEIGHT = 3
    LATE_SLOT_WEIGHT = 2
    SPREAD_WEIGHT = 1
    
    def __init__(self, time_limit_seconds: float = 120.0):
        """
        Initialize the generator.
        
        Args:
            time_limit_seconds: Maximum solving time (default 120s)
        """
        if not ORTOOLS_AVAILABLE:
            raise ImportError("OR-Tools not installed. Run: pip install ortools")
        
        self.time_limit = time_limit_seconds
        self.model: Optional[cp_model.CpModel] = None
        self.solver: Optional[cp_model.CpSolver] = None
        
        # Decision variables
        self.x: Dict[str, Dict[int, Dict[int, cp_model.IntVar]]] = {}  # session_id -> day -> slot -> var
        
    def generate(
        self, 
        parsed_data: ParsedData,
        rooms: Optional[List[str]] = None,
    ) -> GeneratorResult:
        """
        Generate a clash-free timetable for all sessions.
        
        Args:
            parsed_data: Parsed data from CSV
            rooms: Optional list of room codes (if None, rooms not assigned)
            
        Returns:
            GeneratorResult with scheduled sessions
        """
        start_time = time.perf_counter()
        
        sessions = parsed_data.sessions
        if not sessions:
            return GeneratorResult(
                status=SolverStatus.INFEASIBLE,
                explanation="No sessions to schedule"
            )
        
        print(f"\n{'='*60}")
        print("TIMETABLE GENERATION STARTED")
        print(f"{'='*60}")
        print(f"Sessions to schedule: {len(sessions)}")
        print(f"Time limit: {self.time_limit}s")
        
        # Create model
        self.model = cp_model.CpModel()
        
        # Index sessions
        sessions_by_teacher = defaultdict(list)
        sessions_by_batch = defaultdict(list)
        
        for session in sessions:
            sessions_by_teacher[session.teacher_name].append(session)
            sessions_by_batch[session.batch_section].append(session)
        
        print(f"Teachers: {len(sessions_by_teacher)}")
        print(f"Batches: {len(sessions_by_batch)}")
        
        # Create decision variables
        print("\nCreating decision variables...")
        self._create_variables(sessions)
        
        # Add constraints
        print("Adding constraints...")
        self._add_assignment_constraints(sessions)
        self._add_teacher_clash_constraints(sessions_by_teacher)
        self._add_batch_clash_constraints(sessions_by_batch)
        self._add_lab_constraints(sessions)
        
        # Add objective
        print("Setting up objective function...")
        self._add_objective(sessions, sessions_by_batch)
        
        # Solve
        print(f"\nSolving (time limit: {self.time_limit}s)...")
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = self.time_limit
        self.solver.parameters.num_search_workers = 8  # Parallel search
        
        # Add progress callback
        class ProgressCallback(cp_model.CpSolverSolutionCallback):
            def __init__(self):
                cp_model.CpSolverSolutionCallback.__init__(self)
                self.solutions = 0
                
            def on_solution_callback(self):
                self.solutions += 1
                if self.solutions % 100 == 0:
                    print(f"  Found {self.solutions} solutions, objective: {self.ObjectiveValue()}")
        
        callback = ProgressCallback()
        status = self.solver.Solve(self.model, callback)
        
        solving_time = time.perf_counter() - start_time
        
        # Process result
        return self._process_result(
            status, sessions, sessions_by_batch, solving_time
        )
    
    def _create_variables(self, sessions: List[ClassSession]):
        """Create decision variables for each session."""
        self.x = {}
        
        for session in sessions:
            self.x[session.session_id] = {}
            
            # Determine valid slot starts
            if session.is_lab or session.slot_duration == 2:
                valid_starts = self.LAB_START_SLOTS
            else:
                valid_starts = list(range(1, self.NUM_SLOTS + 1))
            
            for day in range(self.NUM_DAYS):
                self.x[session.session_id][day] = {}
                for slot in valid_starts:
                    # Check slot validity for labs (slot + 1 must exist and be valid)
                    if session.slot_duration == 2:
                        if slot > 5:  # Can't fit 2 slots starting at slot 6
                            continue
                    
                    var_name = f"x_{session.session_id}_{day}_{slot}"
                    self.x[session.session_id][day][slot] = self.model.NewBoolVar(var_name)
    
    def _add_assignment_constraints(self, sessions: List[ClassSession]):
        """Each session must be assigned exactly one (day, slot) pair."""
        for session in sessions:
            all_vars = []
            for day in range(self.NUM_DAYS):
                for slot, var in self.x[session.session_id][day].items():
                    all_vars.append(var)
            
            # Exactly one assignment
            self.model.Add(sum(all_vars) == 1)
    
    def _add_teacher_clash_constraints(
        self, 
        sessions_by_teacher: Dict[str, List[ClassSession]]
    ):
        """No teacher can be in two places at the same time."""
        for teacher, teacher_sessions in sessions_by_teacher.items():
            if len(teacher_sessions) < 2:
                continue
            
            # For each (day, slot) pair
            for day in range(self.NUM_DAYS):
                for slot in range(1, self.NUM_SLOTS + 1):
                    # Collect all sessions this teacher could have at (day, slot)
                    session_vars = []
                    
                    for session in teacher_sessions:
                        # Check if session could occupy this slot
                        duration = session.slot_duration
                        
                        # For a session starting at slot s with duration d,
                        # it occupies slots s, s+1, ..., s+d-1
                        # So it affects slot k if s <= k < s+d, i.e., k-d+1 < s <= k
                        
                        for start_slot in self.x[session.session_id].get(day, {}).keys():
                            end_slot = start_slot + duration - 1
                            if start_slot <= slot <= end_slot:
                                session_vars.append(
                                    self.x[session.session_id][day][start_slot]
                                )
                    
                    # At most one can be active
                    if len(session_vars) >= 2:
                        self.model.Add(sum(session_vars) <= 1)
    
    def _add_batch_clash_constraints(
        self,
        sessions_by_batch: Dict[str, List[ClassSession]]
    ):
        """No batch can have two classes at the same time."""
        for batch, batch_sessions in sessions_by_batch.items():
            if len(batch_sessions) < 2:
                continue
            
            # For each (day, slot) pair
            for day in range(self.NUM_DAYS):
                for slot in range(1, self.NUM_SLOTS + 1):
                    session_vars = []
                    
                    for session in batch_sessions:
                        duration = session.slot_duration
                        
                        for start_slot in self.x[session.session_id].get(day, {}).keys():
                            end_slot = start_slot + duration - 1
                            if start_slot <= slot <= end_slot:
                                session_vars.append(
                                    self.x[session.session_id][day][start_slot]
                                )
                    
                    if len(session_vars) >= 2:
                        self.model.Add(sum(session_vars) <= 1)
    
    def _add_lab_constraints(self, sessions: List[ClassSession]):
        """
        Lab constraints are already handled by:
        1. Only creating variables for valid lab start slots
        2. The clash constraints accounting for slot duration
        
        This method adds any additional lab-specific constraints if needed.
        """
        # Labs already constrained to valid slots in _create_variables
        pass
    
    def _add_objective(
        self,
        sessions: List[ClassSession],
        sessions_by_batch: Dict[str, List[ClassSession]]
    ):
        """
        Objective: Minimize gaps + late slots.
        
        Gap = For each batch, count slots between first and last class
              minus the number of class slots.
        Late = Count of classes in slot 6.
        """
        objective_terms = []
        
        # Late slot penalty
        for session in sessions:
            for day in range(self.NUM_DAYS):
                # Slot 6 is late
                if 6 in self.x[session.session_id].get(day, {}):
                    objective_terms.append(
                        self.LATE_SLOT_WEIGHT * self.x[session.session_id][day][6]
                    )
                # Slot 5 is somewhat late
                if 5 in self.x[session.session_id].get(day, {}):
                    objective_terms.append(
                        1 * self.x[session.session_id][day][5]
                    )
        
        # Try to spread classes across days for each batch
        # Penalize having too many classes on same day
        for batch, batch_sessions in sessions_by_batch.items():
            if len(batch_sessions) <= 3:
                continue
            
            for day in range(self.NUM_DAYS):
                # Count sessions on this day
                day_vars = []
                for session in batch_sessions:
                    for slot in self.x[session.session_id].get(day, {}).keys():
                        day_vars.append(self.x[session.session_id][day][slot])
                
                if len(day_vars) > 3:
                    # Create auxiliary variable for "overloaded day"
                    overload = self.model.NewBoolVar(f"overload_{batch}_{day}")
                    # overload = 1 if count > 3
                    self.model.Add(sum(day_vars) > 3).OnlyEnforceIf(overload)
                    self.model.Add(sum(day_vars) <= 3).OnlyEnforceIf(overload.Not())
                    objective_terms.append(self.SPREAD_WEIGHT * 2 * overload)
        
        # Minimize gaps (simplified - prefer consecutive slots)
        # Full gap calculation is complex, use approximation
        for batch, batch_sessions in sessions_by_batch.items():
            for day in range(self.NUM_DAYS):
                # Get all slot variables for this batch on this day
                slot_to_vars = defaultdict(list)
                
                for session in batch_sessions:
                    duration = session.slot_duration
                    for start_slot in self.x[session.session_id].get(day, {}).keys():
                        for s in range(start_slot, start_slot + duration):
                            slot_to_vars[s].append(
                                self.x[session.session_id][day][start_slot]
                            )
                
                # Create variables for slot occupation
                slot_occupied = {}
                for slot in range(1, 7):
                    if slot_to_vars[slot]:
                        slot_occupied[slot] = self.model.NewBoolVar(
                            f"occ_{batch}_{day}_{slot}"
                        )
                        # slot_occupied = 1 if any session uses this slot
                        self.model.AddMaxEquality(
                            slot_occupied[slot], 
                            slot_to_vars[slot]
                        )
                
                # Penalize gaps (empty slot between occupied slots)
                # Simple gap penalty: for each pair (occupied, empty, occupied)
                for s in range(2, 6):  # Middle slots that could be gaps
                    if s in slot_occupied and (s-1) in slot_occupied and (s+1) in slot_occupied:
                        # s is a gap if s-1 occupied, s empty, s+1 occupied
                        gap_var = self.model.NewBoolVar(f"gap_{batch}_{day}_{s}")
                        
                        # gap_var = 1 if (s-1 occupied) AND (s not occupied) AND (s+1 occupied)
                        # Simplified: just penalize non-consecutive when there are 2+ classes
                        pass  # Full gap calculation is complex, skip for now
        
        if objective_terms:
            self.model.Minimize(sum(objective_terms))
    
    def _process_result(
        self,
        status: int,
        sessions: List[ClassSession],
        sessions_by_batch: Dict[str, List[ClassSession]],
        solving_time: float
    ) -> GeneratorResult:
        """Process solver result and return GeneratorResult."""
        
        if status == cp_model.OPTIMAL:
            result_status = SolverStatus.OPTIMAL
            print(f"\n✅ OPTIMAL solution found!")
        elif status == cp_model.FEASIBLE:
            result_status = SolverStatus.FEASIBLE
            print(f"\n✅ FEASIBLE solution found (may not be optimal)")
        elif status == cp_model.INFEASIBLE:
            result_status = SolverStatus.INFEASIBLE
            print(f"\n❌ INFEASIBLE - No valid schedule exists")
            return self._analyze_infeasibility(sessions, sessions_by_batch, solving_time)
        else:
            result_status = SolverStatus.TIMEOUT
            print(f"\n⚠️ TIMEOUT - No solution found within time limit")
            return GeneratorResult(
                status=result_status,
                explanation=f"Solver timed out after {solving_time:.1f}s",
                solving_time_seconds=solving_time,
                total_sessions=len(sessions)
            )
        
        # Extract solution
        scheduled_sessions = []
        schedule_by_batch: Dict[str, List[ScheduledSession]] = defaultdict(list)
        
        for session in sessions:
            for day in range(self.NUM_DAYS):
                for slot, var in self.x[session.session_id].get(day, {}).items():
                    if self.solver.Value(var) == 1:
                        scheduled = ScheduledSession(
                            session=session,
                            day=DAYS[day],
                            day_idx=day,
                            slot_start=slot,
                            slot_end=slot + session.slot_duration - 1,
                            room_code=""  # Room assignment if needed
                        )
                        scheduled_sessions.append(scheduled)
                        schedule_by_batch[session.batch_section].append(scheduled)
                        break
        
        # Calculate statistics
        total_late = sum(
            1 for s in scheduled_sessions 
            if s.slot_end == 6
        )
        
        # Calculate gaps per batch
        total_gaps = 0
        for batch, batch_schedule in schedule_by_batch.items():
            total_gaps += self._calculate_batch_gaps(batch_schedule)
        
        print(f"\nSolution Statistics:")
        print(f"  Scheduled: {len(scheduled_sessions)}/{len(sessions)} sessions")
        print(f"  Late slots (slot 6): {total_late}")
        print(f"  Total gaps: {total_gaps}")
        print(f"  Objective value: {self.solver.ObjectiveValue()}")
        print(f"  Solving time: {solving_time:.2f}s")
        
        return GeneratorResult(
            status=result_status,
            scheduled_sessions=scheduled_sessions,
            schedule_by_batch=dict(schedule_by_batch),
            total_sessions=len(sessions),
            total_scheduled=len(scheduled_sessions),
            total_gaps=total_gaps,
            total_late_slots=total_late,
            objective_value=self.solver.ObjectiveValue(),
            solving_time_seconds=solving_time,
            explanation=f"Successfully scheduled {len(scheduled_sessions)} sessions"
        )
    
    def _calculate_batch_gaps(self, batch_schedule: List[ScheduledSession]) -> int:
        """Calculate total gaps in a batch's schedule."""
        gaps = 0
        
        # Group by day
        by_day = defaultdict(list)
        for s in batch_schedule:
            by_day[s.day_idx].append(s)
        
        for day_idx, day_sessions in by_day.items():
            if len(day_sessions) < 2:
                continue
            
            # Get all occupied slots
            occupied = set()
            for s in day_sessions:
                for slot in range(s.slot_start, s.slot_end + 1):
                    occupied.add(slot)
            
            if not occupied:
                continue
            
            # Count gaps (don't count break between slot 3 and 4 as gap)
            min_slot = min(occupied)
            max_slot = max(occupied)
            
            for slot in range(min_slot, max_slot + 1):
                if slot not in occupied:
                    # Don't count the break gap
                    if not (slot == 3 and 4 in occupied) and not (slot == 4 and 3 in occupied):
                        gaps += 1
        
        return gaps
    
    def _analyze_infeasibility(
        self,
        sessions: List[ClassSession],
        sessions_by_batch: Dict[str, List[ClassSession]],
        solving_time: float
    ) -> GeneratorResult:
        """Analyze why the problem is infeasible."""
        conflicts = []
        
        # Check for overloaded teachers
        sessions_by_teacher = defaultdict(list)
        for s in sessions:
            sessions_by_teacher[s.teacher_name].append(s)
        
        for teacher, teacher_sessions in sessions_by_teacher.items():
            # Max possible slots = 5 days * 6 slots = 30
            # But labs take 2 slots each
            required_slots = sum(s.slot_duration for s in teacher_sessions)
            if required_slots > 30:
                conflicts.append(
                    f"Teacher '{teacher}' needs {required_slots} slots "
                    f"but only 30 available"
                )
        
        # Check for overloaded batches
        for batch, batch_sessions in sessions_by_batch.items():
            required_slots = sum(s.slot_duration for s in batch_sessions)
            if required_slots > 30:
                conflicts.append(
                    f"Batch '{batch}' needs {required_slots} slots "
                    f"but only 30 available"
                )
        
        return GeneratorResult(
            status=SolverStatus.INFEASIBLE,
            conflicts=conflicts,
            explanation="No valid schedule exists. See conflicts for details.",
            solving_time_seconds=solving_time,
            total_sessions=len(sessions)
        )


def assign_rooms(
    scheduled_sessions: List[ScheduledSession],
    available_rooms: List[str],
    lab_rooms: List[str]
) -> List[ScheduledSession]:
    """
    Assign rooms to scheduled sessions, ensuring no room clashes.
    
    Args:
        scheduled_sessions: List of scheduled sessions
        available_rooms: List of lecture room codes
        lab_rooms: List of lab room codes
        
    Returns:
        List of sessions with room assignments
    """
    # Track room usage: (day, slot) -> room
    room_usage: Dict[Tuple[int, int], Set[str]] = defaultdict(set)
    
    for session in scheduled_sessions:
        # Determine room pool
        if session.is_lab:
            room_pool = lab_rooms
        else:
            room_pool = available_rooms
        
        # Find available room
        assigned_room = None
        for room in room_pool:
            # Check all slots this session occupies
            is_available = True
            for slot in range(session.slot_start, session.slot_end + 1):
                key = (session.day_idx, slot)
                if room in room_usage[key]:
                    is_available = False
                    break
            
            if is_available:
                assigned_room = room
                break
        
        if assigned_room:
            session.room_code = assigned_room
            for slot in range(session.slot_start, session.slot_end + 1):
                room_usage[(session.day_idx, slot)].add(assigned_room)
        else:
            session.room_code = "TBA"  # To Be Assigned
    
    return scheduled_sessions
