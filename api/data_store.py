"""
Data Store for Timetable System

In-memory data store with demo data.
Can be replaced with database backend.
"""
from typing import List, Dict, Optional, Any
from threading import Lock

import sys
sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

from timetable_core.models import (
    Offering, Student, Course, Teacher, Room, Meeting, Day,
    RoomType, OfferingType
)
from timetable_core.fuzzy_match import CourseMatcher


class DataStore:
    """
    Singleton data store for timetable data.
    
    Thread-safe access to offerings, students, courses, etc.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # Data storage
        self.offerings: Dict[str, Offering] = {}
        self.students: Dict[str, Student] = {}
        self.courses: Dict[str, Course] = {}
        self.teachers: Dict[str, Teacher] = {}
        self.rooms: Dict[str, Room] = {}
        
        # Indexes
        self._offerings_by_batch: Dict[str, List[Offering]] = {}
        self._offerings_by_course: Dict[str, List[Offering]] = {}
        
        # Course matcher
        self._course_matcher: Optional[CourseMatcher] = None
        
        # Load demo data
        self._load_demo_data()
    
    @classmethod
    def get_instance(cls) -> 'DataStore':
        """Get singleton instance."""
        return cls()
    
    def _load_demo_data(self):
        """Load demo data for testing."""
        # Create demo courses
        demo_courses = [
            Course("CSC301", "Artificial Intelligence", 3, False, "CS", ["AI", "A.I."]),
            Course("CSC302", "Machine Learning", 3, False, "CS", ["ML"]),
            Course("CSC303", "Database Systems", 3, True, "CS", ["DB", "DBMS"]),
            Course("CSC304", "Operating Systems", 3, True, "CS", ["OS"]),
            Course("CSC201", "Object Oriented Programming", 3, True, "CS", ["OOP"]),
            Course("CSC202", "Data Structures", 3, True, "CS", ["DSA", "DS"]),
            Course("CSC101", "Introduction to Computing", 3, True, "CS", ["ITC", "ICT"]),
            Course("CSC102", "Programming Fundamentals", 3, True, "CS", ["PF"]),
            Course("MTH101", "Calculus I", 3, False, "MATH", ["Cal", "Calculus"]),
            Course("MTH201", "Linear Algebra", 3, False, "MATH", ["LA"]),
            Course("ENG101", "English Composition", 3, False, "ENG", ["English"]),
            Course("PHY101", "Applied Physics", 3, True, "PHY", ["Physics"]),
        ]
        
        for course in demo_courses:
            self.courses[course.course_code] = course
        
        # Create demo teachers
        demo_teachers = [
            Teacher("T001", "Dr. Ahmed Khan", "CS", "ahmed@cui.edu.pk"),
            Teacher("T002", "Dr. Sara Ali", "CS", "sara@cui.edu.pk"),
            Teacher("T003", "Mr. Usman Malik", "CS", "usman@cui.edu.pk"),
            Teacher("T004", "Ms. Fatima Hassan", "CS", "fatima@cui.edu.pk"),
            Teacher("T005", "Dr. Zubair Ahmed", "MATH", "zubair@cui.edu.pk"),
            Teacher("T006", "Dr. Ayesha Tariq", "MATH", "ayesha@cui.edu.pk"),
            Teacher("T007", "Mr. Bilal Khan", "ENG", "bilal@cui.edu.pk"),
            Teacher("T008", "Dr. Imran Shah", "PHY", "imran@cui.edu.pk"),
        ]
        
        for teacher in demo_teachers:
            self.teachers[teacher.teacher_id] = teacher
        
        # Create demo rooms
        demo_rooms = [
            Room("R001", "CS-1", RoomType.LECTURE, 60, "Main"),
            Room("R002", "CS-2", RoomType.LECTURE, 60, "Main"),
            Room("R003", "CS-3", RoomType.LECTURE, 50, "Main"),
            Room("R004", "MS-1", RoomType.LECTURE, 70, "Main"),
            Room("R005", "MS-2", RoomType.LECTURE, 70, "Main"),
            Room("R006", "Lab-1", RoomType.LAB, 40, "Main"),
            Room("R007", "Lab-2", RoomType.LAB, 40, "Main"),
            Room("R008", "Lab-3", RoomType.LAB, 35, "Main"),
        ]
        
        for room in demo_rooms:
            self.rooms[room.room_id] = room
        
        # Create demo offerings for multiple batches
        self._create_batch_offerings("BCS-FA25-2A")
        self._create_batch_offerings("BCS-FA25-2B")
        self._create_batch_offerings("BCS-SP26-1")
        self._create_batch_offerings("BCS-FA22-8A")  # 8th semester for repeaters
        
        # Create demo students
        demo_students = [
            Student("S001", "Ali Hassan", "BCS-FA22-8A", [], True, ["CSC301"]),
            Student("S002", "Zara Khan", "BCS-FA25-2A", [], False, []),
            Student("S003", "Ahmed Raza", "BCS-SP26-1", [], False, []),
        ]
        
        # Enroll students in their batch offerings
        for student in demo_students:
            batch_offerings = self._offerings_by_batch.get(student.batch_section, [])
            for offering in batch_offerings:
                student.enrolled_offering_ids.append(offering.offering_id)
            self.students[student.student_id] = student
        
        # Build course matcher
        self._build_course_matcher()
    
    def _create_batch_offerings(self, batch_section: str):
        """Create a set of offerings for a batch."""
        courses_list = list(self.courses.values())
        teachers_list = list(self.teachers.values())
        rooms_list = [r for r in self.rooms.values() if r.room_type == RoomType.LECTURE]
        lab_rooms = [r for r in self.rooms.values() if r.room_type == RoomType.LAB]
        
        # Create different schedules for different batches
        base_id = len(self.offerings)
        
        # Sample schedule patterns per batch
        if "FA25-2A" in batch_section:
            schedule = [
                # (course_idx, teacher_idx, room_idx, day, slot_start, slot_end, is_lab)
                (0, 0, 0, Day.MONDAY, 1, 1, False),      # AI - Mon S1
                (0, 0, 0, Day.WEDNESDAY, 1, 1, False),   # AI - Wed S1
                (1, 1, 1, Day.MONDAY, 2, 2, False),      # ML - Mon S2
                (1, 1, 1, Day.THURSDAY, 2, 2, False),    # ML - Thu S2
                (2, 2, 2, Day.TUESDAY, 1, 1, False),     # DB - Tue S1
                (2, 2, 2, Day.TUESDAY, 4, 5, True),      # DB Lab - Tue S4-5
                (3, 3, 0, Day.WEDNESDAY, 2, 2, False),   # OS - Wed S2
                (3, 3, 0, Day.FRIDAY, 4, 5, True),       # OS Lab - Fri S4-5
                (8, 4, 3, Day.THURSDAY, 1, 1, False),    # Calculus - Thu S1
                (8, 4, 3, Day.FRIDAY, 1, 1, False),      # Calculus - Fri S1
            ]
        elif "FA25-2B" in batch_section:
            schedule = [
                (0, 0, 1, Day.MONDAY, 3, 3, False),      # AI - Mon S3
                (0, 0, 1, Day.THURSDAY, 3, 3, False),    # AI - Thu S3
                (1, 1, 2, Day.TUESDAY, 2, 2, False),     # ML - Tue S2
                (1, 1, 2, Day.FRIDAY, 2, 2, False),      # ML - Fri S2
                (2, 2, 0, Day.WEDNESDAY, 1, 1, False),   # DB - Wed S1
                (2, 2, 0, Day.WEDNESDAY, 4, 5, True),    # DB Lab - Wed S4-5
                (3, 3, 1, Day.MONDAY, 4, 4, False),      # OS - Mon S4
                (3, 3, 1, Day.THURSDAY, 4, 5, True),     # OS Lab - Thu S4-5
                (8, 5, 3, Day.TUESDAY, 1, 1, False),     # Calculus - Tue S1
                (8, 5, 3, Day.FRIDAY, 3, 3, False),      # Calculus - Fri S3
            ]
        elif "SP26-1" in batch_section:
            schedule = [
                (6, 2, 0, Day.MONDAY, 1, 1, False),      # ITC - Mon S1
                (6, 2, 0, Day.MONDAY, 4, 5, True),       # ITC Lab - Mon S4-5
                (7, 3, 1, Day.TUESDAY, 1, 1, False),     # PF - Tue S1
                (7, 3, 1, Day.TUESDAY, 4, 5, True),      # PF Lab - Tue S4-5
                (10, 6, 3, Day.WEDNESDAY, 1, 1, False),  # English - Wed S1
                (10, 6, 3, Day.FRIDAY, 1, 1, False),     # English - Fri S1
                (8, 4, 2, Day.THURSDAY, 1, 1, False),    # Calculus - Thu S1
                (8, 4, 2, Day.FRIDAY, 2, 2, False),      # Calculus - Fri S2
            ]
        else:  # FA22-8A (8th semester)
            schedule = [
                (0, 0, 0, Day.MONDAY, 4, 4, False),      # AI - Mon S4 (different time)
                (0, 0, 0, Day.WEDNESDAY, 5, 5, False),   # AI - Wed S5
                (1, 1, 1, Day.TUESDAY, 4, 4, False),     # ML - Tue S4
                (1, 1, 1, Day.THURSDAY, 5, 5, False),    # ML - Thu S5
                (2, 2, 2, Day.MONDAY, 5, 5, False),      # DB - Mon S5
                (2, 2, 2, Day.FRIDAY, 4, 5, True),       # DB Lab - Fri S4-5
            ]
        
        # Create offerings from schedule
        batch_offerings = []
        
        # Group schedule entries by course to create single offerings with multiple meetings
        course_meetings: Dict[int, List[tuple]] = {}
        for entry in schedule:
            course_idx = entry[0]
            if course_idx not in course_meetings:
                course_meetings[course_idx] = []
            course_meetings[course_idx].append(entry)
        
        for course_idx, meetings in course_meetings.items():
            first_entry = meetings[0]
            course = courses_list[first_entry[0] % len(courses_list)]
            teacher = teachers_list[first_entry[1] % len(teachers_list)]
            
            # Check if any meeting is a lab
            is_lab = any(m[6] for m in meetings)
            
            if is_lab:
                room = lab_rooms[first_entry[2] % len(lab_rooms)]
                offering_type = OfferingType.LAB
            else:
                room = rooms_list[first_entry[2] % len(rooms_list)]
                offering_type = OfferingType.LECTURE
            
            offering_id = f"OFF-{batch_section}-{course.course_code}"
            
            offering = Offering(
                offering_id=offering_id,
                course=course,
                batch_section=batch_section,
                teacher=teacher,
                room=room,
                offering_type=offering_type,
                meetings=[]
            )
            
            # Add all meetings
            for entry in meetings:
                _, _, _, day, slot_start, slot_end, _ = entry
                meeting = Meeting(day=day, slot_start=slot_start, slot_end=slot_end)
                offering.add_meeting(meeting)
            
            self.offerings[offering_id] = offering
            batch_offerings.append(offering)
            
            # Update course index
            if course.course_code not in self._offerings_by_course:
                self._offerings_by_course[course.course_code] = []
            self._offerings_by_course[course.course_code].append(offering)
        
        # Update batch index
        self._offerings_by_batch[batch_section] = batch_offerings
    
    def _build_course_matcher(self):
        """Build the fuzzy course matcher."""
        self._course_matcher = CourseMatcher()
        self._course_matcher.register_courses_from_offerings(list(self.offerings.values()))
    
    # Public access methods
    
    def get_offering(self, offering_id: str) -> Optional[Offering]:
        """Get offering by ID."""
        return self.offerings.get(offering_id)
    
    def get_all_offerings(self) -> List[Offering]:
        """Get all offerings."""
        return list(self.offerings.values())
    
    def get_offerings_by_batch(self, batch_section: str) -> List[Offering]:
        """Get all offerings for a batch."""
        return self._offerings_by_batch.get(batch_section, [])
    
    def get_offerings_by_course(self, course_code: str) -> List[Offering]:
        """Get all offerings of a course."""
        return self._offerings_by_course.get(course_code, [])
    
    def get_all_batches(self) -> List[str]:
        """Get all batch section names."""
        return list(self._offerings_by_batch.keys())
    
    def get_student(self, student_id: str) -> Optional[Student]:
        """Get student by ID."""
        return self.students.get(student_id)
    
    def get_all_students(self) -> List[Student]:
        """Get all students."""
        return list(self.students.values())
    
    def get_course_matcher(self) -> CourseMatcher:
        """Get course fuzzy matcher."""
        if self._course_matcher is None:
            self._build_course_matcher()
        return self._course_matcher
    
    def add_offering(self, offering: Offering):
        """Add a new offering."""
        self.offerings[offering.offering_id] = offering
        
        # Update indexes
        if offering.batch_section not in self._offerings_by_batch:
            self._offerings_by_batch[offering.batch_section] = []
        self._offerings_by_batch[offering.batch_section].append(offering)
        
        if offering.course.course_code not in self._offerings_by_course:
            self._offerings_by_course[offering.course.course_code] = []
        self._offerings_by_course[offering.course.course_code].append(offering)
        
        # Rebuild matcher
        self._build_course_matcher()
    
    def add_student(self, student: Student):
        """Add a new student."""
        self.students[student.student_id] = student
