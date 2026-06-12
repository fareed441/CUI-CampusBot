"""
Core data models for the timetable system.
Timeslots match the exact PDF format:
  Slot 1: 8:30–10:00
  Slot 2: 10:00–11:30
  Slot 3: 11:30–1:00
  BREAK: 1:00–1:30 (no classes)
  Slot 4: 1:30–3:00
  Slot 5: 3:00–4:30
  Slot 6: 4:30–6:00
  Days: Monday–Friday
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import time


class Day(Enum):
    """Days of the week (Monday to Friday)"""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4


# Short day names for display
DAY_SHORT_NAMES = {
    Day.MONDAY: "Mon",
    Day.TUESDAY: "Tue",
    Day.WEDNESDAY: "Wed",
    Day.THURSDAY: "Thu",
    Day.FRIDAY: "Fri",
}

DAY_FULL_NAMES = {
    Day.MONDAY: "Monday",
    Day.TUESDAY: "Tuesday",
    Day.WEDNESDAY: "Wednesday",
    Day.THURSDAY: "Thursday",
    Day.FRIDAY: "Friday",
}

DAYS = list(Day)


@dataclass
class TimeSlot:
    """A single time slot definition"""
    slot_number: int  # 1-6
    start_time: time
    end_time: time
    display_start: str  # e.g., "8:30"
    display_end: str    # e.g., "10:00"
    is_after_break: bool = False  # True for slots 4, 5, 6
    
    @property
    def display(self) -> str:
        """Format like 'Slot 1 / 8:30 - 10:00 AM'"""
        start_period = "AM" if self.start_time.hour < 12 else "PM"
        end_period = "AM" if self.end_time.hour < 12 or (self.end_time.hour == 12 and self.end_time.minute == 0) else "PM"
        # For afternoon slots, adjust display
        if self.slot_number <= 3:
            return f"Slot {self.slot_number} / {self.display_start} - {self.display_end} AM"
        else:
            return f"Slot {self.slot_number} / {self.display_start} - {self.display_end} PM"
    
    @property
    def header_display(self) -> str:
        """Format for table header"""
        if self.slot_number <= 3:
            period = "AM"
            start_disp = self.display_start
            end_disp = self.display_end
        else:
            period = "PM"
            start_disp = self.display_start
            end_disp = self.display_end
        return f"Slot {self.slot_number}\n{start_disp} - {end_disp} {period}"


# Define the exact timeslots as per PDF
TIMESLOTS = {
    1: TimeSlot(
        slot_number=1,
        start_time=time(8, 30),
        end_time=time(10, 0),
        display_start="8:30",
        display_end="10:00",
        is_after_break=False
    ),
    2: TimeSlot(
        slot_number=2,
        start_time=time(10, 0),
        end_time=time(11, 30),
        display_start="10:00",
        display_end="11:30",
        is_after_break=False
    ),
    3: TimeSlot(
        slot_number=3,
        start_time=time(11, 30),
        end_time=time(13, 0),
        display_start="11:30",
        display_end="1:00",
        is_after_break=False
    ),
    # BREAK: 1:00 - 1:30 PM (not a slot, just a column)
    4: TimeSlot(
        slot_number=4,
        start_time=time(13, 30),
        end_time=time(15, 0),
        display_start="1:30",
        display_end="3:00",
        is_after_break=True
    ),
    5: TimeSlot(
        slot_number=5,
        start_time=time(15, 0),
        end_time=time(16, 30),
        display_start="3:00",
        display_end="4:30",
        is_after_break=True
    ),
    6: TimeSlot(
        slot_number=6,
        start_time=time(16, 30),
        end_time=time(18, 0),
        display_start="4:30",
        display_end="6:00",
        is_after_break=True
    ),
}

# Total cells in a week: 5 days * 6 slots = 30
TOTAL_CELLS = 30


class RoomType(Enum):
    """Type of room"""
    LECTURE = "lecture"
    LAB = "lab"


class OfferingType(Enum):
    """Type of offering (lecture or lab)"""
    LECTURE = "LEC"
    LAB = "LAB"


@dataclass
class Meeting:
    """A single meeting/class session"""
    day: Day
    slot_start: int  # 1-6
    slot_end: int    # 1-6 (same as slot_start for 1-slot classes, +1 for labs)
    
    def __post_init__(self):
        if self.slot_start < 1 or self.slot_start > 6:
            raise ValueError(f"slot_start must be 1-6, got {self.slot_start}")
        if self.slot_end < self.slot_start or self.slot_end > 6:
            raise ValueError(f"slot_end must be >= slot_start and <= 6, got {self.slot_end}")
        # Labs cannot cross the break (slot 3 to slot 4)
        if self.slot_start <= 3 < self.slot_end:
            raise ValueError("Labs cannot span across break (slot 3 to 4)")
    
    @property
    def duration_slots(self) -> int:
        """Number of slots this meeting spans"""
        return self.slot_end - self.slot_start + 1
    
    @property
    def is_double_slot(self) -> bool:
        """True for 2-slot classes (labs)"""
        return self.duration_slots == 2
    
    def get_timeslot_start(self) -> TimeSlot:
        return TIMESLOTS[self.slot_start]
    
    def get_timeslot_end(self) -> TimeSlot:
        return TIMESLOTS[self.slot_end]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day.name,
            "day_index": self.day.value,
            "slot_start": self.slot_start,
            "slot_end": self.slot_end,
            "start_time": self.get_timeslot_start().display_start,
            "end_time": self.get_timeslot_end().display_end,
        }


@dataclass
class Course:
    """Course definition"""
    course_code: str
    course_name: str
    credit_hours: int = 3
    has_lab: bool = False
    department: str = ""
    
    # Aliases for fuzzy matching
    aliases: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "course_code": self.course_code,
            "course_name": self.course_name,
            "credit_hours": self.credit_hours,
            "has_lab": self.has_lab,
            "department": self.department,
            "aliases": self.aliases,
        }


@dataclass 
class Teacher:
    """Teacher definition"""
    teacher_id: str
    name: str
    department: str = ""
    email: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "teacher_id": self.teacher_id,
            "name": self.name,
            "department": self.department,
            "email": self.email,
        }


@dataclass
class Room:
    """Room definition"""
    room_id: str
    room_code: str  # e.g., "CS-3", "MS-6"
    room_type: RoomType
    capacity: int = 50
    building: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "room_code": self.room_code,
            "room_type": self.room_type.value,
            "capacity": self.capacity,
            "building": self.building,
        }


@dataclass
class Offering:
    """
    A section offering of a course.
    This is the main scheduling unit.
    """
    offering_id: str
    course: Course
    batch_section: str  # e.g., "BCS-FA25-2A"
    teacher: Teacher
    room: Room
    offering_type: OfferingType
    meetings: List[Meeting] = field(default_factory=list)
    
    # Cached bitmask (computed lazily)
    _bitmask: Optional[int] = field(default=None, repr=False)
    
    @property
    def display_name(self) -> str:
        return f"{self.course.course_name} ({self.batch_section})"
    
    def add_meeting(self, meeting: Meeting):
        """Add a meeting and invalidate cached bitmask"""
        self.meetings.append(meeting)
        self._bitmask = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "offering_id": self.offering_id,
            "course": self.course.to_dict(),
            "batch_section": self.batch_section,
            "teacher": self.teacher.to_dict(),
            "room": self.room.to_dict(),
            "offering_type": self.offering_type.value,
            "meetings": [m.to_dict() for m in self.meetings],
        }


@dataclass
class Student:
    """Student with enrolled offerings"""
    student_id: str
    name: str
    batch_section: str  # Primary batch
    enrolled_offering_ids: List[str] = field(default_factory=list)
    is_repeater: bool = False
    repeat_courses: List[str] = field(default_factory=list)  # Course codes pending repeat
    
    # Cached schedule bitmask
    _schedule_mask: Optional[int] = field(default=None, repr=False)
    
    def add_offering(self, offering_id: str):
        """Add an offering and invalidate cached mask"""
        if offering_id not in self.enrolled_offering_ids:
            self.enrolled_offering_ids.append(offering_id)
            self._schedule_mask = None
    
    def remove_offering(self, offering_id: str):
        """Remove an offering and invalidate cached mask"""
        if offering_id in self.enrolled_offering_ids:
            self.enrolled_offering_ids.remove(offering_id)
            self._schedule_mask = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "student_id": self.student_id,
            "name": self.name,
            "batch_section": self.batch_section,
            "enrolled_offering_ids": self.enrolled_offering_ids,
            "is_repeater": self.is_repeater,
            "repeat_courses": self.repeat_courses,
        }


@dataclass
class ClashDetail:
    """Details about a specific clash"""
    day: Day
    slot: int
    offering1_id: str
    offering2_id: str
    reason: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day.name,
            "day_display": DAY_FULL_NAMES[self.day],
            "slot": self.slot,
            "slot_time": TIMESLOTS[self.slot].display,
            "offering1_id": self.offering1_id,
            "offering2_id": self.offering2_id,
            "reason": self.reason,
        }


@dataclass
class AlternativeSuggestion:
    """A suggested alternative offering"""
    offering: Offering
    is_feasible: bool
    clash_details: List[ClashDetail] = field(default_factory=list)
    score: float = 0.0  # Lower is better (gaps + late penalty)
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "offering": self.offering.to_dict(),
            "is_feasible": self.is_feasible,
            "clash_details": [c.to_dict() for c in self.clash_details],
            "score": self.score,
            "reason": self.reason,
        }
