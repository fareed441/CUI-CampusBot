"""
Clash Checker for Timetable Validation

Verifies that a generated timetable has:
- No teacher clashes (same teacher, same day+slot)
- No batch clashes (same batch, same day+slot)
- No room clashes (same room, same day+slot)
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple
import sys

sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

from timetable_generator.cpsat_generator import ScheduledSession


@dataclass
class ClashReport:
    """Report of all clashes found"""
    teacher_clashes: List[Dict] = field(default_factory=list)
    batch_clashes: List[Dict] = field(default_factory=list)
    room_clashes: List[Dict] = field(default_factory=list)
    
    @property
    def is_clash_free(self) -> bool:
        return (len(self.teacher_clashes) == 0 and 
                len(self.batch_clashes) == 0 and 
                len(self.room_clashes) == 0)
    
    @property
    def total_clashes(self) -> int:
        return (len(self.teacher_clashes) + 
                len(self.batch_clashes) + 
                len(self.room_clashes))
    
    def print_report(self):
        """Print a formatted clash report"""
        print("\n" + "="*60)
        print("CLASH VERIFICATION REPORT")
        print("="*60)
        
        if self.is_clash_free:
            print("✅ TIMETABLE IS CLASH-FREE!")
            print("  - No teacher clashes")
            print("  - No batch clashes")
            print("  - No room clashes")
        else:
            print(f"❌ FOUND {self.total_clashes} CLASHES")
            
            if self.teacher_clashes:
                print(f"\nTeacher Clashes ({len(self.teacher_clashes)}):")
                for clash in self.teacher_clashes[:10]:  # Show first 10
                    print(f"  - {clash['teacher']}: {clash['day']} Slot {clash['slot']}")
                    for s in clash['sessions']:
                        print(f"      * {s['batch']}: {s['course']}")
                if len(self.teacher_clashes) > 10:
                    print(f"  ... and {len(self.teacher_clashes) - 10} more")
            
            if self.batch_clashes:
                print(f"\nBatch Clashes ({len(self.batch_clashes)}):")
                for clash in self.batch_clashes[:10]:
                    print(f"  - {clash['batch']}: {clash['day']} Slot {clash['slot']}")
                    for s in clash['sessions']:
                        print(f"      * {s['course']} ({s['teacher']})")
                if len(self.batch_clashes) > 10:
                    print(f"  ... and {len(self.batch_clashes) - 10} more")
            
            if self.room_clashes:
                print(f"\nRoom Clashes ({len(self.room_clashes)}):")
                for clash in self.room_clashes[:10]:
                    print(f"  - {clash['room']}: {clash['day']} Slot {clash['slot']}")
                    for s in clash['sessions']:
                        print(f"      * {s['batch']}: {s['course']}")
                if len(self.room_clashes) > 10:
                    print(f"  ... and {len(self.room_clashes) - 10} more")
        
        print("="*60 + "\n")


class ClashChecker:
    """Checks scheduled sessions for clashes"""
    
    DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    def check(self, scheduled_sessions: List[ScheduledSession]) -> ClashReport:
        """
        Check all scheduled sessions for clashes.
        
        Args:
            scheduled_sessions: List of scheduled sessions
            
        Returns:
            ClashReport with all found clashes
        """
        report = ClashReport()
        
        # Group sessions by (day, slot)
        sessions_at_slot: Dict[Tuple[int, int], List[ScheduledSession]] = defaultdict(list)
        
        for session in scheduled_sessions:
            # A session occupies all slots from slot_start to slot_end
            for slot in range(session.slot_start, session.slot_end + 1):
                key = (session.day_idx, slot)
                sessions_at_slot[key].append(session)
        
        # Check each slot
        for (day_idx, slot), sessions in sessions_at_slot.items():
            day_name = self.DAY_NAMES[day_idx]
            
            # Check teacher clashes
            teacher_sessions: Dict[str, List[ScheduledSession]] = defaultdict(list)
            for s in sessions:
                teacher_sessions[s.session.teacher_name].append(s)
            
            for teacher, t_sessions in teacher_sessions.items():
                if len(t_sessions) > 1:
                    report.teacher_clashes.append({
                        'teacher': teacher,
                        'day': day_name,
                        'day_idx': day_idx,
                        'slot': slot,
                        'sessions': [{
                            'batch': s.session.batch_section,
                            'course': s.session.course_name,
                        } for s in t_sessions]
                    })
            
            # Check batch clashes
            batch_sessions: Dict[str, List[ScheduledSession]] = defaultdict(list)
            for s in sessions:
                batch_sessions[s.session.batch_section].append(s)
            
            for batch, b_sessions in batch_sessions.items():
                if len(b_sessions) > 1:
                    report.batch_clashes.append({
                        'batch': batch,
                        'day': day_name,
                        'day_idx': day_idx,
                        'slot': slot,
                        'sessions': [{
                            'course': s.session.course_name,
                            'teacher': s.session.teacher_name,
                        } for s in b_sessions]
                    })
            
            # Check room clashes
            room_sessions: Dict[str, List[ScheduledSession]] = defaultdict(list)
            for s in sessions:
                if s.room_code and s.room_code != "TBA":
                    room_sessions[s.room_code].append(s)
            
            for room, r_sessions in room_sessions.items():
                if len(r_sessions) > 1:
                    report.room_clashes.append({
                        'room': room,
                        'day': day_name,
                        'day_idx': day_idx,
                        'slot': slot,
                        'sessions': [{
                            'batch': s.session.batch_section,
                            'course': s.session.course_name,
                        } for s in r_sessions]
                    })
        
        return report


def verify_timetable(scheduled_sessions: List[ScheduledSession]) -> bool:
    """
    Quick verification that returns True if timetable is clash-free.
    
    Args:
        scheduled_sessions: List of scheduled sessions
        
    Returns:
        True if no clashes found
    """
    checker = ClashChecker()
    report = checker.check(scheduled_sessions)
    return report.is_clash_free
