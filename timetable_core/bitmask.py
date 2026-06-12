"""
Bitmask operations for ultra-fast clash detection.

Each offering is represented as a 30-bit mask (5 days * 6 slots).
Bit layout: 
  bits 0-5:   Monday   slots 1-6
  bits 6-11:  Tuesday  slots 1-6
  bits 12-17: Wednesday slots 1-6
  bits 18-23: Thursday  slots 1-6
  bits 24-29: Friday    slots 1-6

Clash check is O(1): (maskA & maskB) != 0

This allows Layer-1 filtering to be O(n) even with thousands of offerings.
"""
from typing import List, Tuple, Dict, Optional
from .models import (
    Day, Meeting, Offering, Student, ClashDetail, 
    DAYS, TIMESLOTS, TOTAL_CELLS, DAY_FULL_NAMES
)


def cell_index(day: Day, slot: int) -> int:
    """
    Convert (day, slot) to bit index.
    day: Day enum (0-4)
    slot: 1-6
    Returns: bit index 0-29
    """
    # slot is 1-indexed, convert to 0-indexed
    return day.value * 6 + (slot - 1)


def index_to_day_slot(index: int) -> Tuple[Day, int]:
    """
    Convert bit index back to (day, slot).
    index: 0-29
    Returns: (Day, slot 1-6)
    """
    day_index = index // 6
    slot = (index % 6) + 1
    return DAYS[day_index], slot


def meeting_to_bitmask(meeting: Meeting) -> int:
    """
    Convert a single meeting to its bitmask.
    Handles multi-slot meetings (labs).
    """
    mask = 0
    for slot in range(meeting.slot_start, meeting.slot_end + 1):
        bit_index = cell_index(meeting.day, slot)
        mask |= (1 << bit_index)
    return mask


def offering_to_bitmask(offering: Offering) -> int:
    """
    Convert an offering's all meetings to a combined bitmask.
    Caches the result in offering._bitmask.
    """
    if offering._bitmask is not None:
        return offering._bitmask
    
    mask = 0
    for meeting in offering.meetings:
        mask |= meeting_to_bitmask(meeting)
    
    offering._bitmask = mask
    return mask


def student_schedule_mask(student: Student, offerings_map: Dict[str, Offering]) -> int:
    """
    Compute combined bitmask of all student's enrolled offerings.
    Caches the result in student._schedule_mask.
    
    Args:
        student: The student
        offerings_map: Dict of offering_id -> Offering
    
    Returns:
        Combined bitmask of student's schedule
    """
    if student._schedule_mask is not None:
        return student._schedule_mask
    
    mask = 0
    for offering_id in student.enrolled_offering_ids:
        if offering_id in offerings_map:
            mask |= offering_to_bitmask(offerings_map[offering_id])
    
    student._schedule_mask = mask
    return mask


def check_clash(mask1: int, mask2: int) -> bool:
    """
    Ultra-fast clash check using bitwise AND.
    Returns True if there's any overlap.
    """
    return (mask1 & mask2) != 0


def check_clash_offerings(offering1: Offering, offering2: Offering) -> bool:
    """
    Check if two offerings clash.
    """
    mask1 = offering_to_bitmask(offering1)
    mask2 = offering_to_bitmask(offering2)
    return check_clash(mask1, mask2)


def get_clash_bits(mask1: int, mask2: int) -> int:
    """
    Get the bits where clashes occur.
    """
    return mask1 & mask2


def get_clash_details(
    mask1: int, 
    mask2: int,
    offering1_id: str = "offering1",
    offering2_id: str = "offering2"
) -> List[ClashDetail]:
    """
    Get detailed information about all clashing cells.
    
    Returns list of ClashDetail objects describing each clash.
    """
    clash_bits = get_clash_bits(mask1, mask2)
    if clash_bits == 0:
        return []
    
    details = []
    for i in range(TOTAL_CELLS):
        if clash_bits & (1 << i):
            day, slot = index_to_day_slot(i)
            timeslot = TIMESLOTS[slot]
            details.append(ClashDetail(
                day=day,
                slot=slot,
                offering1_id=offering1_id,
                offering2_id=offering2_id,
                reason=f"Both scheduled on {DAY_FULL_NAMES[day]} at {timeslot.display}"
            ))
    
    return details


