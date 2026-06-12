"""
PDF Renderer for Timetables - Exact CUI Format

Renders timetables in the EXACT format as "Central Timetable (Undergraduate-V-02) For Spring-2026.pdf":
- Header: "COMSATS Vehari Centralized Timetable (V-2)-Spring-2026"
- Big centered batch title (e.g., "BCS-FA25-2A")
- Table layout:
  - Left column with rotated day labels (Monday-Friday)
  - Slot 1, Slot 2, Slot 3, BREAK column, Slot 4, Slot 5, Slot 6
  - Each slot header shows slot number + time range
  - BREAK column shows "Break / 2Hrs Class" and "1:00 - 1:30 PM"
  - Labs/2-hour classes span merged cells
- Footer: "COMSATS Centralized Timetable-<date>" and "aSc Timetables"
"""
from io import BytesIO
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import inch, cm, mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, 
        Spacer, PageBreak
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
    
    # Colors matching CUI timetable (only defined if reportlab is available)
    HEADER_BG = colors.Color(0.2, 0.4, 0.6)  # Dark blue
    HEADER_TEXT = colors.white
    CELL_BG_LECTURE = colors.Color(0.95, 0.95, 1.0)  # Light blue
    CELL_BG_LAB = colors.Color(1.0, 0.95, 0.9)  # Light orange
    BREAK_BG = colors.Color(0.9, 0.9, 0.9)  # Gray
    BORDER_COLOR = colors.black
    GRID_COLOR = colors.Color(0.5, 0.5, 0.5)
except ImportError:
    REPORTLAB_AVAILABLE = False
    colors = None

import sys
sys.path.insert(0, 'c:/Users/Fareed Bhatti/Desktop/CUI Campus bot 1')

from timetable_core.models import (
    Offering, Day, Meeting, TIMESLOTS, DAYS, 
    DAY_FULL_NAMES, DAY_SHORT_NAMES, OfferingType
)


