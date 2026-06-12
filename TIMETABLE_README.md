# Clash-Free Timetable System with Repeater Resolver

A comprehensive timetable management system for COMSATS University with two-layer repeater student clash resolution.

## Features

### A) Master Timetable (Global)

- Generate/store master timetables for all batches/sections
- **Hard constraints** (never broken):
  1. No teacher overlap in same day+time
  2. No room overlap in same day+time
  3. No batch/section overlap in same day+time
  4. Lab sessions must be consecutive slots (never cross break)
  5. Room type constraints (lab courses in lab rooms)
- **Soft constraints** (optimized):
  - Minimize gaps for each batch
  - Avoid too many late slots
  - Balance teacher load

### B) Repeater Student Clash Resolver (Two Layers)

#### Layer-1: Fast Path Alternative Suggestion

- O(n) filtering using 30-bit bitmasks
- Lists ALL alternative offerings of a course
- Returns:
  - ✅ Feasible alternatives (ranked by quality)
  - ❌ Conflicting alternatives (with explicit reasons)
- **Performance**: < 200ms for typical data

#### Layer-2: CP-SAT Multi-Course Solver

- Uses Google OR-Tools CP-SAT solver
- Finds optimal combination of offerings for multiple repeat courses
- Minimizes gaps + late slots + department mismatches
- **Performance**: < 2s (configurable)

### C) Output Formats

Timetables match the exact CUI format:

- PDF output (using ReportLab)
- HTML output (responsive, printable)

Layout features:

- Header: "COMSATS Vehari Centralized Timetable (V-2)-Spring-2026"
- Slot columns with exact times:
  - Slot 1: 8:30-10:00 AM
  - Slot 2: 10:00-11:30 AM
  - Slot 3: 11:30-1:00 PM
  - **Break column**: 1:00-1:30 PM
  - Slot 4: 1:30-3:00 PM
  - Slot 5: 3:00-4:30 PM
  - Slot 6: 4:30-6:00 PM
- Merged cells for 2-hour labs
- Rotated day labels (Monday-Friday)

## Installation

### Requirements

```bash
pip install -r requirements_timetable.txt
```

Required packages:

- `fastapi>=0.100.0` - Web framework
- `uvicorn>=0.23.0` - ASGI server
- `pydantic>=2.0.0` - Data validation
- `ortools>=9.7.2996` - CP-SAT solver for Layer-2
- `reportlab>=4.0.0` - PDF generation
- `rapidfuzz>=3.0.0` - Fuzzy course matching

### Running the Application

```bash
# Start the server
python timetable_app.py

# Or with uvicorn directly
uvicorn timetable_app:app --reload --host 0.0.0.0 --port 8000
```

Access:

- **Admin UI**: http://localhost:8000/admin/repeater
- **API Docs**: http://localhost:8000/docs (Swagger)
- **Health Check**: http://localhost:8000/health

## Project Structure

```
├── timetable_core/           # Core data models and bitmask operations
│   ├── __init__.py
│   ├── models.py             # Day, Meeting, Offering, Student, etc.
│   ├── bitmask.py            # 30-bit bitmask clash detection
│   └── fuzzy_match.py        # Fuzzy course name matching
│
├── solver/                   # Clash resolution solvers
│   ├── __init__.py
│   ├── layer1_suggest.py     # Fast path alternative suggestions
│   └── layer2_cpsat.py       # CP-SAT multi-course solver
│
├── renderer/                 # Timetable output renderers
│   ├── __init__.py
│   ├── pdf_renderer.py       # PDF generation (ReportLab)
│   └── html_renderer.py      # HTML generation
│
├── api/                      # REST API endpoints
│   ├── __init__.py
│   ├── data_store.py         # In-memory data store (demo)
│   ├── timetable_api.py      # Timetable endpoints
│   └── repeater_api.py       # Repeater resolution endpoints
│
├── tests/                    # Unit tests
│   └── test_timetable.py
│
├── templates/                # HTML templates
│   └── repeater_admin.html   # Admin UI
│
├── timetable_app.py          # Main FastAPI application
└── requirements_timetable.txt
```

