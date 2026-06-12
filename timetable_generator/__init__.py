"""
Timetable Generator Package

Generates clash-free timetables from CSV data using OR-Tools CP-SAT solver.
"""
from .csv_parser import TimetableDataParser, ParsedData, ClassSession
from .cpsat_generator import (
    TimetableGenerator, GeneratorResult, ScheduledSession, 
    SolverStatus, assign_rooms
)
from .clash_checker import ClashChecker, ClashReport
from .output_generator import TimetableOutputGenerator, generate_outputs

__all__ = [
    'TimetableDataParser', 
    'ParsedData',
    'ClassSession',
    'TimetableGenerator', 
    'GeneratorResult',
    'ScheduledSession',
    'SolverStatus',
    'assign_rooms',
    'ClashChecker',
    'ClashReport',
    'TimetableOutputGenerator',
    'generate_outputs',
]
