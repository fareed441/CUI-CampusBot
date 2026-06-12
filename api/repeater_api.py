"""
Repeater Clash Resolution API Endpoints

Provides REST endpoints for:
- POST /api/repeater/suggest - Layer-1 fast alternative suggestions
- POST /api/repeater/solve - Layer-2 CP-SAT multi-course solver
- GET /api/repeater/student/{student_id}/schedule - Get student schedule
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

import sys
sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

from timetable_core.models import Student
from timetable_core.bitmask import student_schedule_mask, offering_to_bitmask, mask_to_string
from solver.layer1_suggest import RepeaterSuggester, SuggestionResult
from solver.layer2_cpsat import RepeaterSolver, SolverResult, SolverStatus
from api.data_store import DataStore


router = APIRouter(prefix="/api/repeater", tags=["Repeater Resolution"])


class SuggestRequest(BaseModel):
    """Request for Layer-1 alternative suggestions"""
    student_id: str
    course_query: str
    exclude_offering_id: Optional[str] = None


class SuggestResponse(BaseModel):
    """Response from Layer-1 suggestion"""
    course_query: str
    matched_course_code: Optional[str]
    matched_course_name: Optional[str]
    match_confidence: float
    
    feasible_count: int
    conflicting_count: int
    
    feasible_alternatives: List[Dict[str, Any]]
    conflicting_alternatives: List[Dict[str, Any]]
    
    has_solution: bool
    message: str
    processing_time_ms: float


class SolveRequest(BaseModel):
    """Request for Layer-2 CP-SAT solver"""
    student_id: str
    course_queries: List[str]
    exclude_offerings: Optional[List[str]] = None
    time_limit_seconds: float = Field(default=2.0, ge=0.1, le=30.0)


class SolveResponse(BaseModel):
    """Response from Layer-2 solver"""
    status: str
    chosen_offerings: Dict[str, Dict[str, Any]]
    explanation: str
    total_gaps: int
    total_late_slots: int
    objective_value: float
    solving_time_ms: float
    conflicts: List[str]


class StudentScheduleResponse(BaseModel):
    """Student schedule response"""
    student_id: str
    student_name: str
    primary_batch: str
    is_repeater: bool
    enrolled_offerings: List[Dict[str, Any]]
    schedule_bitmask: int
    schedule_display: str


class StudentListItem(BaseModel):
    """Student list item"""
    id: str
    name: str
    roll_number: str
    batch: str
    is_repeater: bool


@router.get("/students", response_model=List[StudentListItem])
async def list_students():
    """
    List all students in the system.
    
    Returns student IDs, names, and roll numbers for selection UIs.
    """
    store = DataStore.get_instance()
    students = store.get_all_students()
    
    return [
        StudentListItem(
            id=s.student_id,
            name=s.name,
            roll_number=s.student_id,  # Use student_id as roll number
            batch=s.batch_section,
            is_repeater=s.is_repeater
        )
        for s in students
    ]


@router.post("/suggest", response_model=SuggestResponse)
async def suggest_alternatives(request: SuggestRequest):
    """
    Layer-1: Fast path alternative offering suggestions.
    
    Given a student and course query, returns all alternative offerings
    ranked by feasibility and quality.
    
    Performance target: < 200ms for typical data.
    """
    store = DataStore.get_instance()
    
    # Get student
    student = store.get_student(request.student_id)
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"Student '{request.student_id}' not found"
        )
    
    # Get all offerings
    offerings = store.get_all_offerings()
    
    # Run Layer-1 suggestion
    suggester = RepeaterSuggester(offerings, store.get_course_matcher())
    result = suggester.suggest_alternatives(
        student=student,
        course_query=request.course_query,
        exclude_current_offering_id=request.exclude_offering_id
    )
    
    return SuggestResponse(
        course_query=result.course_query,
        matched_course_code=result.matched_course.course_code if result.matched_course else None,
        matched_course_name=result.matched_course.course_name if result.matched_course else None,
        match_confidence=result.match_confidence,
        feasible_count=len(result.feasible_alternatives),
        conflicting_count=len(result.conflicting_alternatives),
        feasible_alternatives=[a.to_dict() for a in result.feasible_alternatives],
        conflicting_alternatives=[a.to_dict() for a in result.conflicting_alternatives],
        has_solution=result.has_solution,
        message=result.message,
        processing_time_ms=result.processing_time_ms
    )


@router.post("/solve", response_model=SolveResponse)
async def solve_multi_course(request: SolveRequest):
    """
    Layer-2: CP-SAT solver for multi-course repeater resolution.
    
    When Layer-1 cannot find a solution or student has multiple repeat
    courses, this solver finds an optimal combination.
    
    Performance target: < 2s (configurable).
    """
    store = DataStore.get_instance()
    
    # Get student
    student = store.get_student(request.student_id)
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"Student '{request.student_id}' not found"
        )
    
    # Get all offerings
    offerings = store.get_all_offerings()
    
    # Run Layer-2 solver
    solver = RepeaterSolver(offerings, request.time_limit_seconds)
    
    # Convert course_queries to course codes
    matcher = store.get_course_matcher()
    course_codes = []
    for query in request.course_queries:
        matches = matcher.search(query)
        if not matches:
            raise HTTPException(
                status_code=400,
                detail=f"Could not find course matching '{query}'"
            )
        course_codes.append(matches[0].course_code)
    
    exclude_set = set(request.exclude_offerings) if request.exclude_offerings else None
    
    result = solver.solve(
        student=student,
        course_codes=course_codes,
        exclude_offerings=exclude_set
    )
    
    return SolveResponse(
        status=result.status.value,
        chosen_offerings={
            code: off.to_dict() for code, off in result.chosen_offerings.items()
        },
        explanation=result.explanation,
        total_gaps=result.total_gaps,
        total_late_slots=result.total_late_slots,
        objective_value=result.objective_value,
        solving_time_ms=result.solving_time_ms,
        conflicts=result.conflicts
    )


@router.get("/student/{student_id}/schedule", response_model=StudentScheduleResponse)
async def get_student_schedule(student_id: str):
    """
    Get a student's current enrolled schedule.
    
    Returns all enrolled offerings with combined bitmask.
    """
    store = DataStore.get_instance()
    
    student = store.get_student(student_id)
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"Student '{student_id}' not found"
        )
    
    # Get enrolled offerings
    enrolled = []
    for oid in student.enrolled_offering_ids:
        offering = store.get_offering(oid)
        if offering:
            enrolled.append(offering)
    
    # Compute schedule mask
    offerings_map = {o.offering_id: o for o in store.get_all_offerings()}
    mask = student_schedule_mask(student, offerings_map)
    
    return StudentScheduleResponse(
        student_id=student.student_id,
        student_name=student.name,
        primary_batch=student.batch_section,
        is_repeater=student.is_repeater,
        enrolled_offerings=[o.to_dict() for o in enrolled],
        schedule_bitmask=mask,
        schedule_display=mask_to_string(mask)
    )


class EnrollRequest(BaseModel):
    """Request to enroll in an offering"""
    offering_id: str


@router.post("/student/{student_id}/enroll")
async def enroll_offering(student_id: str, request: EnrollRequest):
    """
    Enroll a student in an offering.
    """
    store = DataStore.get_instance()
    
    student = store.get_student(student_id)
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"Student '{student_id}' not found"
        )
    
    offering = store.get_offering(request.offering_id)
    if not offering:
        raise HTTPException(
            status_code=404,
            detail=f"Offering '{request.offering_id}' not found"
        )
    
    # Check for clashes
    offerings_map = {o.offering_id: o for o in store.get_all_offerings()}
    current_mask = student_schedule_mask(student, offerings_map)
    new_mask = offering_to_bitmask(offering)
    
    if current_mask & new_mask:
        raise HTTPException(
            status_code=409,
            detail="This offering clashes with student's current schedule"
        )
    
    # Enroll
    student.add_offering(offering_id)
    
    return {"message": f"Student enrolled in {offering.course.course_name}"}


@router.delete("/student/{student_id}/enroll/{offering_id}")
async def unenroll_offering(student_id: str, offering_id: str):
    """
    Remove a student from an offering.
    """
    store = DataStore.get_instance()
    
    student = store.get_student(student_id)
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"Student '{student_id}' not found"
        )
    
    if offering_id not in student.enrolled_offering_ids:
        raise HTTPException(
            status_code=404,
            detail="Student not enrolled in this offering"
        )
    
    student.remove_offering(offering_id)
    
    return {"message": "Student removed from offering"}
