"""
CSV Parser for Timetable Data

Parses Excel/CSV files with columns:
- SequencePage
- Batch/Section
- Course
- Teacher

Creates CourseOffering units for scheduling.
"""
import csv
import re
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional
from pathlib import Path
import sys

sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

from timetable_core.models import (
    Course, Teacher, Room, Offering, Meeting, 
    Day, OfferingType, RoomType
)


@dataclass
class ClassSession:
    """A class session to be scheduled"""
    session_id: str
    batch_section: str
    course_name: str
    teacher_name: str
    teacher_dept: str
    is_lab: bool = False
    credit_hours: int = 3
    slot_duration: int = 1  # 1 slot for lecture, 2 for lab
    
    def __hash__(self):
        return hash(self.session_id)


@dataclass 
class ParsedData:
    """Container for all parsed timetable data"""
    sessions: List[ClassSession] = field(default_factory=list)
    batch_sections: Set[str] = field(default_factory=set)
    teachers: Dict[str, str] = field(default_factory=dict)  # name -> dept
    courses: Set[str] = field(default_factory=set)
    
    # Statistics
    total_lectures: int = 0
    total_labs: int = 0


class TimetableDataParser:
    """
    Parses CSV/Excel data and creates class sessions for scheduling.
    """
    
    # Patterns to detect lab courses
    LAB_PATTERNS = [
        r'-lab\b',
        r'\blab\b',
        r'-lab$',
        r'lab$',
        r'laboratory',
        r'\(lab\)',
        r'practical',
    ]
    
    # Patterns for 2-hour courses
    TWO_HOUR_PATTERNS = [
        r'\(2\s*hrs?\.\?\)',
        r'\(2\s*hrs?\)',
        r'\(2\s*hr\)',
        r'2\s*hrs?\.',
        r'2hrs',
        r'\(2\s*cr\)',
        r'\(2cr\)',
        r'2cr\b',
        r'\(2h\)',
        r'\(2\s*h\s*rs\)',
    ]
    
    def __init__(self):
        self.sessions: List[ClassSession] = []
        self.batch_sections: Set[str] = set()
        self.teachers: Dict[str, str] = {}  # name -> dept
        self.courses: Set[str] = set()
        self.session_counter = 0
        
    def _normalize_string(self, s: str) -> str:
        """Normalize string by trimming and cleaning whitespace"""
        if not s:
            return ""
        # Replace multiple spaces with single space
        s = re.sub(r'\s+', ' ', s)
        return s.strip()
    
    def _is_lab(self, course_name: str) -> bool:
        """Check if course is a lab based on name patterns"""
        course_lower = course_name.lower()
        for pattern in self.LAB_PATTERNS:
            if re.search(pattern, course_lower):
                return True
        return False
    
    def _is_two_hour_course(self, course_name: str) -> bool:
        """Check if course is a 2-hour (2 credit) course"""
        course_lower = course_name.lower()
        for pattern in self.TWO_HOUR_PATTERNS:
            if re.search(pattern, course_lower):
                return True
        return False
    
    def _extract_teacher_dept(self, teacher_str: str) -> Tuple[str, str]:
        """
        Extract teacher name and department from string like:
        'Mariam Fiaz (CS)' or 'Dr.Hasnain Raza (Hum)'
        """
        if not teacher_str:
            return "", "Unknown"
            
        # Pattern: Name (Dept) or Name (DEPT)
        match = re.match(r'^(.+?)\s*\(([^)]+)\)\s*$', teacher_str)
        if match:
            name = self._normalize_string(match.group(1))
            dept = match.group(2).strip().upper()
            # Normalize department names
            dept_mapping = {
                'CS': 'CS',
                'HUM': 'HUM',
                'MTH': 'MATH',
                'MATH': 'MATH',
                'MS': 'MS',
                'BTY': 'BTY',
                'ES': 'ES',
                'ECO': 'ECO',
            }
            dept = dept_mapping.get(dept, dept)
            return name, dept
        
        # No parentheses, return as-is
        return self._normalize_string(teacher_str), "Unknown"
    
    def _clean_course_name(self, course_name: str) -> str:
        """Clean course name - remove duplicated text artifacts"""
        if not course_name:
            return ""
        
        # Common artifacts from PDF extraction
        # Example: "Object Oriented Object Oriented Programming Programming-Lab"
        # Should become: "Object Oriented Programming-Lab"
        
        name = self._normalize_string(course_name)
        
        # Remove common PDF extraction artifacts
        artifacts_to_clean = [
            (r'Object Oriented Object Oriented', 'Object Oriented'),
            (r'Programming Programming', 'Programming'),
            (r'Fundamentals Fundamentals', 'Fundamentals'),
            (r'Systems Systems', 'Systems'),
            (r'Technologies Technologies', 'Technologies'),
        ]
        
        for pattern, replacement in artifacts_to_clean:
            name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)
        
        return name
    
    def _generate_session_id(self, batch: str, course: str, teacher: str) -> str:
        """Generate unique session ID"""
        self.session_counter += 1
        # Create a short hash-like ID
        base = f"{batch}_{course[:20]}_{self.session_counter}"
        return re.sub(r'[^a-zA-Z0-9_-]', '', base)
    
    def parse_csv(self, csv_path: str) -> ParsedData:
        """
        Parse CSV file and create class sessions.
        
        Args:
            csv_path: Path to CSV file
            
        Returns:
            ParsedData with all parsed entities
        """
        self.sessions = []
        self.batch_sections = set()
        self.teachers = {}
        self.courses = set()
        self.session_counter = 0
        
        total_lectures = 0
        total_labs = 0
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Extract columns
                batch_section = self._normalize_string(row.get('Batch/Section', ''))
                course_raw = row.get('Course', '')
                teacher_raw = row.get('Teacher', '')
                
                if not batch_section or not course_raw:
                    continue
                
                # Clean course name
                course_name = self._clean_course_name(course_raw)
                if not course_name:
                    continue
                
                # Check if lab
                is_lab = self._is_lab(course_name)
                
                # Extract teacher info
                teacher_name, teacher_dept = self._extract_teacher_dept(teacher_raw)
                
                # Determine slot duration
                # Labs = 2 consecutive slots
                # 2-hour courses = 1 slot (handled differently in scheduling)
                if is_lab:
                    slot_duration = 2
                    total_labs += 1
                else:
                    slot_duration = 1
                    total_lectures += 1
                
                # Create session
                session_id = self._generate_session_id(batch_section, course_name, teacher_name)
                
                session = ClassSession(
                    session_id=session_id,
                    batch_section=batch_section,
                    course_name=course_name,
                    teacher_name=teacher_name,
                    teacher_dept=teacher_dept,
                    is_lab=is_lab,
                    slot_duration=slot_duration,
                )
                
                self.sessions.append(session)
                self.batch_sections.add(batch_section)
                self.courses.add(course_name)
                
                if teacher_name:
                    self.teachers[teacher_name] = teacher_dept
        
        return ParsedData(
            sessions=self.sessions,
            batch_sections=self.batch_sections,
            teachers=self.teachers,
            courses=self.courses,
            total_lectures=total_lectures,
            total_labs=total_labs,
        )
    
    def get_sessions_by_batch(self) -> Dict[str, List[ClassSession]]:
        """Group sessions by batch/section"""
        result: Dict[str, List[ClassSession]] = {}
        for session in self.sessions:
            if session.batch_section not in result:
                result[session.batch_section] = []
            result[session.batch_section].append(session)
        return result
    
    def get_sessions_by_teacher(self) -> Dict[str, List[ClassSession]]:
        """Group sessions by teacher"""
        result: Dict[str, List[ClassSession]] = {}
        for session in self.sessions:
            if session.teacher_name not in result:
                result[session.teacher_name] = []
            result[session.teacher_name].append(session)
        return result
    
    def print_summary(self):
        """Print summary of parsed data"""
        print("\n" + "="*60)
        print("TIMETABLE DATA SUMMARY")
        print("="*60)
        print(f"Total Batch/Sections: {len(self.batch_sections)}")
        print(f"Total Teachers: {len(self.teachers)}")
        print(f"Total Courses: {len(self.courses)}")
        print(f"Total Sessions: {len(self.sessions)}")
        
        # Count lectures vs labs
        labs = sum(1 for s in self.sessions if s.is_lab)
        lectures = len(self.sessions) - labs
        print(f"  - Lectures: {lectures}")
        print(f"  - Labs (2-slot): {labs}")
        
        print("\nBatches:")
        for batch in sorted(self.batch_sections):
            batch_sessions = [s for s in self.sessions if s.batch_section == batch]
            print(f"  {batch}: {len(batch_sessions)} sessions")
        
        print("="*60 + "\n")


def parse_excel_or_csv(file_path: str) -> ParsedData:
    """
    Parse either Excel (.xlsx) or CSV file.
    
    Args:
        file_path: Path to input file
        
    Returns:
        ParsedData with all parsed entities
    """
    path = Path(file_path)
    
    if path.suffix.lower() in ['.xlsx', '.xls']:
        # Convert Excel to CSV first
        try:
            import pandas as pd
            df = pd.read_excel(file_path)
            csv_path = path.with_suffix('.csv')
            df.to_csv(csv_path, index=False)
            file_path = str(csv_path)
        except ImportError:
            raise ImportError("pandas and openpyxl required for Excel files. "
                            "Run: pip install pandas openpyxl")
    
    parser = TimetableDataParser()
    return parser.parse_csv(file_path)


if __name__ == "__main__":
    # Test parsing
    import sys
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = r"c:\Users\Fareed Bhatti\Downloads\all_batches_courses_teachers_spring2026.csv"
    
    parser = TimetableDataParser()
    data = parser.parse_csv(csv_file)
    parser.print_summary()
