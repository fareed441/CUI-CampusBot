#!/usr/bin/env python3
"""
Timetable Generator - Main Entry Point

Generates clash-free timetables from CSV/Excel data using OR-Tools CP-SAT solver.

Usage:
    python generate_timetable.py <input_file.csv> [options]
    
Options:
    --output-dir DIR    Output directory (default: output/timetables)
    --time-limit SEC    Solver time limit in seconds (default: 120)
    --formats FMT       Output formats: html,pdf,xlsx (default: html,pdf,xlsx)
    --rooms FILE        Optional CSV file with room list
    
Example:
    python generate_timetable.py all_batches_courses_teachers_spring2026.csv --time-limit 180
"""
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from timetable_generator.csv_parser import TimetableDataParser, ParsedData
from timetable_generator.cpsat_generator import (
    TimetableGenerator, GeneratorResult, SolverStatus, assign_rooms
)
from timetable_generator.clash_checker import ClashChecker, ClashReport
from timetable_generator.output_generator import TimetableOutputGenerator


# Default rooms if none provided
DEFAULT_LECTURE_ROOMS = [
    "CS-1", "CS-2", "CS-3", "CS-4", "CS-5", "CS-6",
    "MS-1", "MS-2", "MS-3", "MS-4", "MS-5", "MS-6",
    "GEN-1", "GEN-2", "GEN-3", "GEN-4", "GEN-5", "GEN-6",
    "HUM-1", "HUM-2", "HUM-3",
    "BTY-1", "BTY-2",
]

DEFAULT_LAB_ROOMS = [
    "Lab-1", "Lab-2", "Lab-3", "Lab-4", "Lab-5", "Lab-6",
    "Lab-7", "Lab-8", "Lab-9", "Lab-10",
    "BTY-Lab-1", "BTY-Lab-2", "BTY-Lab-3",
    "GP-Lab-1", "GP-Lab-2",
]


def parse_excel_to_csv(excel_path: str) -> str:
    """Convert Excel file to CSV if needed."""
    path = Path(excel_path)
    
    if path.suffix.lower() in ['.xlsx', '.xls']:
        try:
            import pandas as pd
            print(f"Converting Excel to CSV...")
            df = pd.read_excel(excel_path)
            csv_path = path.with_suffix('.csv')
            df.to_csv(csv_path, index=False)
            print(f"  Saved as: {csv_path}")
            return str(csv_path)
        except ImportError:
            print("ERROR: pandas and openpyxl required for Excel files.")
            print("Run: pip install pandas openpyxl")
            sys.exit(1)
    
    return excel_path


def main():
    parser = argparse.ArgumentParser(
        description='Generate clash-free timetables from CSV/Excel data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_timetable.py data.csv
  python generate_timetable.py data.xlsx --time-limit 180 --formats html,pdf
  python generate_timetable.py data.csv --output-dir my_timetables
        """
    )
    
    parser.add_argument('input_file', help='Input CSV or Excel file')
    parser.add_argument('--output-dir', default='output/timetables',
                       help='Output directory (default: output/timetables)')
    parser.add_argument('--time-limit', type=float, default=120.0,
                       help='Solver time limit in seconds (default: 120)')
    parser.add_argument('--formats', default='html,pdf,xlsx',
                       help='Output formats: html,pdf,xlsx (default: html,pdf,xlsx)')
    parser.add_argument('--rooms', help='Optional CSV file with room list')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    args = parser.parse_args()
    
    # Validate input file
    if not os.path.exists(args.input_file):
        print(f"ERROR: Input file not found: {args.input_file}")
        sys.exit(1)
    
    print("="*70)
    print("COMSATS CLASH-FREE TIMETABLE GENERATOR")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Step 1: Parse input file
    print("\n[1/5] PARSING INPUT FILE")
    print("-"*40)
    
    input_path = parse_excel_to_csv(args.input_file)
    
    data_parser = TimetableDataParser()
    parsed_data: ParsedData = data_parser.parse_csv(input_path)
    data_parser.print_summary()
    
    if not parsed_data.sessions:
        print("ERROR: No valid sessions found in input file")
        sys.exit(1)
    
    # Step 2: Generate timetable
    print("\n[2/5] GENERATING CLASH-FREE TIMETABLE")
    print("-"*40)
    
    generator = TimetableGenerator(time_limit_seconds=args.time_limit)
    result: GeneratorResult = generator.generate(parsed_data)
    
    if result.status == SolverStatus.INFEASIBLE:
        print("\n" + "="*70)
        print("GENERATION FAILED - NO VALID SCHEDULE EXISTS")
        print("="*70)
        if result.conflicts:
            print("\nConflicts detected:")
            for conflict in result.conflicts:
                print(f"  - {conflict}")
        print("\nPossible solutions:")
        print("  1. Reduce number of sessions for overloaded teachers/batches")
        print("  2. Add more time slots or days")
        print("  3. Split large batches into sections")
        sys.exit(1)
    
    if result.status == SolverStatus.TIMEOUT:
        print("\nWARNING: Solver timed out. Try increasing --time-limit")
        sys.exit(1)
    
    # Step 3: Assign rooms
    print("\n[3/5] ASSIGNING ROOMS")
    print("-"*40)
    
    result.scheduled_sessions = assign_rooms(
        result.scheduled_sessions,
        DEFAULT_LECTURE_ROOMS,
        DEFAULT_LAB_ROOMS
    )
    
    # Update schedule_by_batch with room assignments
    from collections import defaultdict
    result.schedule_by_batch = defaultdict(list)
    for session in result.scheduled_sessions:
        result.schedule_by_batch[session.session.batch_section].append(session)
    result.schedule_by_batch = dict(result.schedule_by_batch)
    
    rooms_assigned = sum(
        1 for s in result.scheduled_sessions 
        if s.room_code and s.room_code != "TBA"
    )
    print(f"  Rooms assigned: {rooms_assigned}/{len(result.scheduled_sessions)}")
    
    # Step 4: Verify no clashes
    print("\n[4/5] VERIFYING TIMETABLE")
    print("-"*40)
    
    checker = ClashChecker()
    report: ClashReport = checker.check(result.scheduled_sessions)
    report.print_report()
    
    if not report.is_clash_free:
        print("WARNING: Clashes detected! This should not happen with CP-SAT solver.")
        print("Please report this issue.")
    
    # Step 5: Generate outputs
    print("\n[5/5] GENERATING OUTPUT FILES")
    print("-"*40)
    
    output_generator = TimetableOutputGenerator(args.output_dir)
    formats = [f.strip() for f in args.formats.split(',')]
    
    generated = output_generator.generate_all(result, formats)
    
    print(f"\nOutput directory: {args.output_dir}")
    for fmt, files in generated.items():
        print(f"\n{fmt.upper()} files ({len(files)}):")
        for f in files[:5]:
            print(f"  - {Path(f).name}")
        if len(files) > 5:
            print(f"  ... and {len(files) - 5} more")
    
    # Summary
    print("\n" + "="*70)
    print("GENERATION COMPLETE")
    print("="*70)
    print(f"Status: {result.status.value.upper()}")
    print(f"Sessions scheduled: {result.total_scheduled}/{result.total_sessions}")
    print(f"Batches: {len(result.schedule_by_batch)}")
    print(f"Solving time: {result.solving_time_seconds:.2f}s")
    print(f"Total gaps: {result.total_gaps}")
    print(f"Late slots (slot 6): {result.total_late_slots}")
    print(f"Clashes: {report.total_clashes}")
    print(f"\nOutput directory: {os.path.abspath(args.output_dir)}")
    print("="*70)


if __name__ == "__main__":
    main()
