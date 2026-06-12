"""
Timetable Generator API Module

Provides endpoints for:
- Uploading course offerings CSV (batch, course, teacher)
- Generating complete timetable using CP-SAT solver
- Storing results in MongoDB
- Exporting timetables to PDF
"""
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from io import BytesIO, StringIO
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from pymongo import MongoClient
from pymongo.database import Database

# Import timetable generator components
from timetable_generator.csv_parser import TimetableDataParser, ParsedData, ClassSession
from timetable_generator.cpsat_generator import (
    TimetableGenerator, GeneratorResult, SolverStatus, ScheduledSession, assign_rooms
)
from timetable_generator.clash_checker import ClashChecker, ClashReport

# Import room renderer for PDF generation
try:
    from renderer.pdf_renderer import TimetablePDFRenderer
    PDF_RENDERER_AVAILABLE = True
except ImportError:
    PDF_RENDERER_AVAILABLE = False


@dataclass
class GenerationSummary:
    """Summary of timetable generation"""
    success: bool
    status: str
    total_offerings: int
    total_scheduled: int
    total_batches: int
    total_teachers: int
    total_clashes: int
    generation_time_seconds: float
    missing_classes: List[str]
    errors: List[str]
    message: str


class TimetableGeneratorAPI:
    """
    API handler for timetable generation.
    
    Workflow:
    1. Admin uploads CSV with (Batch/Section, Course, Teacher)
    2. System stores offerings in timetable_offerings collection
    3. Admin triggers generation
    4. System runs CP-SAT solver
    5. System stores scheduled entries in timetable_entries
    6. System stores meta info in timetable_meta
    """
    
    # Collection names
    OFFERINGS_COLLECTION = "timetable_offerings"
    ENTRIES_COLLECTION = "timetable_entries"
    META_COLLECTION = "timetable_meta"
    ROOMS_COLLECTION = "timetable_rooms"
    
    def __init__(self, db: Database):
        """
        Initialize with MongoDB database.
        
        Args:
            db: pymongo Database instance
        """
        self.db = db
        self.offerings = db[self.OFFERINGS_COLLECTION]
        self.entries = db[self.ENTRIES_COLLECTION]
        self.meta = db[self.META_COLLECTION]
        self.rooms = db[self.ROOMS_COLLECTION]
        
        # Create indexes
        self._create_indexes()
    
    def _create_indexes(self):
        """Create necessary indexes for performance."""
        try:
            # Offerings indexes
            self.offerings.create_index("batch_section")
            self.offerings.create_index("teacher")
            self.offerings.create_index("course")
            
            # Entries indexes
            self.entries.create_index("batch_section")
            self.entries.create_index("teacher")
            self.entries.create_index([("day", 1), ("slotStart", 1)])
            
            # Rooms index
            self.rooms.create_index("room_code")
            
            print("[OK] Timetable indexes created")
        except Exception as e:
            print(f"[WARNING] Index creation failed: {e}")
    
    def get_all_rooms(self) -> Dict:
        """Get all configured rooms."""
        rooms = list(self.rooms.find({}, {'_id': 0}))
        lecture_rooms = [r for r in rooms if r.get('room_type') == 'LEC']
        lab_rooms = [r for r in rooms if r.get('room_type') == 'LAB']
        
        return {
            'success': True,
            'rooms': rooms,
            'lecture_rooms': lecture_rooms,
            'lab_rooms': lab_rooms,
            'total': len(rooms)
        }
    
    def add_room(self, room_code: str, room_type: str, capacity: int = 40) -> Dict:
        """Add a new room."""
        room_code = room_code.strip().upper()
        room_type = room_type.upper()
        
        if room_type not in ['LEC', 'LAB']:
            return {'success': False, 'message': 'Room type must be LEC or LAB'}
        
        # Check if room already exists
        if self.rooms.find_one({'room_code': room_code}):
            return {'success': False, 'message': f'Room {room_code} already exists'}
        
        self.rooms.insert_one({
            'room_code': room_code,
            'room_type': room_type,
            'capacity': capacity,
            'created_at': datetime.utcnow()
        })
        
        return {'success': True, 'message': f'Room {room_code} added', 'room_code': room_code}
    
    def delete_room(self, room_code: str) -> Dict:
        """Delete a room."""
        result = self.rooms.delete_one({'room_code': room_code.strip().upper()})
        if result.deleted_count > 0:
            return {'success': True, 'message': f'Room {room_code} deleted'}
        return {'success': False, 'message': f'Room {room_code} not found'}
    
    def clear_rooms(self) -> Dict:
        """Clear all rooms."""
        result = self.rooms.delete_many({})
        return {'success': True, 'deleted': result.deleted_count}
    
    def reset_to_default_rooms(self) -> Dict:
        """Reset rooms to defaults."""
        self.rooms.delete_many({})
        self._init_default_rooms()
        return self.get_all_rooms()

    def upload_rooms_csv(self, file_content: bytes, filename: str) -> Dict:
        """
        Upload rooms from CSV file.
        
        Expected CSV format:
        room_code,room_type,capacity
        CS-1,LEC,40
        Lab-1,LAB,30
        
        Or simpler format:
        room_code,room_type
        CS-1,lecture
        Lab-1,lab
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            
        Returns:
            Dict with upload results
        """
        try:
            # Parse CSV
            if filename.lower().endswith('.csv'):
                try:
                    df = pd.read_csv(BytesIO(file_content), encoding='utf-8')
                except UnicodeDecodeError:
                    df = pd.read_csv(BytesIO(file_content), encoding='latin-1')
            else:
                df = pd.read_excel(BytesIO(file_content))
            
            print(f"[UPLOAD ROOMS] Parsing file with {len(df)} rows")
            
            # Normalize column names
            df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
            
            # Map column names
            column_mapping = {
                'room_code': ['room_code', 'room', 'code', 'name', 'room_name', 'room_number', 'venue'],
                'room_type': ['room_type', 'type', 'category'],
                'capacity': ['capacity', 'seats', 'size']
            }
            
            actual_cols = {}
            for standard_name, variations in column_mapping.items():
                for col in df.columns:
                    if col in variations or any(v in col for v in variations):
                        actual_cols[standard_name] = col
                        break
            
            print(f"[UPLOAD ROOMS] Detected columns: {actual_cols}")
            
            # Must have at least room_code
            if 'room_code' not in actual_cols:
                return {
                    'success': False,
                    'message': f"Missing room_code column. Found columns: {list(df.columns)}"
                }
            
            # Clear existing rooms
            deleted = self.rooms.delete_many({})
            print(f"[UPLOAD ROOMS] Cleared {deleted.deleted_count} existing rooms")
            
            # Process rooms
            rooms_added = 0
            lecture_count = 0
            lab_count = 0
            errors = []
            
            for idx, row in df.iterrows():
                try:
                    room_code = str(row[actual_cols['room_code']]).strip().upper()
                    
                    if not room_code or room_code == 'NAN':
                        continue
                    
                    # Determine room type
                    if 'room_type' in actual_cols:
                        type_val = str(row[actual_cols['room_type']]).strip().upper()
                        if type_val in ['LAB', 'LABORATORY', 'LABS']:
                            room_type = 'LAB'
                        else:
                            room_type = 'LEC'
                    else:
                        # Auto-detect from room code
                        if 'LAB' in room_code.upper():
                            room_type = 'LAB'
                        else:
                            room_type = 'LEC'
                    
                    # Get capacity
                    capacity = 40
                    if 'capacity' in actual_cols:
                        try:
                            capacity = int(row[actual_cols['capacity']])
                        except:
                            capacity = 30 if room_type == 'LAB' else 40
                    
                    self.rooms.insert_one({
                        'room_code': room_code,
                        'room_type': room_type,
                        'capacity': capacity,
                        'created_at': datetime.utcnow()
                    })
                    
                    rooms_added += 1
                    if room_type == 'LAB':
                        lab_count += 1
                    else:
                        lecture_count += 1
                        
                except Exception as e:
                    errors.append(f"Row {idx + 2}: {str(e)}")
            
            print(f"[UPLOAD ROOMS] Added {rooms_added} rooms ({lecture_count} lecture, {lab_count} lab)")
            
            return {
                'success': True,
                'message': f"Added {rooms_added} rooms",
                'rooms_added': rooms_added,
                'lecture_rooms': lecture_count,
                'lab_rooms': lab_count,
                'errors': errors[:10] if errors else []
            }
            
        except Exception as e:
            print(f"[ERROR] Room upload failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': str(e)
            }

    def normalize_batch_code(self, batch: str) -> str:
        """Normalize batch code to standard format."""
        if not batch:
            return ""
        # Uppercase, remove extra spaces, convert spaces to hyphens
        normalized = batch.strip().upper()
        normalized = "-".join(normalized.split())
        return normalized
    
    def detect_session_type(self, course_name: str) -> Tuple[str, int]:
        """
        Detect if course is a lab based on name.
        
        Returns:
            Tuple of (type: "LEC"|"LAB", slot_duration: 1|2)
        """
        course_lower = course_name.lower()
        lab_keywords = ['lab', 'practical', 'workshop', 'laboratory']
        
        for keyword in lab_keywords:
            if keyword in course_lower:
                return ("LAB", 2)
        
        return ("LEC", 1)
    
    def upload_offerings_csv(self, file_content: bytes, filename: str) -> Dict:
        """
        Upload and parse offerings CSV.
        
        Expected CSV format:
        Batch/Section,Course,Teacher
        FA22-BCS-8A,Artificial Intelligence,Dr Ahmed
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            
        Returns:
            Dict with upload results
        """
        try:
            # Parse CSV
            if filename.lower().endswith('.csv'):
                try:
                    df = pd.read_csv(BytesIO(file_content), encoding='utf-8')
                except UnicodeDecodeError:
                    df = pd.read_csv(BytesIO(file_content), encoding='latin-1')
            else:
                df = pd.read_excel(BytesIO(file_content))
            
            print(f"[UPLOAD] Parsing file with {len(df)} rows")
            
            # Normalize column names
            df.columns = df.columns.str.strip().str.lower().str.replace('/', '_').str.replace(' ', '_')
            
            # Map common column name variations
            column_mapping = {
                'batch_section': ['batch_section', 'batch', 'section', 'batch/section'],
                'course': ['course', 'course_name', 'subject', 'course_title'],
                'teacher': ['teacher', 'teacher_name', 'instructor', 'faculty'],
            }
            
            # Optional columns
            optional_cols = {
                'credit_hours': ['credit_hours', 'credits', 'hours', 'credit'],
                'type': ['type', 'session_type', 'class_type'],
            }
            
            # Find actual column names
            actual_cols = {}
            for standard_name, variations in column_mapping.items():
                for col in df.columns:
                    if col in variations or any(v in col for v in variations):
                        actual_cols[standard_name] = col
                        break
            
            # Find optional columns
            for standard_name, variations in optional_cols.items():
                for col in df.columns:
                    if col in variations or any(v in col for v in variations):
                        actual_cols[standard_name] = col
                        break
            
            print(f"[UPLOAD] Detected columns: {actual_cols}")
            
            # Validate required columns
            missing_cols = [k for k in column_mapping.keys() if k not in actual_cols]
            if missing_cols:
                return {
                    'success': False,
                    'error': f"Missing required columns: {missing_cols}. Found: {list(df.columns)}"
                }
            
            # Clear existing offerings
            deleted = self.offerings.delete_many({})
            print(f"[UPLOAD] Cleared {deleted.deleted_count} existing offerings")
            
            # Process and store offerings
            offerings_added = 0
            errors = []
            unique_batches = set()
            unique_teachers = set()
            
            for idx, row in df.iterrows():
                try:
                    batch = self.normalize_batch_code(str(row[actual_cols['batch_section']]))
                    course = str(row[actual_cols['course']]).strip()
                    teacher = str(row[actual_cols['teacher']]).strip()
                    
                    if not batch or not course or batch == 'NAN' or course.upper() == 'NAN':
                        continue
                    
                    # Detect session type (auto-detect from course name)
                    session_type, slot_duration = self.detect_session_type(course)
                    
                    # Override type if explicitly specified in CSV
                    if 'type' in actual_cols:
                        type_val = str(row[actual_cols['type']]).strip().upper()
                        if type_val in ['LAB', 'LABORATORY']:
                            session_type = 'LAB'
                            slot_duration = 2
                    
                    # Get credit hours (default: 3 for lecture, 1 for lab)
                    credit_hours = 3 if session_type == 'LEC' else 1
                    if 'credit_hours' in actual_cols:
                        try:
                            credit_hours = int(row[actual_cols['credit_hours']])
                        except:
                            pass
                    
                    offering = {
                        'batch_section': batch,
                        'course': course,
                        'teacher': teacher,
                        'type': session_type,
                        'slot_duration': slot_duration,
                        'credit_hours': credit_hours,
                        'uploaded_at': datetime.utcnow()
                    }
                    
                    self.offerings.insert_one(offering)
                    offerings_added += 1
                    unique_batches.add(batch)
                    unique_teachers.add(teacher)
                    
                except Exception as e:
                    errors.append(f"Row {idx + 2}: {str(e)}")
            
            print(f"[UPLOAD] Added {offerings_added} offerings")
            
            return {
                'success': True,
                'offerings_added': offerings_added,
                'total_batches': len(unique_batches),
                'total_teachers': len(unique_teachers),
                'batches': sorted(list(unique_batches)),
                'errors': errors[:10] if errors else []
            }
            
        except Exception as e:
            print(f"[ERROR] Upload failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    def generate_timetable(self, time_limit_seconds: float = 300.0) -> GenerationSummary:
        """
        Generate complete timetable from offerings using CP-SAT solver.
        
        Args:
            time_limit_seconds: Maximum solver time (default 5 minutes)
            
        Returns:
            GenerationSummary with results
        """
        start_time = time.perf_counter()
        
        try:
            # Check for rooms first
            rooms_data = self.get_all_rooms()
            lecture_rooms = [r['room_code'] for r in rooms_data.get('lecture_rooms', [])]
            lab_rooms = [r['room_code'] for r in rooms_data.get('lab_rooms', [])]
            
            if not lecture_rooms and not lab_rooms:
                return GenerationSummary(
                    success=False,
                    status="NO_ROOMS",
                    total_offerings=0,
                    total_scheduled=0,
                    total_batches=0,
                    total_teachers=0,
                    total_clashes=0,
                    generation_time_seconds=0,
                    missing_classes=[],
                    errors=["No rooms configured. Please upload rooms CSV first (Step 1)."],
                    message="No rooms to assign"
                )
            
            # Get all offerings
            offerings = list(self.offerings.find({}))
            if not offerings:
                return GenerationSummary(
                    success=False,
                    status="NO_OFFERINGS",
                    total_offerings=0,
                    total_scheduled=0,
                    total_batches=0,
                    total_teachers=0,
                    total_clashes=0,
                    generation_time_seconds=0,
                    missing_classes=[],
                    errors=["No offerings found. Please upload course offerings CSV (Step 2)."],
                    message="No offerings to schedule"
                )
            
            print(f"[GENERATE] Found {len(offerings)} offerings to schedule")
            print(f"[GENERATE] Using {len(lecture_rooms)} lecture rooms, {len(lab_rooms)} lab rooms")
            
            # Detect if CSV has one row per course or one row per class meeting
            # by checking for duplicate batch+course combinations
            from collections import Counter
            batch_course_counts = Counter(
                (off['batch_section'], off['course']) for off in offerings
            )
            has_duplicates = any(count > 1 for count in batch_course_counts.values())
            
            if has_duplicates:
                print("[GENERATE] CSV has multiple rows per course - treating each row as one session")
                expand_lectures = False
            else:
                print("[GENERATE] CSV has one row per course - expanding to weekly sessions")
                expand_lectures = True
            
            # Convert offerings to ClassSession format for solver
            sessions = []
            session_counter = 0
            
            for off in offerings:
                is_lab = (off.get('type', 'LEC') == 'LAB')
                
                if is_lab:
                    # Labs: 1 session per week, 2 consecutive slots
                    session = ClassSession(
                        session_id=f"session_{session_counter}",
                        batch_section=off['batch_section'],
                        course_name=off['course'],
                        teacher_name=off['teacher'],
                        teacher_dept=off.get('department', 'CS'),
                        is_lab=True,
                        slot_duration=2
                    )
                    sessions.append(session)
                    session_counter += 1
                else:
                    # Lectures: expand based on detection
                    if expand_lectures:
                        # Each course = 3 sessions/week (for 3 credit hours)
                        credit_hours = off.get('credit_hours', 3)
                        for lec_num in range(credit_hours):
                            session = ClassSession(
                                session_id=f"session_{session_counter}",
                                batch_section=off['batch_section'],
                                course_name=off['course'],
                                teacher_name=off['teacher'],
                                teacher_dept=off.get('department', 'CS'),
                                is_lab=False,
                                slot_duration=1
                            )
                            sessions.append(session)
                            session_counter += 1
                    else:
                        # Each row = 1 session
                        session = ClassSession(
                            session_id=f"session_{session_counter}",
                            batch_section=off['batch_section'],
                            course_name=off['course'],
                            teacher_name=off['teacher'],
                            teacher_dept=off.get('department', 'CS'),
                            is_lab=False,
                            slot_duration=1
                        )
                        sessions.append(session)
                        session_counter += 1
            
            print(f"[GENERATE] Created {len(sessions)} sessions to schedule")
            
            # Create ParsedData
            parsed_data = ParsedData(sessions=sessions)
            
            # Run generator
            print(f"[GENERATE] Running CP-SAT solver (time limit: {time_limit_seconds}s)...")
            generator = TimetableGenerator(time_limit_seconds=time_limit_seconds)
            result: GeneratorResult = generator.generate(parsed_data)
            
            if result.status == SolverStatus.INFEASIBLE:
                return GenerationSummary(
                    success=False,
                    status="INFEASIBLE",
                    total_offerings=len(offerings),
                    total_scheduled=0,
                    total_batches=len(set(o['batch_section'] for o in offerings)),
                    total_teachers=len(set(o['teacher'] for o in offerings)),
                    total_clashes=0,
                    generation_time_seconds=time.perf_counter() - start_time,
                    missing_classes=[],
                    errors=result.conflicts if result.conflicts else ["No valid schedule exists"],
                    message="Cannot create clash-free timetable. Check for conflicts."
                )
            
            if result.status == SolverStatus.TIMEOUT:
                return GenerationSummary(
                    success=False,
                    status="TIMEOUT",
                    total_offerings=len(offerings),
                    total_scheduled=result.total_scheduled,
                    total_batches=len(set(o['batch_section'] for o in offerings)),
                    total_teachers=len(set(o['teacher'] for o in offerings)),
                    total_clashes=0,
                    generation_time_seconds=time.perf_counter() - start_time,
                    missing_classes=[],
                    errors=["Solver timed out. Try increasing time limit."],
                    message="Solver timed out"
                )
            
            # Assign rooms from database (rooms were already validated at start)
            print("[GENERATE] Assigning rooms...")
            rooms_data = self.get_all_rooms()
            lecture_rooms = [r['room_code'] for r in rooms_data.get('lecture_rooms', [])]
            lab_rooms = [r['room_code'] for r in rooms_data.get('lab_rooms', [])]
            
            result.scheduled_sessions = assign_rooms(
                result.scheduled_sessions,
                lecture_rooms,
                lab_rooms
            )
            
            # Verify no clashes
            print("[GENERATE] Verifying schedule...")
            checker = ClashChecker()
            report: ClashReport = checker.check(result.scheduled_sessions)
            
            # Check for missing classes
            scheduled_ids = set(s.session.session_id for s in result.scheduled_sessions)
            missing = [
                f"{sessions[i].batch_section}: {sessions[i].course_name}"
                for i, s in enumerate(sessions)
                if s.session_id not in scheduled_ids
            ]
            
            if missing:
                print(f"[WARNING] {len(missing)} classes could not be scheduled")
            
            # ALWAYS store successfully scheduled entries to database
            # even if some classes couldn't be scheduled
            print("[GENERATE] Storing schedule in MongoDB...")
            self.entries.delete_many({})
            
            entries_to_insert = []
            for scheduled in result.scheduled_sessions:
                entry = {
                    'batch_section': scheduled.session.batch_section,
                    'course': scheduled.session.course_name,
                    'teacher': scheduled.session.teacher_name,
                    'day': scheduled.day_idx,
                    'slotStart': scheduled.slot_start,
                    'slotSpan': scheduled.slot_span,
                    'room': scheduled.room_code,
                    'type': 'LAB' if scheduled.is_lab else 'LEC',
                    'created_at': datetime.utcnow()
                }
                entries_to_insert.append(entry)
            
            if entries_to_insert:
                self.entries.insert_many(entries_to_insert)
            
            # Store meta info
            self.meta.delete_many({})
            self.meta.insert_one({
                'generated_at': datetime.utcnow(),
                'total_batches': len(result.schedule_by_batch),
                'total_classes': len(result.scheduled_sessions),
                'total_teachers': len(set(o['teacher'] for o in offerings)),
                'solver_status': result.status.value,
                'solving_time_seconds': result.solving_time_seconds,
                'total_gaps': result.total_gaps,
                'total_late_slots': result.total_late_slots,
                'total_clashes': report.total_clashes
            })
            
            generation_time = time.perf_counter() - start_time
            print(f"[GENERATE] Complete! {len(entries_to_insert)} entries stored in {generation_time:.2f}s")
            
            # Determine status and message based on missing classes
            if missing:
                status_msg = "PARTIAL"
                message = f"Scheduled {len(result.scheduled_sessions)} classes for {len(result.schedule_by_batch)} batches. WARNING: {len(missing)} classes could not be scheduled."
                errors = [f"Missing {len(missing)} classes - may need more rooms or time slots"]
            else:
                status_msg = result.status.value.upper()
                message = f"Successfully scheduled {len(result.scheduled_sessions)} classes for {len(result.schedule_by_batch)} batches"
                errors = []
            
            return GenerationSummary(
                success=True,  # Treat as success even with partial - entries are stored
                status=status_msg,
                total_offerings=len(offerings),
                total_scheduled=len(result.scheduled_sessions),
                total_batches=len(result.schedule_by_batch),
                total_teachers=len(set(o['teacher'] for o in offerings)),
                total_clashes=report.total_clashes,
                generation_time_seconds=generation_time,
                missing_classes=missing[:50] if missing else [],  # Limit to first 50
                errors=errors,
                message=message
            )
            
        except Exception as e:
            print(f"[ERROR] Generation failed: {e}")
            import traceback
            traceback.print_exc()
            return GenerationSummary(
                success=False,
                status="ERROR",
                total_offerings=0,
                total_scheduled=0,
                total_batches=0,
                total_teachers=0,
                total_clashes=0,
                generation_time_seconds=time.perf_counter() - start_time,
                missing_classes=[],
                errors=[str(e)],
                message=f"Generation failed: {str(e)}"
            )
    
    def get_batch_timetable(self, batch_code: str) -> Dict:
        """
        Get timetable for a specific batch.
        
        Args:
            batch_code: Batch code (e.g., FA22-BCS-8A)
            
        Returns:
            Dict with batch timetable
        """
        batch = self.normalize_batch_code(batch_code)
        entries = list(self.entries.find({'batch_section': batch}))
        
        if not entries:
            return {
                'success': False,
                'batch': batch,
                'batch_section': batch,
                'entries': [],
                'message': 'No entries found for this batch'
            }
        
        # Format entries
        formatted = []
        for e in entries:
            formatted.append({
                'day': e['day'],
                'slotStart': e['slotStart'],
                'slotSpan': e.get('slotSpan', 1),
                'course': e['course'],
                'teacher': e['teacher'],
                'room': e.get('room', ''),
                'type': e.get('type', 'LEC')
            })
        
        return {
            'success': True,
            'batch': batch,
            'batch_section': batch,  # For PDF renderer compatibility
            'entries': formatted,
            'total_classes': len(formatted)
        }
    
    def get_all_batches(self) -> Dict:
        """Get list of all batches with scheduled entries."""
        batches = self.entries.distinct('batch_section')
        return {
            'success': True,
            'batches': sorted(batches),
            'count': len(batches)
        }
    
    def get_generation_meta(self) -> Dict:
        """Get metadata about last generation."""
        meta = self.meta.find_one({})
        if not meta:
            return {'success': True, 'meta': None, 'generated': False}
        
        meta['_id'] = str(meta['_id'])
        return {'success': True, 'meta': meta, 'generated': True}
    
    def get_all_offerings(self) -> List[Dict]:
        """Get all current offerings."""
        offerings = list(self.offerings.find({}))
        for o in offerings:
            o['_id'] = str(o['_id'])
        return offerings
    
    def get_all_timetables_for_export(self) -> List[Dict]:
        """Get all batch timetables formatted for PDF export."""
        batches_result = self.get_all_batches()
        batches = batches_result.get('batches', [])
        all_data = []
        
        for batch in batches:
            result = self.get_batch_timetable(batch)
            if result.get('success') and result.get('entries'):
                all_data.append({
                    'batch_section': result['batch_section'],
                    'entries': result['entries']
                })
        
        return all_data

    def clear_all_data(self) -> Dict:
        """Clear all timetable data (offerings and entries)."""
        off_deleted = self.offerings.delete_many({})
        ent_deleted = self.entries.delete_many({})
        meta_deleted = self.meta.delete_many({})
        
        return {
            'offerings_deleted': off_deleted.deleted_count,
            'entries_deleted': ent_deleted.deleted_count,
            'meta_deleted': meta_deleted.deleted_count
        }


# Singleton instance
_generator_api: Optional[TimetableGeneratorAPI] = None


def get_generator_api(db: Database) -> TimetableGeneratorAPI:
    """Get or create singleton TimetableGeneratorAPI instance."""
    global _generator_api
    if _generator_api is None:
        _generator_api = TimetableGeneratorAPI(db)
    return _generator_api
