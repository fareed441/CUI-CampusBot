"""
HTML Renderer for Timetables - Exact CUI Format

Renders timetables as HTML matching the PDF format:
- Header: "COMSATS Vehari Centralized Timetable (V-2)-Spring-2026"
- Big centered batch title
- Table with merged cells for labs
- Rotated day labels
- Break column between slot 3 and 4
"""
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import html

import sys
sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

from timetable_core.models import (
    Offering, Day, Meeting, TIMESLOTS, DAYS,
    DAY_FULL_NAMES, OfferingType
)


# CSS styles matching PDF format
TIMETABLE_CSS = """
<style>
    .timetable-container {
        font-family: Arial, sans-serif;
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }
    
    .timetable-header {
        text-align: center;
        margin-bottom: 10px;
    }
    
    .timetable-title {
        font-size: 16px;
        text-decoration: underline;
        color: #333;
        margin-bottom: 5px;
    }
    
    .batch-title {
        font-size: 24px;
        font-weight: bold;
        color: #000;
        margin: 15px 0;
    }
    
    .timetable {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
    }
    
    .timetable th,
    .timetable td {
        border: 1px solid #666;
        padding: 5px;
        vertical-align: middle;
        text-align: center;
    }
    
    .timetable th {
        background-color: #2c5282;
        color: white;
        font-size: 11px;
        font-weight: bold;
        height: 50px;
    }
    
    .timetable th.day-header {
        background-color: #d4d4d4;
        color: #333;
        width: 60px;
        font-size: 10px;
    }
    
    .timetable th.slot-header {
        width: 14%;
    }
    
    .timetable th.break-header {
        background-color: #e8e8e8;
        color: #333;
        width: 70px;
    }
    
    .day-cell {
        background-color: #d4d4d4;
        font-weight: bold;
        font-size: 11px;
        writing-mode: vertical-rl;
        text-orientation: mixed;
        transform: rotate(180deg);
        height: 80px;
    }
    
    .slot-cell {
        height: 80px;
        font-size: 10px;
        background-color: #f8f9ff;
    }
    
    .slot-cell.lab {
        background-color: #fff8f0;
    }
    
    .slot-cell.merged {
        background-color: #f0f8ff;
    }
    
    .break-cell {
        background-color: #e8e8e8;
        font-weight: bold;
        color: #666;
        writing-mode: vertical-rl;
        text-orientation: mixed;
        transform: rotate(180deg);
    }
    
    .course-name {
        font-weight: bold;
        font-size: 11px;
        color: #333;
        margin-bottom: 2px;
    }
    
    .room-code {
        font-size: 10px;
        color: #555;
        margin-bottom: 2px;
    }
    
    .teacher-name {
        font-size: 9px;
        color: #666;
    }
    
    .empty-cell {
        background-color: #fafafa;
    }
    
    .timetable-footer {
        display: flex;
        justify-content: space-between;
        margin-top: 15px;
        font-size: 10px;
        color: #666;
    }
    
    .slot-time {
        font-size: 9px;
        font-weight: normal;
        display: block;
        margin-top: 3px;
    }
    
    @media print {
        .timetable-container {
            padding: 0;
        }
        
        .timetable th,
        .timetable td {
            font-size: 9px;
        }
        
        .day-cell,
        .slot-cell {
            height: 60px;
        }
    }
</style>
"""


