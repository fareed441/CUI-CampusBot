# 🎓 CUI CampusBot

An AI-powered multilingual university assistant developed for COMSATS University Islamabad (Vehari Campus) using Retrieval-Augmented Generation (RAG), LangChain, MongoDB Atlas, ChromaDB, and modern authentication mechanisms.

---

## 📌 Project Overview

CUI CampusBot is designed to assist students by providing instant access to university-related information through an intelligent chatbot interface.

The system retrieves information from uploaded university documents, timetables, policies, notices, and other academic resources using a RAG-based architecture.

Students can interact with the chatbot without creating an account, while administrators can securely manage the knowledge base, timetables, and notifications through a protected dashboard.

---

## ✨ Key Features

### 🤖 AI-Powered Chatbot

* Retrieval-Augmented Generation (RAG)
* Context-aware responses
* Accurate document-based answers
* Hallucination reduction using document retrieval

### 🌍 Multilingual Support

* English
* Urdu
* Roman Urdu

### 📚 Knowledge Base Management

* PDF document upload
* Automatic text extraction
* Chunk generation
* Embedding generation
* Vector storage

### 📅 Timetable Management

* Admin uploads timetable PDFs
* Automatic class code extraction
* Student timetable lookup
* Inline PDF viewing
* Timetable downloads

### 📢 Notifications System

* Fee notifications
* Semester calendar
* Midterm datesheets
* Final datesheets
* General announcements

### 🔐 Security Features

* JWT Authentication
* bcrypt Password Hashing
* Role-Based Access Control (RBAC)
* Invite-Based Admin Registration
* Protected Admin Routes

---

## 🏗 System Architecture

```text
Admin Uploads Documents
        │
        ▼
MongoDB GridFS
        │
        ▼
Text Extraction
        │
        ▼
RecursiveCharacterTextSplitter
        │
        ▼
BAAI/bge-m3 Embeddings
        │
        ▼
ChromaDB Vector Store
        │
        ▼
Student Query
        │
        ▼
Semantic Retrieval
        │
        ▼
LangChain RAG Pipeline
        │
        ▼
LLM Response Generation
```

---

## 🧠 AI & RAG Pipeline

### Document Processing Flow

1. Admin uploads PDF
2. PDF stored in MongoDB GridFS
3. Text extracted from document
4. Text preprocessing
5. Chunk generation using RecursiveCharacterTextSplitter
6. Embedding generation using BAAI/bge-m3
7. Embeddings stored in ChromaDB

### Query Processing Flow

1. Student asks question
2. Query embedding generated
3. ChromaDB similarity search
4. Relevant chunks retrieved
5. LangChain combines context
6. LLM generates final answer

---

## 🛠 Technology Stack

### Backend

* Python
* Flask
* FastAPI
* Uvicorn

### AI & NLP

* LangChain
* BAAI/bge-m3
* Llama 3.3
* RAG Architecture

### Database

* MongoDB Atlas
* GridFS
* ChromaDB

### Frontend

* HTML5
* CSS3
* JavaScript
* Tailwind CSS
* Jinja2 Templates

### Security

* JWT Authentication
* bcrypt Password Hashing
* RBAC

---

## 📂 Project Structure

```text
CUI-CampusBot/
│
├── api/
├── app/
├── database/
├── routes/
├── security/
├── services/
├── static/
├── templates/
├── tests/
│
├── app.py
├── config.py
├── rag_pipeline.py
├── embeddings.py
├── vector_store.py
│
├── requirements.txt
├── README.md
└── .env.example
```

---

## ⚙️ Installation

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/CUI-CampusBot.git
cd CUI-CampusBot
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### 3. Activate Environment

Windows:

```bash
venv\Scripts\activate
```

Linux/Mac:

```bash
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

Optional:

```bash
pip install -r requirements_timetable.txt
```

### 5. Configure Environment Variables

Create `.env`

```env
MONGO_URI=your_mongodb_uri
MONGODB_DB_NAME=cui_campusbot

JWT_SECRET=your_secret

GROQ_API_KEY=your_key
GEMINI_API_KEY=your_key

EMAIL_USERNAME=your_email
EMAIL_PASSWORD=your_password