def get_clash_details_offerings(
    offering1: Offering,
    offering2: Offering
) -> List[ClashDetail]:
    """
    Get clash details between two offerings.
    """
    mask1 = offering_to_bitmask(offering1)
    mask2 = offering_to_bitmask(offering2)
    return get_clash_details(mask1, mask2, offering1.offering_id, offering2.offering_id)


def count_gaps_in_day(mask: int, day: Day) -> int:
    """
    Count gap slots (free slots between classes) for a given day.
    Used for schedule quality scoring.
    """
    day_mask = 0
    start_bit = day.value * 6
    for i in range(6):
        if mask & (1 << (start_bit + i)):
            day_mask |= (1 << i)
    
    if day_mask == 0:
        return 0
    
    # Find first and last set bit
    first_slot = -1
    last_slot = -1
    for i in range(6):
        if day_mask & (1 << i):
            if first_slot == -1:
                first_slot = i
            last_slot = i
    
    if first_slot == last_slot:
        return 0
    
    # Count gaps (zeros between first and last bit)
    gaps = 0
    for i in range(first_slot + 1, last_slot):
        if not (day_mask & (1 << i)):
            gaps += 1
    
    return gaps


def total_gaps(mask: int) -> int:
    """
    Count total gaps across all days.
    """
    return sum(count_gaps_in_day(mask, day) for day in DAYS)


def count_late_slots(mask: int) -> int:
    """
    Count late slots (slot 5 and 6) used.
    Used for schedule quality scoring.
    """
    late_count = 0
    for day in DAYS:
        start_bit = day.value * 6
        # Slots 5 and 6 are bits 4 and 5 within the day
        if mask & (1 << (start_bit + 4)):  # Slot 5
            late_count += 1
        if mask & (1 << (start_bit + 5)):  # Slot 6
            late_count += 1
    return late_count


def mask_to_grid(mask: int) -> List[List[bool]]:
    """
    Convert bitmask to 5x6 grid for visualization.
    Returns: grid[day][slot-1] = True if occupied
    """
    grid = [[False] * 6 for _ in range(5)]
    for i in range(TOTAL_CELLS):
        if mask & (1 << i):
            day_idx = i // 6
            slot_idx = i % 6
            grid[day_idx][slot_idx] = True
    return grid


def grid_to_mask(grid: List[List[bool]]) -> int:
    """
    Convert 5x6 grid back to bitmask.
    grid[day][slot-1] = True if occupied
    """
    mask = 0
    for day_idx in range(5):
        for slot_idx in range(6):
            if grid[day_idx][slot_idx]:
                mask |= (1 << (day_idx * 6 + slot_idx))
    return mask


def mask_to_string(mask: int) -> str:
    """
    Convert bitmask to readable string representation.
    Useful for debugging.
    """
    lines = []
    lines.append("     S1  S2  S3  |  S4  S5  S6")
    lines.append("    " + "-" * 28)
    
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for day in DAYS:
        start_bit = day.value * 6
        slots = []
        for i in range(6):
            if mask & (1 << (start_bit + i)):
                slots.append(" X ")
            else:
                slots.append(" . ")
            if i == 2:  # Break after slot 3
                slots.append(" | ")
        lines.append(f"{day_names[day.value]}  {''.join(slots)}")
    
    return "\n".join(lines)


def combine_masks(*masks: int) -> int:
    """
    Combine multiple masks with OR operation.
    """
    result = 0
    for mask in masks:
        result |= mask
    return result


def slots_used_count(mask: int) -> int:
    """
    Count total number of slots used (popcount).
    """
    return bin(mask).count('1')


def get_free_slots(mask: int) -> List[Tuple[Day, int]]:
    """
    Get list of all free (day, slot) pairs.
    """
    free = []
    for i in range(TOTAL_CELLS):
        if not (mask & (1 << i)):
            day, slot = index_to_day_slot(i)
            free.append((day, slot))
    return free


def get_occupied_slots(mask: int) -> List[Tuple[Day, int]]:
    """
    Get list of all occupied (day, slot) pairs.
    """
    occupied = []
    for i in range(TOTAL_CELLS):
        if mask & (1 << i):
            day, slot = index_to_day_slot(i)
            occupied.append((day, slot))
    return occupied
