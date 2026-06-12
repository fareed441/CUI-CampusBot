"""
Layer-1: Fast Path Alternative Offering Suggestion

This is the first layer of repeater clash resolution.
It uses bitmask operations for O(n) filtering of alternative offerings.

Features:
- Ultra-fast clash detection using 30-bit bitmasks
- Returns ALL alternative offerings for a course
- Separates feasible (✅) and conflicting (❌) alternatives
- Provides detailed clash reasons for conflicts
- Ranks feasible alternatives by quality (gaps, department match, etc.)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import time

import sys
sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

from timetable_core.models import (
    Offering, Student, Course, ClashDetail, AlternativeSuggestion,
    TIMESLOTS, DAY_FULL_NAMES
)
from timetable_core.bitmask import (
    offering_to_bitmask,
    student_schedule_mask,
    check_clash,
    get_clash_details,
    total_gaps,
    count_late_slots,
    combine_masks,
)
from timetable_core.fuzzy_match import CourseMatcher, FuzzyMatch


@dataclass
class SuggestionResult:
    """Result from Layer-1 suggestion"""
    course_query: str
    matched_course: Optional[Course]
    match_confidence: float
    
    # Feasible alternatives (no clash with student schedule)
    feasible_alternatives: List[AlternativeSuggestion] = field(default_factory=list)
    
    # Conflicting alternatives (with clash details)
    conflicting_alternatives: List[AlternativeSuggestion] = field(default_factory=list)
    
    # Processing time (ms)
    processing_time_ms: float = 0.0
    
    # Status
    has_solution: bool = False
    message: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "course_query": self.course_query,
            "matched_course": self.matched_course.to_dict() if self.matched_course else None,
            "match_confidence": self.match_confidence,
            "feasible_alternatives": [a.to_dict() for a in self.feasible_alternatives],
            "conflicting_alternatives": [a.to_dict() for a in self.conflicting_alternatives],
            "processing_time_ms": self.processing_time_ms,
            "has_solution": self.has_solution,
            "message": self.message,
        }


class RepeaterSuggester:
    """
    Layer-1 fast-path suggester for repeater students.
    
    Given a student's current schedule and a course query,
    finds all alternative offerings ranked by feasibility and quality.
    """
    
    def __init__(
        self,
        offerings: List[Offering],
        course_matcher: Optional[CourseMatcher] = None
    ):
        """
        Initialize with all available offerings.
        
        Args:
            offerings: List of all section offerings
            course_matcher: Optional fuzzy matcher (created if not provided)
        """
        # Build offerings map by ID
        self.offerings_by_id: Dict[str, Offering] = {
            o.offering_id: o for o in offerings
        }
        
        # Build offerings index by course code
        self.offerings_by_course: Dict[str, List[Offering]] = {}
        for offering in offerings:
            code = offering.course.course_code
            if code not in self.offerings_by_course:
                self.offerings_by_course[code] = []
            self.offerings_by_course[code].append(offering)
        
        # Precompute all bitmasks for fast access
        self._precompute_bitmasks(offerings)
        
        # Course matcher
        if course_matcher is None:
            course_matcher = CourseMatcher()
            course_matcher.register_courses_from_offerings(offerings)
        self.course_matcher = course_matcher
    
    def _precompute_bitmasks(self, offerings: List[Offering]):
        """Precompute bitmasks for all offerings."""
        for offering in offerings:
            # This caches the bitmask in offering._bitmask
            offering_to_bitmask(offering)
    
    def get_student_mask(
        self, 
        student: Student,
        exclude_offering_ids: Optional[List[str]] = None
    ) -> int:
        """
        Get combined bitmask of student's schedule.
        
        Args:
            student: The student
            exclude_offering_ids: Offerings to exclude (e.g., the conflicting one)
        """
        if exclude_offering_ids:
            # Can't use cached mask, compute fresh
            mask = 0
            for oid in student.enrolled_offering_ids:
                if oid not in exclude_offering_ids and oid in self.offerings_by_id:
                    mask |= offering_to_bitmask(self.offerings_by_id[oid])
            return mask
        else:
            return student_schedule_mask(student, self.offerings_by_id)
    
    def suggest_alternatives(
        self,
        student: Student,
        course_query: str,
        exclude_current_offering_id: Optional[str] = None,
        prefer_department: Optional[str] = None,
    ) -> SuggestionResult:
        """
        Main Layer-1 entry point.
        
        Given a student and course query (e.g., "AI"), find all alternative
        offerings of that course and classify as feasible or conflicting.
        
        Args:
            student: The repeater student
            course_query: Natural language query like "AI" or "Artificial Intelligence"
            exclude_current_offering_id: ID of the conflicting offering to exclude
            prefer_department: Preferred department for ranking
        
        Returns:
            SuggestionResult with feasible and conflicting alternatives
        """
        start_time = time.perf_counter()
        
        result = SuggestionResult(
            course_query=course_query,
            matched_course=None,
            match_confidence=0.0,
        )
        
        # Step 1: Fuzzy match course query
        matches = self.course_matcher.search(course_query)
        if not matches:
            result.message = f"No course found matching '{course_query}'"
            result.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        best_match = matches[0]
        course_code = best_match.course_code
        course = self.course_matcher.get_course(course_code)
        
        result.matched_course = course
        result.match_confidence = best_match.score
        
        # Step 2: Get all offerings of this course
        offerings = self.offerings_by_course.get(course_code, [])
        if not offerings:
            result.message = f"No offerings found for course '{course.course_name}'"
            result.processing_time_ms = (time.perf_counter() - start_time) * 1000
            return result
        
        # Step 3: Get student's current schedule mask
        exclude_ids = [exclude_current_offering_id] if exclude_current_offering_id else None
        student_mask = self.get_student_mask(student, exclude_ids)
        
        # Step 4: Check each offering for clashes (O(n) with bitmasks)
        feasible = []
        conflicting = []
        
        for offering in offerings:
            # Skip the offering being replaced
            if exclude_current_offering_id and offering.offering_id == exclude_current_offering_id:
                continue
            
            offering_mask = offering_to_bitmask(offering)
            
            if check_clash(student_mask, offering_mask):
                # Has clash - get details
                clashes = get_clash_details(
                    student_mask, 
                    offering_mask,
                    "student_schedule",
                    offering.offering_id
                )
                
                # Build clash reason string
                clash_reasons = []
                for clash in clashes:
                    # Find which enrolled offering causes this clash
                    for enrolled_id in student.enrolled_offering_ids:
                        if enrolled_id in self.offerings_by_id:
                            enrolled = self.offerings_by_id[enrolled_id]
                            enrolled_mask = offering_to_bitmask(enrolled)
                            if check_clash(enrolled_mask, offering_mask):
                                clash_reasons.append(
                                    f"Clashes with {enrolled.course.course_name} "
                                    f"({enrolled.batch_section}) on {clash.day.name} Slot {clash.slot}"
                                )
                                break
                
                suggestion = AlternativeSuggestion(
                    offering=offering,
                    is_feasible=False,
                    clash_details=clashes,
                    reason="; ".join(clash_reasons) if clash_reasons else "Schedule conflict"
                )
                conflicting.append(suggestion)
            else:
                # No clash - calculate quality score
                combined_mask = combine_masks(student_mask, offering_mask)
                gaps = total_gaps(combined_mask)
                late_slots = count_late_slots(offering_mask)
                
                # Score: lower is better
                # Prioritize: same department > fewer gaps > fewer late slots
                dept_penalty = 0 if (prefer_department and 
                    offering.teacher.department == prefer_department) else 5
                score = gaps * 2 + late_slots + dept_penalty
                
                suggestion = AlternativeSuggestion(
                    offering=offering,
                    is_feasible=True,
                    score=score,
                    reason=f"✅ Available - {gaps} gaps, {late_slots} late slots"
                )
                feasible.append(suggestion)
        
        # Sort feasible by score (lower is better)
        feasible.sort(key=lambda x: x.score)
        
        # Sort conflicting by number of clashes (fewer is better - easier to resolve)
        conflicting.sort(key=lambda x: len(x.clash_details))
        
        result.feasible_alternatives = feasible
        result.conflicting_alternatives = conflicting
        result.has_solution = len(feasible) > 0
        
        if feasible:
            result.message = f"Found {len(feasible)} clash-free alternative(s) for {course.course_name}"
        else:
            result.message = f"No clash-free alternatives for {course.course_name}. All {len(conflicting)} offerings conflict."
        
        result.processing_time_ms = (time.perf_counter() - start_time) * 1000
        return result


def find_alternative_offerings(
    student: Student,
    course_query: str,
    offerings: List[Offering],
    course_matcher: Optional[CourseMatcher] = None,
    exclude_offering_id: Optional[str] = None,
) -> SuggestionResult:
    """
    Convenience function for Layer-1 suggestion.
    
    Args:
        student: The repeater student
        course_query: Course query string (e.g., "AI")
        offerings: All available offerings
        course_matcher: Optional fuzzy matcher
        exclude_offering_id: Offering to exclude from suggestions
    
    Returns:
        SuggestionResult with alternatives
    """
    suggester = RepeaterSuggester(offerings, course_matcher)
    return suggester.suggest_alternatives(
        student,
        course_query,
        exclude_current_offering_id=exclude_offering_id
    )
