# Timetable Core Module
# Clean architecture for clash-free timetable system

from .models import (
    TimeSlot,
    Day,
    Meeting,
    Offering,
    Student,
    Room,
    Teacher,
    Course,
    TIMESLOTS,
    DAYS,
    TOTAL_CELLS,
)
from .bitmask import (
    meeting_to_bitmask,
    offering_to_bitmask,
    student_schedule_mask,
    check_clash,
    get_clash_details,
)

__all__ = [
    "TimeSlot",
    "Day",
    "Meeting",
    "Offering",
    "Student",
    "Room",
    "Teacher",
    "Course",
    "TIMESLOTS",
    "DAYS",
    "TOTAL_CELLS",
    "meeting_to_bitmask",
    "offering_to_bitmask",
    "student_schedule_mask",
    "check_clash",
    "get_clash_details",
]
