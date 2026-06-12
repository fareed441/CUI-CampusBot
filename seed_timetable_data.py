"""
Seed MongoDB with Sample Timetable Data

This script populates the MongoDB timetable_entries collection with sample data
for testing the timetable system.

Run: python seed_timetable_data.py
"""
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.mongodb_timetable import get_timetable_store, normalize_batch_code


def create_sample_entries():
    """Create sample timetable entries for testing."""
    
    # Sample data for multiple batches
    batches_data = {
        "FA22-BCS-8A": [
            {"day": 0, "slotStart": 1, "slotSpan": 1, "course": "Artificial Intelligence", "teacher": "Dr. Ahmed Khan", "room": "CS-1", "type": "LEC"},
            {"day": 0, "slotStart": 2, "slotSpan": 1, "course": "Machine Learning", "teacher": "Dr. Sara Ali", "room": "CS-2", "type": "LEC"},
            {"day": 0, "slotStart": 4, "slotSpan": 2, "course": "AI Lab", "teacher": "Dr. Ahmed Khan", "room": "Lab-1", "type": "LAB"},
            {"day": 1, "slotStart": 1, "slotSpan": 1, "course": "Database Systems", "teacher": "Mr. Usman Malik", "room": "CS-3", "type": "LEC"},
            {"day": 1, "slotStart": 3, "slotSpan": 1, "course": "Software Engineering", "teacher": "Ms. Fatima Hassan", "room": "CS-1", "type": "LEC"},
            {"day": 1, "slotStart": 4, "slotSpan": 2, "course": "DB Lab", "teacher": "Mr. Usman Malik", "room": "Lab-2", "type": "LAB"},
            {"day": 2, "slotStart": 2, "slotSpan": 1, "course": "Machine Learning", "teacher": "Dr. Sara Ali", "room": "CS-2", "type": "LEC"},
            {"day": 2, "slotStart": 3, "slotSpan": 1, "course": "Artificial Intelligence", "teacher": "Dr. Ahmed Khan", "room": "CS-1", "type": "LEC"},
            {"day": 3, "slotStart": 1, "slotSpan": 1, "course": "Database Systems", "teacher": "Mr. Usman Malik", "room": "CS-3", "type": "LEC"},
            {"day": 3, "slotStart": 5, "slotSpan": 1, "course": "Software Engineering", "teacher": "Ms. Fatima Hassan", "room": "CS-1", "type": "LEC"},
            {"day": 4, "slotStart": 2, "slotSpan": 2, "course": "ML Lab", "teacher": "Dr. Sara Ali", "room": "Lab-1", "type": "LAB"},
        ],
        "FA23-BCS-6A": [
            {"day": 0, "slotStart": 1, "slotSpan": 1, "course": "Operating Systems", "teacher": "Dr. Imran Shah", "room": "CS-2", "type": "LEC"},
            {"day": 0, "slotStart": 2, "slotSpan": 1, "course": "Computer Networks", "teacher": "Dr. Zubair Ahmed", "room": "CS-1", "type": "LEC"},
            {"day": 0, "slotStart": 4, "slotSpan": 2, "course": "OS Lab", "teacher": "Dr. Imran Shah", "room": "Lab-2", "type": "LAB"},
            {"day": 1, "slotStart": 1, "slotSpan": 1, "course": "Web Development", "teacher": "Mr. Bilal Khan", "room": "CS-3", "type": "LEC"},
            {"day": 1, "slotStart": 3, "slotSpan": 1, "course": "Data Mining", "teacher": "Dr. Ayesha Tariq", "room": "CS-1", "type": "LEC"},
            {"day": 2, "slotStart": 1, "slotSpan": 1, "course": "Operating Systems", "teacher": "Dr. Imran Shah", "room": "CS-2", "type": "LEC"},
            {"day": 2, "slotStart": 4, "slotSpan": 2, "course": "Web Dev Lab", "teacher": "Mr. Bilal Khan", "room": "Lab-1", "type": "LAB"},
            {"day": 3, "slotStart": 2, "slotSpan": 1, "course": "Computer Networks", "teacher": "Dr. Zubair Ahmed", "room": "CS-1", "type": "LEC"},
            {"day": 3, "slotStart": 3, "slotSpan": 1, "course": "Data Mining", "teacher": "Dr. Ayesha Tariq", "room": "CS-1", "type": "LEC"},
            {"day": 4, "slotStart": 1, "slotSpan": 1, "course": "Web Development", "teacher": "Mr. Bilal Khan", "room": "CS-3", "type": "LEC"},
            {"day": 4, "slotStart": 4, "slotSpan": 2, "course": "Networks Lab", "teacher": "Dr. Zubair Ahmed", "room": "Lab-3", "type": "LAB"},
        ],
        "FA24-BCS-4A": [
            {"day": 0, "slotStart": 1, "slotSpan": 1, "course": "Data Structures", "teacher": "Dr. Ahmed Khan", "room": "MS-1", "type": "LEC"},
            {"day": 0, "slotStart": 3, "slotSpan": 1, "course": "Discrete Mathematics", "teacher": "Dr. Zubair Ahmed", "room": "MS-2", "type": "LEC"},
            {"day": 0, "slotStart": 4, "slotSpan": 2, "course": "DSA Lab", "teacher": "Dr. Ahmed Khan", "room": "Lab-1", "type": "LAB"},
            {"day": 1, "slotStart": 2, "slotSpan": 1, "course": "OOP", "teacher": "Mr. Usman Malik", "room": "CS-1", "type": "LEC"},
            {"day": 1, "slotStart": 4, "slotSpan": 1, "course": "Digital Logic Design", "teacher": "Dr. Imran Shah", "room": "CS-2", "type": "LEC"},
            {"day": 2, "slotStart": 1, "slotSpan": 1, "course": "Data Structures", "teacher": "Dr. Ahmed Khan", "room": "MS-1", "type": "LEC"},
            {"day": 2, "slotStart": 2, "slotSpan": 1, "course": "Discrete Mathematics", "teacher": "Dr. Zubair Ahmed", "room": "MS-2", "type": "LEC"},
            {"day": 2, "slotStart": 4, "slotSpan": 2, "course": "OOP Lab", "teacher": "Mr. Usman Malik", "room": "Lab-2", "type": "LAB"},
            {"day": 3, "slotStart": 1, "slotSpan": 1, "course": "OOP", "teacher": "Mr. Usman Malik", "room": "CS-1", "type": "LEC"},
            {"day": 3, "slotStart": 3, "slotSpan": 1, "course": "Digital Logic Design", "teacher": "Dr. Imran Shah", "room": "CS-2", "type": "LEC"},
            {"day": 4, "slotStart": 4, "slotSpan": 2, "course": "DLD Lab", "teacher": "Dr. Imran Shah", "room": "Lab-3", "type": "LAB"},
        ],
        "FA25-BCS-2A": [
            {"day": 0, "slotStart": 1, "slotSpan": 1, "course": "Programming Fundamentals", "teacher": "Ms. Fatima Hassan", "room": "CS-1", "type": "LEC"},
            {"day": 0, "slotStart": 2, "slotSpan": 1, "course": "Calculus", "teacher": "Dr. Zubair Ahmed", "room": "MS-1", "type": "LEC"},
            {"day": 0, "slotStart": 4, "slotSpan": 2, "course": "PF Lab", "teacher": "Ms. Fatima Hassan", "room": "Lab-1", "type": "LAB"},
            {"day": 1, "slotStart": 1, "slotSpan": 1, "course": "English", "teacher": "Mr. Bilal Khan", "room": "MS-2", "type": "LEC"},
            {"day": 1, "slotStart": 3, "slotSpan": 1, "course": "Applied Physics", "teacher": "Dr. Imran Shah", "room": "CS-3", "type": "LEC"},
            {"day": 2, "slotStart": 2, "slotSpan": 1, "course": "Programming Fundamentals", "teacher": "Ms. Fatima Hassan", "room": "CS-1", "type": "LEC"},
            {"day": 2, "slotStart": 4, "slotSpan": 2, "course": "Physics Lab", "teacher": "Dr. Imran Shah", "room": "Lab-2", "type": "LAB"},
            {"day": 3, "slotStart": 1, "slotSpan": 1, "course": "Calculus", "teacher": "Dr. Zubair Ahmed", "room": "MS-1", "type": "LEC"},
            {"day": 3, "slotStart": 2, "slotSpan": 1, "course": "English", "teacher": "Mr. Bilal Khan", "room": "MS-2", "type": "LEC"},
            {"day": 4, "slotStart": 1, "slotSpan": 1, "course": "Applied Physics", "teacher": "Dr. Imran Shah", "room": "CS-3", "type": "LEC"},
            {"day": 4, "slotStart": 3, "slotSpan": 1, "course": "ICT", "teacher": "Ms. Fatima Hassan", "room": "CS-2", "type": "LEC"},
        ],
        "SP24-BBA-5A": [
            {"day": 0, "slotStart": 1, "slotSpan": 1, "course": "Financial Management", "teacher": "Dr. Ayesha Tariq", "room": "MS-1", "type": "LEC"},
            {"day": 0, "slotStart": 3, "slotSpan": 1, "course": "Marketing Management", "teacher": "Mr. Bilal Khan", "room": "MS-2", "type": "LEC"},
            {"day": 1, "slotStart": 2, "slotSpan": 1, "course": "Business Statistics", "teacher": "Dr. Zubair Ahmed", "room": "CS-1", "type": "LEC"},
            {"day": 1, "slotStart": 4, "slotSpan": 1, "course": "Human Resource Management", "teacher": "Dr. Sara Ali", "room": "MS-1", "type": "LEC"},
            {"day": 2, "slotStart": 1, "slotSpan": 1, "course": "Financial Management", "teacher": "Dr. Ayesha Tariq", "room": "MS-1", "type": "LEC"},
            {"day": 2, "slotStart": 3, "slotSpan": 1, "course": "Business Communication", "teacher": "Mr. Bilal Khan", "room": "MS-2", "type": "LEC"},
            {"day": 3, "slotStart": 2, "slotSpan": 1, "course": "Business Statistics", "teacher": "Dr. Zubair Ahmed", "room": "CS-1", "type": "LEC"},
            {"day": 3, "slotStart": 4, "slotSpan": 1, "course": "Marketing Management", "teacher": "Mr. Bilal Khan", "room": "MS-2", "type": "LEC"},
            {"day": 4, "slotStart": 1, "slotSpan": 1, "course": "Human Resource Management", "teacher": "Dr. Sara Ali", "room": "MS-1", "type": "LEC"},
            {"day": 4, "slotStart": 3, "slotSpan": 1, "course": "Business Communication", "teacher": "Mr. Bilal Khan", "room": "MS-2", "type": "LEC"},
        ],
    }
    
    return batches_data


