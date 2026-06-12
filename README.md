# CUI Campus Chatbot

A smart RAG (Retrieval-Augmented Generation) chatbot for COMSATS University Islamabad using FREE BAAI BGE embeddings and Perplexity API for generation.

## 🌟 Features

- ✅ **FREE & Unlimited** - Uses BAAI BGE embeddings (no API quotas)
- ✅ **Smart RAG System** - Retrieves relevant context before answering
- ✅ **Beautiful UI** - Modern gradient design with Tailwind CSS
- ✅ **Fast & Accurate** - Powered by Perplexity Sonar models
- ✅ **247 Documents** - Covers academics, admissions, facilities, scholarships, timetables

## 📋 Prerequisites

- Python 3.8 or higher
- Perplexity API Key
- ~200MB disk space for model and database

## 🚀 Quick Start

### 1. Clone or Download the Project

```powershell
cd "c:\Users\Fareed Bhatti\Desktop\CUI Campus bot"
```

### 2. Create Virtual Environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure Perplexity API Key

Set your Perplexity API key in PowerShell:

```powershell
$env:PPLX_API_KEY = "pplx-..."
$env:PPLX_MODEL = "sonar"   # optional: sonar | sonar-reasoning | sonar-pro | sonar-deep-research
```

Or copy `.env.example` to `.env` and fill in `PPLX_API_KEY`.

### 5. Initialize Database

```powershell
python initialize_db.py
```

This will:

- Load 247 documents from `cui_chatbot_data/`
- Download BAAI BGE model (~130MB, one-time)
- Create embeddings for all documents
- Store in local ChromaDB database

Expected output:

```
✓ Loaded 247 document chunks
✓ Successfully added 247 documents
✓ Retrieval test successful!
🎉 Ready to start the chatbot!
```

### 6. Start the Web Application

```powershell
python app.py
```

If you set the API key after starting the app, you can hot-reload without a restart:

```powershell
# In a new PowerShell, set key then call reload
$env:PPLX_API_KEY = "pplx-..."; Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/reload
```

### 7. Open in Browser

Navigate to: **http://localhost:5000**

## 🎨 Web Interface

### Features:

- 💬 Interactive chat interface
- 🎯 Suggested questions for quick start
- 🔄 Typing indicators and smooth animations
- 📚 Source/category badges (hidden by default)
- 🗑️ Clear chat history
- ⌨️ Keyboard shortcuts (Ctrl+K to focus input)

### Try These Questions:

- "What are the admission requirements?"
- "Tell me about CUI scholarships"
- "What facilities are available at CUI?"
- "Show me the timetable information"

## 📁 Project Structure

```
CUI Campus bot/
├── app.py                      # Flask web server
├── rag_pipeline_free.py        # RAG implementation (FREE embeddings)
├── vector_store_free.py        # Vector database with BAAI BGE
├── perplexity_llm.py           # Perplexity Chat Completions wrapper
├── load_cui_data.py           # Data loader with chunking
├── initialize_db.py           # Database setup script
├── config.py                  # Configuration settings
├── requirements.txt           # Python dependencies
│
├── templates/
│   └── index.html             # Beautiful web interface
│
├── static/
│   └── script.js              # Interactive frontend logic
│
├── cui_chatbot_data/          # Your data files (auto-discovered)
│   ├── *.json                 # Any JSON Q&A files
│   └── *.pdf                  # Any PDFs (e.g., Timetable.pdf)
│
├── chroma_db/                 # Vector database (auto-created)
└── venv/                      # Virtual environment
```

## 🔧 API Endpoints

### POST /api/chat

Send a message to the chatbot

**Request:**

```json
{
  "message": "What are admission requirements?"
}
```

**Response:**

```json
{
  "success": true,
  "answer": "The admission requirements include...",
  "sources": ["admission.json"], // present; hidden in UI by default
  "categories": ["Admission"]
}
```

### POST /api/clear

Clear chat history

### GET /api/status

Get system status

### GET /api/suggestions

### POST /api/reload

Re-initialize the RAG pipeline (useful after setting `PPLX_API_KEY` without restarting the server).

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/reload
```

Get suggested questions

## ⚙️ Configuration

Environment variables used by the app (see `config.py`):

- `PPLX_API_KEY`: Your Perplexity API key (required)
- `PPLX_MODEL`: Perplexity model (default: `sonar`)
- `DATA_DIRECTORY`: Data folder path (default: `cui_chatbot_data`)

View active config:

```powershell
python config.py
```

## 🔍 How It Works

### RAG Architecture:

```
User Query
    ↓
[BAAI BGE Embeddings] (FREE, local, unlimited)
    ↓
[ChromaDB Vector Search] (finds relevant documents)
    ↓
[Retrieve Top-K Documents]
    ↓
[Perplexity Sonar] (generates answer with context)
    ↓