class TimetableHTMLRenderer:
    """
    Renders batch timetables as HTML matching the PDF format.
    """
    
    SLOT_HEADERS = [
        ('Slot 1', '8:30-10:00 AM'),
        ('Slot 2', '10:00-11:30 AM'),
        ('Slot 3', '11:30-1:00 PM'),
        ('Break', '1:00-1:30 PM'),
        ('Slot 4', '1:30-3:00 PM'),
        ('Slot 5', '3:00-4:30 PM'),
        ('Slot 6', '4:30-6:00 PM'),
    ]
    
    def __init__(self):
        pass
    
    def _build_schedule_grid(
        self,
        offerings: List[Offering]
    ) -> Dict[Tuple[int, int], Dict]:
        """Build a grid of cell contents from offerings."""
        grid = {}
        
        for offering in offerings:
            for meeting in offering.meetings:
                day_idx = meeting.day.value
                
                cell_data = {
                    'course_name': offering.course.course_name,
                    'room': offering.room.room_code,
                    'teacher': offering.teacher.name,
                    'dept': offering.teacher.department,
                    'is_lab': offering.offering_type == OfferingType.LAB,
                    'span': meeting.duration_slots,
                    'slot_start': meeting.slot_start,
                    'slot_end': meeting.slot_end,
                }
                
                key = (day_idx, meeting.slot_start)
                grid[key] = cell_data
        
        return grid
    
    def _format_cell_html(self, cell_data: Dict) -> str:
        """Format cell content as HTML."""
        course = html.escape(cell_data['course_name'])
        room = html.escape(cell_data['room'])
        teacher = html.escape(cell_data['teacher'])
        dept = html.escape(cell_data.get('dept', ''))
        
        teacher_line = f"{teacher} ({dept})" if dept else teacher
        
        return f"""
            <div class="course-name">{course}</div>
            <div class="room-code">{room}</div>
            <div class="teacher-name">{teacher_line}</div>
        """
    
    def render(
        self,
        batch_section: str,
        offerings: List[Offering],
        semester: str = "Spring-2026",
        standalone: bool = True,
    ) -> str:
        """
        Render timetable for a batch section as HTML.
        
        Args:
            batch_section: Batch identifier
            offerings: List of offerings for this batch
            semester: Semester label
            standalone: Include full HTML document wrapper
        
        Returns:
            HTML string
        """
        grid = self._build_schedule_grid(offerings)
        
        # Build table rows
        rows_html = []
        
        # Header row
        header_cells = ['<th class="day-header"></th>']  # Empty corner cell
        
        for i, (slot_name, slot_time) in enumerate(self.SLOT_HEADERS):
            if 'Break' in slot_name:
                header_cells.append(f'''
                    <th class="break-header">
                        {slot_name}<br/>
                        <span class="slot-time">2Hrs Class</span><br/>
                        <span class="slot-time">{slot_time}</span>
                    </th>
                ''')
            else:
                header_cells.append(f'''
                    <th class="slot-header">
                        {slot_name}<br/>
                        <span class="slot-time">{slot_time}</span>
                    </th>
                ''')
        
        rows_html.append(f'<tr>{"".join(header_cells)}</tr>')
        
        # Day rows
        for day_idx, day in enumerate(DAYS):
            row_cells = [f'<td class="day-cell">{DAY_FULL_NAMES[day]}</td>']
            
            # Track covered slots (for colspan)
            skip_slots = set()
            
            # Process slots 1-3, then break, then 4-6
            for slot in range(1, 7):
                # Insert break column after slot 3
                if slot == 4:
                    if day_idx == 0:
                        # Only first row gets the rowspan
                        row_cells.append(
                            '<td class="break-cell" rowspan="5">Break</td>'
                        )
                    # Other rows don't add break cell (covered by rowspan)
                
                if slot in skip_slots:
                    continue
                
                key = (day_idx, slot)
                if key in grid:
                    cell_data = grid[key]
                    span = cell_data['span']
                    is_lab = cell_data['is_lab']
                    
                    cell_class = 'slot-cell'
                    if is_lab:
                        cell_class += ' lab'
                    if span > 1:
                        cell_class += ' merged'
                    
                    content = self._format_cell_html(cell_data)
                    
                    if span > 1:
                        # Mark subsequent slots as covered
                        for s in range(slot + 1, slot + span):
                            skip_slots.add(s)
                        row_cells.append(
                            f'<td class="{cell_class}" colspan="{span}">{content}</td>'
                        )
                    else:
                        row_cells.append(f'<td class="{cell_class}">{content}</td>')
                else:
                    row_cells.append('<td class="slot-cell empty-cell"></td>')
            
            rows_html.append(f'<tr>{"".join(row_cells)}</tr>')
        
        # Build full table
        table_html = f'''
            <table class="timetable">
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        '''
        
        # Footer
        footer_date = datetime.now().strftime("%Y-%m-%d")
        footer_html = f'''
            <div class="timetable-footer">
                <span>COMSATS Centralized Timetable-{footer_date}</span>
                <span>aSc Timetables</span>
            </div>
        '''
        
        # Complete content
        content_html = f'''
            <div class="timetable-container">
                <div class="timetable-header">
                    <div class="timetable-title">
                        COMSATS Vehari Centralized Timetable (V-2)-{semester}
                    </div>
                    <div class="batch-title">{html.escape(batch_section)}</div>
                </div>
                {table_html}
                {footer_html}
            </div>
        '''
        
        if standalone:
            return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Timetable - {html.escape(batch_section)}</title>
    {TIMETABLE_CSS}
</head>
<body>
    {content_html}
