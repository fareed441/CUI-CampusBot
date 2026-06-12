# Development Setup Guide

## Project Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    YOUR MACHINE                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ┌─────────────────┐    ┌─────────────────────┐       │
│   │  Frontend       │    │  Backend (FastAPI)  │       │
│   │  Port: 5500     │───▶│  Port: 8000         │       │
│   │  Static HTML/JS │    │  API + Templates    │       │
│   └─────────────────┘    └─────────────────────┘       │
│                                                         │
│   Access via: http://YOUR_IP:5500 (frontend)           │
│               http://YOUR_IP:8000 (backend/API)        │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Option 1: VS Code Tasks (Recommended)

1. Press `Ctrl+Shift+P` → Type "Tasks: Run Task"
2. Select **"Start Full Stack"** to run both servers

Or run individually:
- **"Start Backend (FastAPI)"** - API on port 8000
- **"Start Frontend Server"** - Static files on port 5500

### Option 2: VS Code Debug (F5)

1. Press `F5` or go to Run and Debug panel
2. Select from dropdown:
   - **"Full Stack (Backend + Frontend)"** - Both servers with debugging
   - **"FastAPI Backend (Debug)"** - Backend only with breakpoints
   - **"Frontend Server (Port 5500)"** - Frontend only

### Option 3: Manual Terminal Commands

```powershell
# Terminal 1 - Backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 - Frontend
python -m http.server 5500 --directory frontend_project --bind 0.0.0.0
```

---

## Mobile Testing (Same Network)

### Step 1: Find Your Local IP
Run the VS Code task **"Show Local IP"** or:
```powershell
(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike '*Loopback*'}).IPAddress
```

### Step 2: Access from Mobile
- **Frontend:** `http://YOUR_IP:5500`
- **Backend API:** `http://YOUR_IP:8000`
- **API Docs:** `http://YOUR_IP:8000/docs`

### Step 3: Windows Firewall
If mobile can't connect, allow ports through firewall:
```powershell
# Run as Administrator
netsh advfirewall firewall add rule name="Dev Backend" dir=in action=allow protocol=TCP localport=8000
netsh advfirewall firewall add rule name="Dev Frontend" dir=in action=allow protocol=TCP localport=5500
```

---

## Configuration Files Explained

### `.vscode/settings.json`
- Python interpreter path
- Code formatting (Black)
- File exclusions for search
- Live Server root configuration

### `.vscode/launch.json`
- Debug configurations for Python
- Compound launch for full stack
- Environment file support (.env)

### `.vscode/tasks.json`
- Build tasks for servers
- Parallel server startup
- Utility tasks (Show IP, Install deps)

### `frontend_project/config.js`
- API base URL auto-detection
- Works on localhost and mobile testing
- Helper function for authenticated API calls

---

## Recommended VS Code Extensions

Install these for best experience:

```
ms-python.python              # Python support
ms-python.black-formatter     # Code formatting
ms-python.vscode-pylance      # Python IntelliSense
ritwickdey.LiveServer         # Alternative frontend server
bradlc.vscode-tailwindcss     # Tailwind CSS IntelliSense
```

---

## Development Workflow

### 1. Start Development
```
Ctrl+Shift+B → "Start Full Stack"
```

### 2. Make Backend Changes
- FastAPI auto-reloads on save
- Debug with breakpoints using F5

### 3. Make Frontend Changes
- Refresh browser manually
- Or use Live Server extension for auto-reload

### 4. Test on Mobile
- Ensure both devices on same WiFi
- Use local IP address (not localhost)
- Check firewall if issues

---

## Ports Summary

| Service          | Port | URL Example                    |
|------------------|------|--------------------------------|
| FastAPI Backend  | 8000 | http://localhost:8000          |
| Frontend Server  | 5500 | http://localhost:5500          |
| API Documentation| 8000 | http://localhost:8000/docs     |
| MongoDB          | 27017| Connection string in .env      |

---

## Directory Listing Fix

The `python -m http.server` serves `index.html` automatically when accessing a directory. If you see a directory listing:

1. Ensure `frontend_project/index.html` exists
2. Access via `http://localhost:5500/` (not a subdirectory)
3. For production, use proper web server (nginx, Apache)

---

## Troubleshooting

### Backend won't start
```powershell
# Check if port 8000 is in use
netstat -ano | findstr :8000
# Kill the process if needed
taskkill /PID <PID> /F
```

### Frontend shows directory listing
- Ensure you're accessing the root URL
- Check `index.html` exists in `frontend_project/`

### Mobile can't connect
1. Verify same WiFi network
2. Check Windows Firewall rules
3. Try disabling firewall temporarily to test

### CORS errors in browser
- Backend already has CORS middleware configured
- Clear browser cache if issues persist
