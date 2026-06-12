"""
Quick demo script to test the timetable system.
Run this to verify everything works correctly.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=" * 60)
    print("CUI Timetable System - Demo")
    print("=" * 60)
    
    # Test imports
    print("\n1. Testing imports...")
    try:
        from timetable_core.models import Day, Meeting, Offering, Student, Course
        from timetable_core.bitmask import meeting_to_bitmask, check_clash, mask_to_string
        print("   ✅ Core modules imported successfully")
    except ImportError as e:
        print(f"   ❌ Import error: {e}")
        return
    
    # Test bitmask operations
    print("\n2. Testing bitmask operations...")
    m1 = Meeting(Day.MONDAY, 1, 1)
    m2 = Meeting(Day.MONDAY, 1, 1)
    m3 = Meeting(Day.MONDAY, 2, 2)
    
    mask1 = meeting_to_bitmask(m1)
    mask2 = meeting_to_bitmask(m2)
    mask3 = meeting_to_bitmask(m3)
    
    print(f"   Monday Slot 1 mask: {bin(mask1)} (clash: {check_clash(mask1, mask2)})")
    print(f"   Monday Slot 2 mask: {bin(mask3)} (clash: {check_clash(mask1, mask3)})")
    
    if check_clash(mask1, mask2) and not check_clash(mask1, mask3):
        print("   ✅ Clash detection working correctly")
    else:
        print("   ❌ Clash detection error")
    
    # Test data store
    print("\n3. Testing data store...")
    try:
        from api.data_store import DataStore
        store = DataStore.get_instance()
        
        batches = store.get_all_batches()
        students = store.get_all_students()
        offerings = store.get_all_offerings()
        
        print(f"   Batches: {len(batches)}")
        print(f"   Students: {len(students)}")
        print(f"   Offerings: {len(offerings)}")
        print("   ✅ Data store working")
    except Exception as e:
        print(f"   ❌ Data store error: {e}")
    
    # Test Layer-1 suggestion
    print("\n4. Testing Layer-1 suggestion...")
    try:
        from solver.layer1_suggest import RepeaterSuggester
        
        student = store.get_student("S001")
        suggester = RepeaterSuggester(store.get_all_offerings())
        result = suggester.suggest_alternatives(student, "AI")
        
        print(f"   Query: 'AI'")
        print(f"   Matched: {result.matched_course.course_name if result.matched_course else 'None'}")
        print(f"   Feasible: {len(result.feasible_alternatives)}")
        print(f"   Conflicting: {len(result.conflicting_alternatives)}")
        print(f"   Time: {result.processing_time_ms:.2f}ms")
        print("   ✅ Layer-1 working")
    except Exception as e:
        print(f"   ❌ Layer-1 error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test Layer-2 solver (if OR-Tools available)
    print("\n5. Testing Layer-2 CP-SAT solver...")
    try:
        from solver.layer2_cpsat import RepeaterSolver, SolverStatus
        
        solver = RepeaterSolver(store.get_all_offerings(), time_limit_seconds=2.0)
        
        # Create a fresh student to test
        test_student = Student("TEST", "Test Student", "TEST-BATCH")
        result = solver.solve(test_student, ["CSC301", "CSC302"])
        
        print(f"   Status: {result.status.value}")
        print(f"   Chosen offerings: {len(result.chosen_offerings)}")
        print(f"   Time: {result.solving_time_ms:.2f}ms")
        
        if result.status in [SolverStatus.OPTIMAL, SolverStatus.FEASIBLE]:
            print("   ✅ Layer-2 working")
        else:
            print(f"   ⚠️ Layer-2 returned: {result.status.value}")
    except ImportError:
        print("   ⚠️ OR-Tools not installed (Layer-2 unavailable)")
    except Exception as e:
        print(f"   ❌ Layer-2 error: {e}")
    
    # Test HTML renderer
    print("\n6. Testing HTML renderer...")
    try:
        from renderer.html_renderer import render_batch_timetable_html
        
        offerings = store.get_offerings_by_batch("BCS-FA25-2A")
        html = render_batch_timetable_html("BCS-FA25-2A", offerings)
        
        print(f"   Generated HTML: {len(html)} characters")
        print("   ✅ HTML renderer working")
    except Exception as e:
        print(f"   ❌ HTML renderer error: {e}")
    
    # Test PDF renderer
    print("\n7. Testing PDF renderer...")
    try:
        from renderer.pdf_renderer import render_batch_timetable_pdf
        
        offerings = store.get_offerings_by_batch("BCS-FA25-2A")
        pdf_bytes = render_batch_timetable_pdf("BCS-FA25-2A", offerings)
        
        print(f"   Generated PDF: {len(pdf_bytes)} bytes")
        
        # Save demo PDF
        output_path = "demo_timetable.pdf"
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"   Saved to: {output_path}")
        print("   ✅ PDF renderer working")
    except ImportError:
        print("   ⚠️ ReportLab not installed (PDF unavailable)")
    except Exception as e:
        print(f"   ❌ PDF renderer error: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("Demo complete! To run the full application:")
    print("  python timetable_app.py")
    print("Then open: http://localhost:8000/admin/repeater")
    print("=" * 60)


if __name__ == "__main__":
    main()