## API Endpoints

### Timetable API

| Method | Endpoint                             | Description                      |
| ------ | ------------------------------------ | -------------------------------- |
| GET    | `/api/timetable/batch/{batch}`       | Get batch schedule with bitmasks |
| GET    | `/api/timetable/batches`             | List all batch sections          |
| GET    | `/api/timetable/offerings`           | List offerings (with filters)    |
| POST   | `/api/timetable/render-pdf`          | Generate PDF timetable           |
| GET    | `/api/timetable/render-html/{batch}` | Generate HTML timetable          |

### Repeater API

| Method | Endpoint                                  | Description                           |
| ------ | ----------------------------------------- | ------------------------------------- |
| POST   | `/api/repeater/suggest`                   | Layer-1: Fast alternative suggestions |
| POST   | `/api/repeater/solve`                     | Layer-2: CP-SAT multi-course solver   |
| GET    | `/api/repeater/student/{id}/schedule`     | Get student schedule                  |
| POST   | `/api/repeater/student/{id}/enroll`       | Enroll in offering                    |
| DELETE | `/api/repeater/student/{id}/enroll/{oid}` | Unenroll from offering                |

## Usage Examples

### Layer-1: Find Alternatives for "AI" Course

```python
import requests

response = requests.post("http://localhost:8000/api/repeater/suggest", json={
    "student_id": "S001",
    "course_query": "AI"
})

data = response.json()
print(f"Found {data['feasible_count']} feasible alternatives")
print(f"Processing time: {data['processing_time_ms']:.1f}ms")

for alt in data['feasible_alternatives']:
    print(f"  ✅ {alt['offering']['batch_section']} - Score: {alt['score']}")
```

### Layer-2: Solve Multiple Repeat Courses

```python
response = requests.post("http://localhost:8000/api/repeater/solve", json={
    "student_id": "S001",
    "course_queries": ["AI", "Database", "OS"],
    "time_limit_seconds": 2.0
})

data = response.json()
if data['status'] in ['optimal', 'feasible']:
    print("Solution found!")
    for code, offering in data['chosen_offerings'].items():
        print(f"  {code}: {offering['batch_section']}")
```

### Generate PDF Timetable

```python
response = requests.post("http://localhost:8000/api/timetable/render-pdf", json={
    "batch_section": "BCS-FA25-2A",
    "semester": "Spring-2026"
})

with open("timetable.pdf", "wb") as f:
    f.write(response.content)
```

## Running Tests

```bash
python -m pytest tests/test_timetable.py -v
```

Tests include:

- Bitmask clash detection
- Offering merge span tests (labs)
- Layer-1 performance test (< 200ms)
- Layer-2 CP-SAT feasibility test
- PDF/HTML renderer smoke tests

## Demo Data

The system includes demo data with:

- 4 batches: BCS-FA25-2A, BCS-FA25-2B, BCS-SP26-1, BCS-FA22-8A
- 12 courses with aliases (AI, ML, DB, OS, etc.)
- 8 teachers across departments
- 8 rooms (lecture + lab)
- 3 sample students (including 1 repeater)

## Bitmask Performance

The system uses 30-bit bitmasks for ultra-fast clash detection:

- 5 days × 6 slots = 30 bits per offering
- Clash check: `(maskA & maskB) != 0` - O(1)
- Layer-1 filtering: O(n) with n offerings

Example bitmask visualization:

```
     S1  S2  S3  |  S4  S5  S6
    ----------------------------
Mon   X   .   .  |   .   .   .
Tue   .   X   .  |   .   .   .
Wed   .   .   .  |   X   X   .
Thu   .   .   .  |   .   .   .
Fri   .   .   .  |   .   .   .
```

## License

MIT License - COMSATS University Islamabad
