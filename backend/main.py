import os
import time
import json
import shutil
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader
from dotenv import load_dotenv
import docx

# --- ROBUST IMPORT SECTION ---

from langchain_text_splitters import RecursiveCharacterTextSplitter


from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_groq import ChatGroq

# Load environment variables
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file")

app = FastAPI(title="DocuChat AI - Robust API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
UPLOAD_DIR = "uploads"
HISTORY_DIR = "chat_history"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# Global State
vector_store = None
uploaded_files = {}
chat_sessions = {}
current_session_id = None

# --- AI Configuration ---
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    api_key=GROQ_API_KEY,
    temperature=0.5,
)

print("Loading embedding model...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)
print("Embedding model loaded!")

# --- Data Models ---
class QuestionRequest(BaseModel):
    question: str
    session_id: str = None

# --- Helper Functions ---

def extract_text_from_pdf(file_path: str) -> str:
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        print(f"PDF Extraction Error: {e}")
        return ""

def extract_text_from_docx(file_path: str) -> str:
    try:
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs])
        return text
    except Exception as e:
        print(f"DOCX Extraction Error: {e}")
        return ""

def save_session(session_id: str):
    if session_id in chat_sessions:
        path = os.path.join(HISTORY_DIR, f"{session_id}.json")
        with open(path, 'w') as f:
            json.dump(chat_sessions[session_id], f, indent=2)

def load_session_from_disk(session_id: str):
    """Try to load a specific session from disk if not in memory"""
    global chat_sessions
    path = os.path.join(HISTORY_DIR, f"{session_id}.json")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                chat_sessions[data['id']] = data
                return True
        except Exception as e:
            print(f"Error loading session {session_id}: {e}")
    return False

def load_all_sessions():
    global chat_sessions
    if os.path.exists(HISTORY_DIR):
        for filename in os.listdir(HISTORY_DIR):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(HISTORY_DIR, filename), 'r') as f:
                        data = json.load(f)
                        chat_sessions[data['id']] = data
                except Exception as e:
                    print(f"Error loading session {filename}: {e}")

load_all_sessions()

def format_chat_history(messages: List[dict], limit: int = 6) -> str:
    recent = messages[-limit:]
    formatted = ""
    for msg in recent:
        role = "User" if msg["role"] == "user" else "Assistant"
        formatted += f"{role}: {msg['content']}\n"
    return formatted

# --- API Routes ---

@app.get("/")
async def root():
    return {"status": "healthy", "files": len(uploaded_files)}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    global vector_store, uploaded_files

    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(400, "Only PDF and DOCX files are supported")

    file_id = f"{int(time.time())}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        if file.filename.lower().endswith('.pdf'):
            text = extract_text_from_pdf(file_path)
        else:
            text = extract_text_from_docx(file_path)

        if not text or len(text.strip()) < 10:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(400, "File is empty or unreadable.")

        # Chunking
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_text(text)
        
        metadatas = [{"source": file.filename, "file_id": file_id} for _ in chunks]

        if vector_store is None:
            vector_store = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
        else:
            vector_store.add_texts(chunks, metadatas=metadatas)

        uploaded_files[file_id] = {
            "filename": file.filename,
            "file_id": file_id,
            "chunks": len(chunks)
        }

        return {"message": "Success", "filename": file.filename}

    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(500, f"Server Error: {str(e)}")

@app.get("/files")
async def list_files():
    return {"files": list(uploaded_files.values())}

@app.delete("/files/{file_id}")
async def delete_file(file_id: str):
    if file_id in uploaded_files:
        del uploaded_files[file_id]
        path = os.path.join(UPLOAD_DIR, file_id)
        if os.path.exists(path):
            os.remove(path)
    return {"status": "deleted"}

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    global current_session_id
    
    if not vector_store:
        raise HTTPException(400, "Please upload a document first.")

    # 1. Determine Session ID
    session_id = request.session_id or current_session_id
    
    # 2. Try to recover session from disk if not in memory (Fixes "New Chat" issue on restart)
    if session_id and session_id not in chat_sessions:
        load_session_from_disk(session_id)

    # 3. Create NEW session only if ID is invalid or missing
    if not session_id or session_id not in chat_sessions:
        session_id = f"session_{int(time.time())}"
        chat_sessions[session_id] = {
            "id": session_id,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "messages": [],
            "title": "New Chat"
        }
        current_session_id = session_id

    try:
        # Retrieve Context
        docs = vector_store.similarity_search(request.question, k=5)
        context_text = "\n\n".join([f"[From {d.metadata.get('source', 'Unknown')}]: {d.page_content}" for d in docs])
        sources = list(set([d.metadata.get('source', 'Unknown') for d in docs]))

        # Get History
        history_text = format_chat_history(chat_sessions[session_id]["messages"])

        # Construct Prompt
        prompt = f"""You are an intelligent assistant analyzing uploaded documents.
        
        History:
        {history_text}
        
        Context:
        {context_text}
        
        User Question: {request.question}
        
        Answer based on the Context. Use History to understand references like "it" or "previous".
        """
        
        response = llm.invoke(prompt)
        answer = response.content

        # Save to History
        chat_sessions[session_id]["messages"].append({
            "role": "user", "content": request.question
        })
        chat_sessions[session_id]["messages"].append({
            "role": "assistant", "content": answer, "sources": sources
        })
        
        if len(chat_sessions[session_id]["messages"]) == 2:
            chat_sessions[session_id]["title"] = request.question[:40] + "..."
            
        save_session(session_id)
        
        return {
            "answer": answer,
            "sources": sources,
            "session_id": session_id
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/sessions")
async def get_sessions():
    sessions = list(chat_sessions.values())
    sessions.sort(key=lambda x: x['created_at'], reverse=True)
    return {"sessions": sessions}

@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    if session_id not in chat_sessions:
        # Try load from disk one last time
        if load_session_from_disk(session_id):
            return chat_sessions[session_id]
        raise HTTPException(404, "Session not found")
    return chat_sessions[session_id]

@app.post("/sessions/new")
async def new_session():
    global current_session_id
    session_id = f"session_{int(time.time())}"
    chat_sessions[session_id] = {
        "id": session_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "messages": [],
        "title": "New Chat"
    }
    current_session_id = session_id # FIX: Update global ID
    save_session(session_id)
    return {"session_id": session_id}

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    global current_session_id
    if session_id in chat_sessions:
        del chat_sessions[session_id]
        path = os.path.join(HISTORY_DIR, f"{session_id}.json")
        if os.path.exists(path):
            os.remove(path)
    if current_session_id == session_id:
        current_session_id = None
    return {"status": "deleted"}

@app.delete("/clear")
async def clear_all_data():
    global vector_store, uploaded_files, chat_sessions, current_session_id
    vector_store = None
    uploaded_files = {}
    chat_sessions = {}
    current_session_id = None
    
    for folder in [UPLOAD_DIR, HISTORY_DIR]:
        if os.path.exists(folder):
            for filename in os.listdir(folder):
                try:
                    os.remove(os.path.join(folder, filename))
                except: pass
    return {"message": "All data cleared"}

@app.get("/status")
async def get_status():
    return {
        "current_session": current_session_id,
        "files_count": len(uploaded_files),
        "files": [f["filename"] for f in uploaded_files.values()]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)