class TimetablePDFRenderer:
    """
    Renders batch timetables as PDFs in CUI format.
    """
    
    def __init__(self, page_size=None):
        """
        Initialize renderer.
        
        Args:
            page_size: Page size (default: A4 landscape)
        """
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab not installed. Run: pip install reportlab")
        
        if page_size is None:
            page_size = landscape(A4)
        
        self.page_size = page_size
        self.width, self.height = page_size
        
        # Margins
        self.left_margin = 0.5 * inch
        self.right_margin = 0.5 * inch
        self.top_margin = 0.5 * inch
        self.bottom_margin = 0.5 * inch
        
        # Calculate usable area
        self.usable_width = self.width - self.left_margin - self.right_margin
        self.usable_height = self.height - self.top_margin - self.bottom_margin
        
        # Column widths (proportional)
        # Day column + 6 slots + break column = 8 columns
        day_col_width = 0.6 * inch
        break_col_width = 0.7 * inch
        remaining = self.usable_width - day_col_width - break_col_width
        slot_col_width = remaining / 6
        
        self.col_widths = [
            day_col_width,      # Days
            slot_col_width,     # Slot 1
            slot_col_width,     # Slot 2
            slot_col_width,     # Slot 3
            break_col_width,    # Break
            slot_col_width,     # Slot 4
            slot_col_width,     # Slot 5
            slot_col_width,     # Slot 6
        ]
        
        # Row heights
        self.header_row_height = 0.6 * inch
        self.data_row_height = 1.0 * inch
        
        # Styles
        self.styles = getSampleStyleSheet()
        self._setup_styles()
    
    def _setup_styles(self):
        """Setup custom paragraph styles."""
        self.title_style = ParagraphStyle(
            'TimetableTitle',
            parent=self.styles['Heading1'],
            fontSize=16,
            alignment=TA_CENTER,
            spaceAfter=6,
            textColor=colors.black,
        )
        
        self.batch_style = ParagraphStyle(
            'BatchTitle',
            parent=self.styles['Heading2'],
            fontSize=20,
            alignment=TA_CENTER,
            spaceAfter=12,
            fontName='Helvetica-Bold',
        )
        
        self.header_style = ParagraphStyle(
            'HeaderCell',
            parent=self.styles['Normal'],
            fontSize=8,
            alignment=TA_CENTER,
            textColor=HEADER_TEXT,
            fontName='Helvetica-Bold',
        )
        
        self.cell_course_style = ParagraphStyle(
            'CellCourse',
            parent=self.styles['Normal'],
            fontSize=7,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            leading=9,
        )
        
        self.cell_room_style = ParagraphStyle(
            'CellRoom',
            parent=self.styles['Normal'],
            fontSize=7,
            alignment=TA_CENTER,
            fontName='Helvetica',
            leading=9,
        )
        
        self.cell_teacher_style = ParagraphStyle(
            'CellTeacher',
            parent=self.styles['Normal'],
            fontSize=6,
            alignment=TA_CENTER,
            fontName='Helvetica',
            leading=8,
        )
        
        self.footer_style = ParagraphStyle(
            'Footer',
            parent=self.styles['Normal'],
            fontSize=8,
            alignment=TA_LEFT,
        )
    
    def _build_schedule_grid(
        self, 
        offerings: List[Offering]
    ) -> Dict[Tuple[int, int], List[Dict]]:
        """
        Build a grid of cell contents from offerings.
        
        Returns:
            Dict[(day_index, slot)] -> list of cell content dicts
        """
        grid = {}
        
        for offering in offerings:
            for meeting in offering.meetings:
                day_idx = meeting.day.value
                
                # For double-slot classes, we need to handle merging
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
                if key not in grid:
                    grid[key] = []
                grid[key].append(cell_data)
        
        return grid
    
    def _format_cell_content(self, cell_data: Dict) -> str:
        """Format cell content as HTML-like string for Paragraph."""
        course = cell_data['course_name']
        room = cell_data['room']
        teacher = cell_data['teacher']
        dept = cell_data.get('dept', '')
        
        if dept:
            teacher_line = f"{teacher} ({dept})"
        else:
            teacher_line = teacher
        
        # Wrap and format
        return f"""<b>{course}</b><br/>
{room}<br/>
<font size="6">{teacher_line}</font>"""
    
    def _build_table_data(
        self,
        grid: Dict[Tuple[int, int], List[Dict]],
        batch_section: str
    ) -> Tuple[List[List], List[Tuple]]:
        """
        Build table data array and span specifications.
        
        Returns:
            (data_rows, span_list) where span_list contains (row, col, rowspan, colspan)
        """
        # Header row
        header = [
            Paragraph('', self.header_style),  # Day column
            Paragraph('Slot 1<br/>8:30-10:00 AM', self.header_style),
            Paragraph('Slot 2<br/>10:00-11:30 AM', self.header_style),
            Paragraph('Slot 3<br/>11:30-1:00 PM', self.header_style),
            Paragraph('Break<br/>2Hrs Class<br/>1:00-1:30 PM', self.header_style),
            Paragraph('Slot 4<br/>1:30-3:00 PM', self.header_style),
            Paragraph('Slot 5<br/>3:00-4:30 PM', self.header_style),
            Paragraph('Slot 6<br/>4:30-6:00 PM', self.header_style),
        ]
        
        data = [header]
        spans = []
        
        # Day rows
        for day_idx, day in enumerate(DAYS):
            row = [Paragraph(f'<b>{DAY_FULL_NAMES[day]}</b>', self.cell_course_style)]
            
            # Track which slots are covered by spans
            covered_slots = set()
            
            # First pass: identify spans
            for slot in range(1, 7):
                if slot in covered_slots:
                    continue
                
                key = (day_idx, slot)
                if key in grid:
                    cell_data = grid[key][0]  # Take first if multiple
                    span = cell_data['span']
                    if span > 1:
                        for s in range(slot, slot + span):
                            covered_slots.add(s)
            
            # Second pass: build row
            covered_slots = set()
            for slot in range(1, 7):
                if slot in covered_slots:
                    # This slot is covered by a span, add empty
                    row.append('')
                    continue
                
                key = (day_idx, slot)
                if key in grid:
                    cell_data = grid[key][0]
                    content = self._format_cell_content(cell_data)
                    row.append(Paragraph(content, self.cell_course_style))
                    
                    span = cell_data['span']
                    if span > 1:
                        # Record span (need to account for break column)
                        actual_col = slot  # Column index (1-based slot + day column)
                        
                        # Handle break column insertion
                        if slot <= 3 and slot + span > 3:
                            # Span crosses break - shouldn't happen per our constraints
                            pass
                        elif slot <= 3:
                            # Before break
                            spans.append((day_idx + 1, actual_col, 1, span))
                        else:
                            # After break - account for break column (column 4)
                            spans.append((day_idx + 1, actual_col + 1, 1, span))
                        
                        for s in range(slot + 1, slot + span):
                            covered_slots.add(s)
                else:
                    row.append('')
                
                # Insert break column after slot 3
                if slot == 3:
                    row.append(Paragraph('<b>Break</b>', self.cell_course_style))
            
            # Ensure row has correct number of columns
            # Day + S1 + S2 + S3 + Break + S4 + S5 + S6 = 8 columns
            while len(row) < 8:
                row.append('')
            
            data.append(row)
        
        # Add vertical span for break column (rows 1-5, column 4)
        spans.append((1, 4, 5, 1))  # (row, col, rowspan, colspan)
        
        return data, spans
    
    def _build_schedule_grid_from_entries(
        self,
        entries: List[Dict]
    ) -> Dict[Tuple[int, int], List[Dict]]:
        """
        Build a grid of cell contents from MongoDB-style entries.
        
        Args:
            entries: List of entry dicts with day, slotStart, slotSpan, course, teacher, room, type
        
        Returns:
            Dict[(day_index, slot)] -> list of cell content dicts
        """
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
            if key not in grid:
                grid[key] = []
            grid[key].append(cell_data)
        
        return grid
    
    def render_batch_from_entries(
        self,
        batch_section: str,
        entries: List[Dict],
        output_path: Optional[str] = None,
        semester: str = "Spring-2026",
    ) -> bytes:
        """
        Render timetable for a batch from MongoDB-style entry dicts.
        
        Args:
            batch_section: Batch identifier (e.g., "FA22-BCS-8A")
            entries: List of entry dicts with day, slotStart, slotSpan, course, teacher, room, type
            output_path: Optional file path to save PDF
            semester: Semester label
        
        Returns:
            PDF file as bytes
        """
        buffer = BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.page_size,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin,
        )
        
        story = []
        
        # Title
        title_text = f"COMSATS Vehari Centralized Timetable (V-2)-{semester}"
        story.append(Paragraph(f'<u>{title_text}</u>', self.title_style))
        story.append(Spacer(1, 0.1 * inch))
        
        # Batch title
        story.append(Paragraph(batch_section, self.batch_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Build grid and table data from entries
        grid = self._build_schedule_grid_from_entries(entries)
        data, spans = self._build_table_data(grid, batch_section)
        
        # Create table
        table = Table(
            data,
            colWidths=self.col_widths,
            rowHeights=[self.header_row_height] + [self.data_row_height] * 5
        )
        
        # Table style
        style_commands = [
            # Header row styling
            ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            
            # All cells
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Day column styling
            ('BACKGROUND', (0, 1), (0, -1), colors.Color(0.85, 0.85, 0.85)),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            
            # Break column styling
            ('BACKGROUND', (4, 0), (4, -1), BREAK_BG),
            
            # Grid lines
            ('GRID', (0, 0), (-1, -1), 1, GRID_COLOR),
            ('BOX', (0, 0), (-1, -1), 2, BORDER_COLOR),
            
            # Inner gridlines
            ('INNERGRID', (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ]
        
        # Apply spans
        for row, col, rowspan, colspan in spans:
            if rowspan > 1 or colspan > 1:
                end_row = row + rowspan - 1
                end_col = col + colspan - 1
                style_commands.append(('SPAN', (col, row), (end_col, end_row)))
        
        table.setStyle(TableStyle(style_commands))
        story.append(table)
        
        # Footer
        story.append(Spacer(1, 0.3 * inch))
        
        footer_date = datetime.now().strftime("%Y-%m-%d")
        footer_left = f"COMSATS Centralized Timetable-{footer_date}"
        footer_right = "aSc Timetables"
        
        footer_table = Table(
            [[Paragraph(footer_left, self.footer_style), 
              Paragraph(footer_right, self.footer_style)]],
            colWidths=[self.usable_width * 0.7, self.usable_width * 0.3]
        )
        footer_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        story.append(footer_table)
        
        # Build PDF
        doc.build(story)
        
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        # Save to file if path provided
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
        
        return pdf_bytes
    
    def render_multiple_batches(
        self,
        batch_data_list: List[Dict],
        output_path: Optional[str] = None,
        semester: str = "Spring-2026",
    ) -> bytes:
        """
        Render multiple batches into a single PDF, one page per batch.
        
        Args:
            batch_data_list: List of dicts, each containing:
                - batch_section: str
                - entries: List[Dict] (MongoDB-style entries)
            output_path: Optional file path to save PDF
            semester: Semester label
        
        Returns:
            PDF file as bytes
        """
        buffer = BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.page_size,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin,
        )
        
        story = []
        
        for i, batch_data in enumerate(batch_data_list):
            batch_section = batch_data.get('batch_section', 'Unknown')
            entries = batch_data.get('entries', [])
            
            # Page break for all except first
            if i > 0:
                story.append(PageBreak())
            
            # Title
            title_text = f"COMSATS Vehari Centralized Timetable (V-2)-{semester}"
            story.append(Paragraph(f'<u>{title_text}</u>', self.title_style))
            story.append(Spacer(1, 0.1 * inch))
            
            # Batch title
            story.append(Paragraph(batch_section, self.batch_style))
            story.append(Spacer(1, 0.2 * inch))
            
            # Build grid and table data
            grid = self._build_schedule_grid_from_entries(entries)
            data, spans = self._build_table_data(grid, batch_section)
            
            # Create table
            table = Table(
                data,
                colWidths=self.col_widths,
                rowHeights=[self.header_row_height] + [self.data_row_height] * 5
            )
            
            # Table style
            style_commands = [
                ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
                ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 1), (0, -1), colors.Color(0.85, 0.85, 0.85)),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('BACKGROUND', (4, 0), (4, -1), BREAK_BG),
                ('GRID', (0, 0), (-1, -1), 1, GRID_COLOR),
                ('BOX', (0, 0), (-1, -1), 2, BORDER_COLOR),
                ('INNERGRID', (0, 0), (-1, -1), 0.5, GRID_COLOR),
            ]
            
            for row, col, rowspan, colspan in spans:
                if rowspan > 1 or colspan > 1:
                    end_row = row + rowspan - 1
                    end_col = col + colspan - 1
                    style_commands.append(('SPAN', (col, row), (end_col, end_row)))
            
            table.setStyle(TableStyle(style_commands))
            story.append(table)
            
            # Footer
            story.append(Spacer(1, 0.3 * inch))
            footer_date = datetime.now().strftime("%Y-%m-%d")
            footer_left = f"COMSATS Centralized Timetable-{footer_date}"
            footer_right = f"Page {i+1} of {len(batch_data_list)} - aSc Timetables"
            
            footer_table = Table(
                [[Paragraph(footer_left, self.footer_style), 
                  Paragraph(footer_right, self.footer_style)]],
                colWidths=[self.usable_width * 0.7, self.usable_width * 0.3]
            )
            footer_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ]))
            story.append(footer_table)
        
        # Build PDF
        doc.build(story)
        
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
        
        return pdf_bytes

    def render(
        self,
        batch_section: str,
        offerings: List[Offering],
        output_path: Optional[str] = None,
        semester: str = "Spring-2026",
    ) -> bytes:
        """
        Render timetable for a batch section.
        
        Args:
            batch_section: Batch identifier (e.g., "BCS-FA25-2A")
            offerings: List of offerings for this batch
            output_path: Optional file path to save PDF
            semester: Semester label
        
        Returns:
            PDF file as bytes
        """
        buffer = BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.page_size,
            leftMargin=self.left_margin,
            rightMargin=self.right_margin,
            topMargin=self.top_margin,
            bottomMargin=self.bottom_margin,
        )
        
        story = []
        
        # Title
        title_text = f"COMSATS Vehari Centralized Timetable (V-2)-{semester}"
        story.append(Paragraph(f'<u>{title_text}</u>', self.title_style))
        story.append(Spacer(1, 0.1 * inch))
        
        # Batch title
        story.append(Paragraph(batch_section, self.batch_style))
        story.append(Spacer(1, 0.2 * inch))
        
        # Build grid and table data
        grid = self._build_schedule_grid(offerings)
        data, spans = self._build_table_data(grid, batch_section)
        
        # Create table
        table = Table(
            data,
            colWidths=self.col_widths,
            rowHeights=[self.header_row_height] + [self.data_row_height] * 5
        )
        
        # Table style
        style_commands = [
            # Header row styling
            ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
            ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_TEXT),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            
            # All cells
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Day column styling
            ('BACKGROUND', (0, 1), (0, -1), colors.Color(0.85, 0.85, 0.85)),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            
            # Break column styling
            ('BACKGROUND', (4, 0), (4, -1), BREAK_BG),
            
            # Grid lines
            ('GRID', (0, 0), (-1, -1), 1, GRID_COLOR),
            ('BOX', (0, 0), (-1, -1), 2, BORDER_COLOR),
            
            # Inner gridlines
            ('INNERGRID', (0, 0), (-1, -1), 0.5, GRID_COLOR),
        ]
        
        # Apply spans
        for row, col, rowspan, colspan in spans:
            if rowspan > 1 or colspan > 1:
                end_row = row + rowspan - 1
                end_col = col + colspan - 1
                style_commands.append(('SPAN', (col, row), (end_col, end_row)))
        
        table.setStyle(TableStyle(style_commands))
        story.append(table)
        
        # Footer
        story.append(Spacer(1, 0.3 * inch))
        
        footer_date = datetime.now().strftime("%Y-%m-%d")
        footer_left = f"COMSATS Centralized Timetable-{footer_date}"
        footer_right = "aSc Timetables"
        
        footer_table = Table(
            [[Paragraph(footer_left, self.footer_style), 
              Paragraph(footer_right, self.footer_style)]],
            colWidths=[self.usable_width * 0.7, self.usable_width * 0.3]
        )
        footer_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ]))
        story.append(footer_table)
        
        # Build PDF
        doc.build(story)
        
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        # Save to file if path provided
        if output_path:
            with open(output_path, 'wb') as f:
                f.write(pdf_bytes)
        
        return pdf_bytes


def render_batch_timetable_pdf(
    batch_section: str,
    offerings: List[Offering],
    output_path: Optional[str] = None,
    semester: str = "Spring-2026",
) -> bytes:
    """
    Convenience function to render a batch timetable PDF.
    
    Args:
        batch_section: Batch identifier
        offerings: List of offerings for this batch
        output_path: Optional file path to save
        semester: Semester label
    
    Returns:
        PDF as bytes
    """
    renderer = TimetablePDFRenderer()
    return renderer.render(batch_section, offerings, output_path, semester)