Response to User
```

### Why BAAI BGE?

- **FREE** - No API key needed for embeddings
- **UNLIMITED** - No quotas or rate limits
- **LOCAL** - Runs on your CPU
- **HIGH QUALITY** - Top open-source model
- **FAST** - After initial download (~130MB)

### Why Perplexity?

- **Strong models** - Sonar family optimized for knowledge tasks
- **Simple API** - Chat Completions compatible
- **Flexible** - Multiple model choices and temperatures

## 🐛 Troubleshooting

### Issue: "LLM not configured" or 503 on /api/chat

**Cause:** `PPLX_API_KEY` not set. The app starts and the vector store initializes, but generation is disabled until the key is present.

**Fix:**

```powershell
$env:PPLX_API_KEY = "pplx-..."; Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/reload
```

### Issue: "Module not found" errors

**Solution:**

```powershell
pip install -r requirements.txt
```

### Issue: Database initialization fails

**Solution:**

```powershell
# Delete old database
Remove-Item -Recurse -Force chroma_db

# Reinitialize
python initialize_db.py
```

### Issue: Slow response times

**Solution:**

- First run downloads BAAI model (~130MB)
- Subsequent runs are much faster
- Embeddings are cached in database

### Issue: Deprecation warnings

**Solution:**

```powershell
pip install -U langchain-huggingface
pip install -U langchain-chroma
```

## 📊 Technical Details

### Embedding Model:

- **Model:** BAAI/bge-small-en-v1.5
- **Dimensions:** 384
- **Size:** ~130MB
- **Speed:** Fast on CPU
- **Quality:** State-of-the-art for its size

### LLM Model:

- **Model:** Perplexity Sonar (configurable via `PPLX_MODEL`)
- **Interface:** Chat Completions API
- **Temperature:** 0.7 (balanced)

### Vector Database:

- **Engine:** ChromaDB
- **Storage:** Persistent local disk
- **Documents:** 247 chunks
- **Search:** Cosine similarity

### Text Processing:

- **Strategy:** RecursiveCharacterTextSplitter
- **Chunk Size:** 1000 characters
- **Overlap:** 200 characters
- **Retrieval:** Top-5 most relevant

## 📝 Data Sources

The chatbot has knowledge about:

- ✅ Admission requirements and procedures
- ✅ Academic programs and departments
- ✅ University facilities and services
- ✅ Scholarship opportunities
- ✅ Class timetables
- ✅ General university information

## 🔐 Security Notes

- Never commit your API key to version control
- Prefer environment variables over hardcoding
- The `.gitignore` file protects sensitive data

## ☁️ MongoDB Atlas Storage Monitoring

The admin dashboard includes real-time storage monitoring for MongoDB Atlas Free Tier (M0 cluster - 512MB limit).

### Features

- **Real-time Updates**: Storage usage updates every 30 seconds
- **Visual Progress Bar**: Shows percentage of storage used
- **Warning States**:
  - 🟢 **Healthy** (< 75%): Green status, normal operation
  - 🟡 **Warning** (75-89%): Yellow warning banner, consider cleanup
  - 🔴 **Critical** (≥ 90%): Red alert, delete documents immediately

### API Endpoint

```
GET /api/atlas-storage
```

Returns:

```json
{
  "limitBytes": 536870912,
  "usedBytes": 123456,
  "leftBytes": 536747456,
  "usedMB": 0.12,
  "leftMB": 511.88,
  "percentUsed": 0.02,
  "status": "healthy",
  "databasesChecked": ["cui_campusbot_db"],
  "updatedAt": "2026-02-12T10:30:00.000Z"
}
```

### Environment Variables

| Variable          | Description                     | Required                            |
| ----------------- | ------------------------------- | ----------------------------------- |
| `MONGODB_URI`     | MongoDB Atlas connection string | Yes                                 |
| `MONGODB_DB_NAME` | Database name (fallback)        | No (defaults to `cui_campusbot_db`) |

### Storage Calculation

Storage is calculated as: `usedBytes = dataSize + indexSize`

This matches MongoDB Atlas M0 billing methodology where storage = documents + indexes.

### Optional: Atlas Alerts

To receive email alerts when storage is running low:

1. Go to MongoDB Atlas → Project → Alerts
2. Create new alert with condition: "Logical Size" approaching limit
3. Set threshold: 400MB (78%) for warning, 460MB (90%) for critical
4. Configure email notification

## 🚀 Deployment (Optional)

For a simple deployment on Windows, run with a process manager or use a production WSGI server compatible with your host. Ensure `PPLX_API_KEY` is set in the environment before starting the app.

## 📈 Performance

- **Database Init:** ~2-3 minutes (one-time)
- **Query Response:** ~2-5 seconds
- **Embedding Speed:** ~50 docs/second
- **Memory Usage:** ~500MB with model loaded
- **Disk Usage:** ~200MB (model + database)

## 🤝 Contributing

To add more data:

1. Add any `.json` or `.pdf` files to `cui_chatbot_data/`
2. Run: `python initialize_db.py`
3. Reload: `Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/reload` (or restart)

## 📄 License

This project is for educational purposes.

## 💡 Tips

- Start with suggested questions to see how it works
- Be specific in your questions for better answers
- The bot maintains conversation context
- Clear history if you want to start fresh
- Check sources to verify information

## 🎯 Next Steps

1. ✅ Setup complete
2. ✅ Database initialized
3. 🚀 Start chatting at http://localhost:5000
4. 🔑 Set `PPLX_API_KEY` and call `/api/reload` if needed
5. 📚 Add more data as needed
6. 🎨 Customize the UI in `templates/index.html`
7. ⚙️ Adjust settings in `config.py`

---

**Made with ❤️ for COMSATS University Islamabad**

Need help? Check the troubleshooting section or review the console output for detailed error messages.