def seed_database():
    """Seed MongoDB with sample timetable data."""
    print("=" * 60)
    print("Seeding MongoDB with Sample Timetable Data")
    print("=" * 60)
    
    store = get_timetable_store()
    
    # Connect to MongoDB
    print("\n[1] Connecting to MongoDB...")
    if not store.connect():
        print("[ERROR] Failed to connect to MongoDB")
        print("Make sure MongoDB is running and MONGODB_URI is set correctly")
        return False
    
    print("[OK] Connected to MongoDB")
    
    # Get current stats
    stats = store.get_stats()
    print(f"\n[2] Current database status:")
    print(f"    - Total entries: {stats['total_entries']}")
    print(f"    - Total batches: {stats['total_batches']}")
    
    # Create sample entries
    print("\n[3] Creating sample timetable entries...")
    batches_data = create_sample_entries()
    
    timetable_id = "Spring-2026"
    total_inserted = 0
    
    for batch_section, entries in batches_data.items():
        # Normalize batch code
        normalized_batch = normalize_batch_code(batch_section)
        
        # Check if batch already exists
        existing = store.get_batch_entries(normalized_batch, timetable_id)
        if existing:
            print(f"    [SKIP] {normalized_batch} already has {len(existing)} entries")
            continue
        
        # Add timetable_id and batch_section to each entry
        for entry in entries:
            entry["timetable_id"] = timetable_id
            entry["batch_section"] = normalized_batch
        
        # Insert entries
        count = store.insert_entries(entries)
        print(f"    [OK] {normalized_batch}: Inserted {count} entries")
        total_inserted += count
    
    # Final stats
    print(f"\n[4] Seeding complete!")
    final_stats = store.get_stats()
    print(f"    - Total entries now: {final_stats['total_entries']}")
    print(f"    - Total batches now: {final_stats['total_batches']}")
    print(f"    - Entries inserted: {total_inserted}")
    
    # List all batches
    print("\n[5] Available batches:")
    batches = store.get_all_batches()
    for batch in batches:
        print(f"    - {batch}")
    
    print("\n" + "=" * 60)
    print("Done! You can now test the timetable API.")
    print("=" * 60)
    
    return True


def clear_all_data():
    """Clear all timetable data (use with caution)."""
    print("[WARNING] This will delete ALL timetable data!")
    confirm = input("Are you sure? (type 'yes' to confirm): ")
    
    if confirm.lower() != 'yes':
        print("Aborted.")
        return
    
    store = get_timetable_store()
    store.connect()
    
    # Delete all documents
    deleted = store.collection.delete_many({})
    print(f"Deleted {deleted.deleted_count} entries")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed MongoDB with timetable data")
    parser.add_argument("--clear", action="store_true", help="Clear all data before seeding")
    parser.add_argument("--only-clear", action="store_true", help="Only clear data (don't seed)")
    
    args = parser.parse_args()
    
    if args.only_clear:
        clear_all_data()
    else:
        if args.clear:
            clear_all_data()
        seed_database()