EMBEDDING_MODEL=BAAI/bge-m3
```

### 6. Run Application

```bash
python app.py
```

---

## 👨‍🎓 Student Features

Students can:

* Use chatbot without login
* Ask questions in multiple languages
* View timetable
* Download timetable
* View notifications
* Download notifications

---

## 👨‍💼 Admin Features

Admins can:

* Upload university documents
* Manage knowledge base
* Upload timetable PDFs
* Upload notifications
* View feedback
* Manage content

---

## 👑 Super Admin Features

Super Admin can:

* Invite new admins
* Delete admins
* Manage admin accounts
* Control dashboard access

---

## 🔒 Security Implementation

* JWT-based authentication
* bcrypt password hashing
* Role-based authorization
* Protected dashboard routes
* Secure password reset workflow
* Invitation-based admin onboarding

---

## 🚀 Future Enhancements

* Voice-enabled CampusBot
* Multi-Agent Architecture
* Personalized Student Assistant
* Attendance Integration
* LMS Integration
* Mobile Application
* AI Notification Summarization

---

## 📸 Screenshots

### 🏠 Home Page

<img width="950" height="425" alt="home_page" src="https://github.com/user-attachments/assets/21a37374-4b1b-40f8-b859-9112af64d03f" />


*Landing page of CUI CampusBot providing access to chatbot services and university resources.*

---

### 🔐 Admin Login
<img width="957" height="439" alt="Login_Screen" src="https://github.com/user-attachments/assets/082ccc83-a1b3-42be-be96-0dc12126c9ca" />

*Secure administrator login page protected with JWT authentication and bcrypt password hashing.*

---

### 🤖 Chat Interface

<img width="950" height="440" alt="Chat_Interface_Screen" src="https://github.com/user-attachments/assets/7620b045-55a4-4b7d-bb8e-9c48a060fa8f" />


*Multilingual AI chatbot interface supporting English, Urdu, and Roman Urdu queries using RAG architecture.*

---

### 💬 Student Feedback System

<img width="953" height="438" alt="Feedback_Screen" src="https://github.com/user-attachments/assets/f34c499a-1fac-4f58-9bd9-cf65648bc698" />


*Students can submit ratings and feedback to improve chatbot performance and user experience.*

---

### 📊 Admin Dashboard
<img width="949" height="438" alt="Admin_Dashboard_Screen" src="https://github.com/user-attachments/assets/379e79da-2336-4234-aa32-93fce88efb0b" />


*Central administration panel displaying system statistics, document counts, feedback, and management tools.*

---

### 📚 Knowledge Base Management

<img width="946" height="440" alt="Admin_Dashboard_Screen Knowledge Base" src="https://github.com/user-attachments/assets/d856061c-deb2-4b52-9cac-33cd04b0205c" />


*View, manage, and monitor all uploaded knowledge-base documents used by the RAG chatbot.*

---

### 📄 Document Upload System
<img width="941" height="441" alt="Admin_Dashboard_Screen Document Uploading" src="https://github.com/user-attachments/assets/5230f4ee-effd-405d-9a50-bdec8c636ed0" />


*Upload university documents to MongoDB GridFS for automated text extraction, chunking, and embedding generation.*

---

### 💭 Feedback Management

<img width="941" height="445" alt="Admin_Dashboard_Screen Feedback" src="https://github.com/user-attachments/assets/2f349318-2dd7-45b6-b1ca-6c982298a3df" />


*Admin interface for reviewing and analyzing student feedback and chatbot ratings.*

---

### 📅 Timetable Upload Management

<img width="664" height="451" alt="Admin_Dashboard_Screen Timetable uploading" src="https://github.com/user-attachments/assets/0d284e18-8acc-4022-b416-9a70cf12680b" />


*Upload centralized university timetable PDFs and automatically extract available class codes.*

---

### 📢 Notification Upload Management

<img width="616" height="446" alt="Admin_Dashboard_Screen Notificaiton uploading" src="https://github.com/user-attachments/assets/62fc2844-2869-48aa-b548-134def4c1309" />


*Upload fee notices, semester calendars, datesheets, and other university announcements.*

---


### 📋 Timetable & Notifications Viewer

<img width="332" height="455" alt="timetable  and notifiction view" src="https://github.com/user-attachments/assets/f69f7087-e3e5-45d5-b4aa-71b564dca19f" />


*Unified student portal for viewing timetables, academic notifications, and downloadable resources.*


## 👨‍💻 Developer

**Fareed Anwar (FA22-BCS-099)**
**Hammad Asjad (FA22-BCS-126)**

Final Year Project

COMSATS University Islamabad – Vehari Campus

---

## 📄 License

This project is developed for educational and research purposes.