</body>
</html>
            '''
        else:
            return TIMETABLE_CSS + content_html
    
    def render_student_schedule(
        self,
        student_name: str,
        offerings: List[Offering],
        semester: str = "Spring-2026",
        standalone: bool = True,
    ) -> str:
        """
        Render a student's personal schedule.
        
        Similar to batch timetable but titled with student name/ID.
        """
        # Reuse the batch rendering logic with student as "batch"
        return self.render(
            batch_section=f"Schedule - {student_name}",
            offerings=offerings,
            semester=semester,
            standalone=standalone
        )
    
    def _build_schedule_grid_from_entries(
        self,
        entries: List[Dict]
    ) -> Dict[Tuple[int, int], Dict]:
        """Build a grid of cell contents from MongoDB-style entry dicts."""
        grid = {}
        
        for entry in entries:
            day_idx = entry.get('day', 0)
            slot_start = entry.get('slotStart', 1)
            slot_span = entry.get('slotSpan', 1)
            
            cell_data = {
                'course_name': entry.get('course', ''),
                'room': entry.get('room', ''),
                'teacher': entry.get('teacher', ''),
                'dept': '',
                'is_lab': entry.get('type', 'LEC') == 'LAB',
                'span': slot_span,
                'slot_start': slot_start,
                'slot_end': slot_start + slot_span - 1,
            }
            
            key = (day_idx, slot_start)
            grid[key] = cell_data
        
        return grid
    
    def render_from_entries(
        self,
        batch_section: str,
        entries: List[Dict],
        semester: str = "Spring-2026",
        standalone: bool = True,
    ) -> str:
        """
        Render timetable from MongoDB-style entry dicts.
        
        Args:
            batch_section: Batch identifier
            entries: List of entry dicts with day, slotStart, slotSpan, course, teacher, room, type
            semester: Semester label
            standalone: Include full HTML document wrapper
        
        Returns:
            HTML string
        """
        grid = self._build_schedule_grid_from_entries(entries)
        
        # Build table rows
        rows_html = []
        
        # Header row
        header_cells = ['<th class="day-header"></th>']
        
        for i, (slot_name, slot_time) in enumerate(self.SLOT_HEADERS):
            if 'Break' in slot_name:
                header_cells.append(f'''
                    <th class="break-header">
                        {slot_name}<br/>
                        <span class="slot-time">2Hrs Class</span><br/>
                        <span class="slot-time">{slot_time}</span>
                    </th>
                ''')
            else:
                header_cells.append(f'''
                    <th class="slot-header">
                        {slot_name}<br/>
                        <span class="slot-time">{slot_time}</span>
                    </th>
                ''')
        
        rows_html.append(f'<tr>{"".join(header_cells)}</tr>')
        
        # Day rows
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        for day_idx, day_name in enumerate(day_names):
            row_cells = [f'<td class="day-cell">{day_name}</td>']
            
            skip_slots = set()
            
            for slot in range(1, 7):
                if slot == 4:
                    if day_idx == 0:
                        row_cells.append(
                            '<td class="break-cell" rowspan="5">Break</td>'
                        )
                
                if slot in skip_slots:
                    continue
                
                key = (day_idx, slot)
                if key in grid:
                    cell_data = grid[key]
                    span = cell_data['span']
                    is_lab = cell_data['is_lab']
                    
                    cell_class = 'slot-cell'
                    if is_lab:
                        cell_class += ' lab'
                    if span > 1:
                        cell_class += ' merged'
                    
                    content = self._format_cell_html(cell_data)
                    
                    if span > 1:
                        for s in range(slot + 1, slot + span):
                            skip_slots.add(s)
                        row_cells.append(
                            f'<td class="{cell_class}" colspan="{span}">{content}</td>'
                        )
                    else:
                        row_cells.append(f'<td class="{cell_class}">{content}</td>')
                else:
                    row_cells.append('<td class="slot-cell empty-cell"></td>')
            
            rows_html.append(f'<tr>{"".join(row_cells)}</tr>')
        
        table_html = f'''
            <table class="timetable">
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        '''
        
        footer_date = datetime.now().strftime("%Y-%m-%d")
        footer_html = f'''
            <div class="timetable-footer">
                <span>COMSATS Centralized Timetable-{footer_date}</span>
                <span>aSc Timetables</span>
            </div>
        '''
        
        content_html = f'''
            <div class="timetable-container">
                <div class="timetable-header">
                    <div class="timetable-title">
                        COMSATS Vehari Centralized Timetable (V-2)-{semester}
                    </div>
                    <div class="batch-title">{html.escape(batch_section)}</div>
                </div>
                {table_html}
                {footer_html}
            </div>
        '''
        
        if standalone:
            return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Timetable - {html.escape(batch_section)}</title>
    {TIMETABLE_CSS}
</head>
<body>
    {content_html}
</body>
</html>
            '''
        else:
            return TIMETABLE_CSS + content_html


def render_batch_timetable_html(
    batch_section: str,
    offerings: List[Offering],
    semester: str = "Spring-2026",
    standalone: bool = True,
) -> str:
    """
    Convenience function to render a batch timetable as HTML.
    
    Args:
        batch_section: Batch identifier
        offerings: List of offerings for this batch
        semester: Semester label
        standalone: Include full HTML document wrapper
    
    Returns:
        HTML string
    """
    renderer = TimetableHTMLRenderer()
    return renderer.render(batch_section, offerings, semester, standalone)


def render_batch_from_entries_html(
    batch_section: str,
    entries: List[Dict],
    semester: str = "Spring-2026",
    standalone: bool = True,
) -> str:
    """
    Convenience function to render a batch timetable from MongoDB-style entries.
    
    Args:
        batch_section: Batch identifier
        entries: List of entry dicts with day, slotStart, slotSpan, course, teacher, room, type
        semester: Semester label
        standalone: Include full HTML document wrapper
    
    Returns:
        HTML string
    """
    renderer = TimetableHTMLRenderer()
    return renderer.render_from_entries(batch_section, entries, semester, standalone)

