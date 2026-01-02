import os
import time
import json
import shutil
from datetime import datetime
from typing import Optional, Dict, List
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader
from dotenv import load_dotenv
import docx

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_groq import ChatGroq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY not set")

app = FastAPI(title="DocuChat AI - Production")

# CORS - Allow all origins for now
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
UPLOAD_DIR = "uploads"
HISTORY_DIR = "history"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# ---------------------------------------------------------
# âœ… CHANGED: Global State is now per-user dictionaries
# ---------------------------------------------------------
# Key = user_id, Value = VectorStore
user_vector_stores: Dict[str, FAISS] = {}

# Key = user_id, Value = Dict of uploaded files
user_files: Dict[str, Dict] = {}

# Key = user_id, Value = Dict of chat sessions
user_sessions: Dict[str, Dict] = {}

# Initialize LLM
llm = None
if GROQ_API_KEY:
    try:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=GROQ_API_KEY,
            temperature=0.7,
        )
        print("âœ… Groq LLM initialized")
    except Exception as e:
        print(f"âŒ Error initializing LLM: {e}")

# Initialize FastEmbed
print("ðŸ”„ Loading embeddings model...")
try:
    embeddings = FastEmbedEmbeddings()
    print("âœ… Embeddings loaded successfully!")
except Exception as e:
    print(f"âŒ Error loading embeddings: {e}")
    embeddings = None

# âœ… CHANGED: Added user_id to request model
class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    user_id: str  # <--- Added this field

def extract_pdf(path: str) -> str:
    """Extract text from PDF file"""
    try:
        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        print(f"PDF extraction error: {e}")
        return ""

def extract_docx(path: str) -> str:
    """Extract text from DOCX file"""
    try:
        doc = docx.Document(path)
        text = "\n".join([p.text for p in doc.paragraphs])
        return text
    except Exception as e:
        print(f"DOCX extraction error: {e}")
        return ""

# âœ… CHANGED: Save session now includes user_id check
def save_session(user_id: str, sid: str):
    """Save session to disk"""
    if user_id in user_sessions and sid in user_sessions[user_id]:
        try:
            # We save the user_id inside the JSON so we know who owns it
            data = user_sessions[user_id][sid]
            data['user_id'] = user_id 
            
            filepath = os.path.join(HISTORY_DIR, f"{sid}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving session {sid}: {e}")

# âœ… CHANGED: Load sessions sorts them into user buckets
def load_sessions():
    """Load all sessions from disk"""
    global user_sessions
    if not os.path.exists(HISTORY_DIR):
        return
    
    for filename in os.listdir(HISTORY_DIR):
        if filename.endswith('.json'):
            try:
                filepath = os.path.join(HISTORY_DIR, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    sid = data.get('id')
                    owner = data.get('user_id', 'unknown_user') # Default if old file
                    
                    if owner not in user_sessions:
                        user_sessions[owner] = {}
                    
                    user_sessions[owner][sid] = data
            except Exception as e:
                print(f"Error loading session {filename}: {e}")

# Load existing sessions on startup
load_sessions()
print(f"ðŸ“š Loaded existing sessions into memory")

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "DocuChat AI Multi-User",
        "active_users": len(user_sessions),
        "llm_ready": llm is not None,
        "embeddings_ready": embeddings is not None
    }

@app.get("/health")
def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "groq_configured": GROQ_API_KEY is not None,
        "llm_initialized": llm is not None,
        "embeddings_initialized": embeddings is not None,
    }

# âœ… CHANGED: Read user-id from Header
# FIND THIS FUNCTION IN YOUR CODE AND REPLACE IT
@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...), 
    user_id: Optional[str] = Header(None, alias="user-id")
):
    if not user_id:
        raise HTTPException(400, "User ID header missing")

    if not embeddings:
        raise HTTPException(500, "Embeddings not initialized")
    
    # 1. Validate File Name
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(400, "Only PDF and DOCX files are supported")
    
    user_dir = os.path.join(UPLOAD_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)

    file_id = f"{int(time.time() * 1000)}_{file.filename}"
    file_path = os.path.join(user_dir, file_id)
    
    try:
        # 2. READ CONTENT & CHECK SIZE (10MB Limit)
        content = await file.read()
        
        if len(content) > 10 * 1024 * 1024: # 10MB Limit
            raise HTTPException(400, "File is too large (Max 10MB)")
            
        with open(file_path, "wb") as f:
            f.write(content)
        
        # 3. EXTRACT TEXT
        if file.filename.lower().endswith('.pdf'):
            text = extract_pdf(file_path)
        else:
            text = extract_docx(file_path)
        
        # 4. ROBUST TEXT CHECK (Detects Scanned PDFs)
        if not text or len(text.strip()) < 50:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(400, "Could not extract text. File might be an image/scanned PDF.")
        
        # 5. PROCESS EMBEDDINGS
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            length_function=len
        )
        chunks = text_splitter.split_text(text)
        
        if not chunks:
             raise HTTPException(400, "File contains no readable text chunks.")

        metadatas = [{"source": file.filename, "file_id": file_id} for _ in chunks]
        
        if user_id not in user_vector_stores:
            user_vector_stores[user_id] = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
        else:
            new_store = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
            user_vector_stores[user_id].merge_from(new_store)
        
        # Update File List
        if user_id not in user_files:
            user_files[user_id] = {}

        user_files[user_id][file_id] = {
            "filename": file.filename,
            "file_id": file_id,
            "chunks": len(chunks),
            "size": len(content),
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "file_id": file_id,
            "chunks": len(chunks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"Upload error: {e}")
        raise HTTPException(500, f"Error processing file: {str(e)}")

# âœ… CHANGED: List only user's files
@app.get("/files")
def list_files(user_id: Optional[str] = Header(None, alias="user-id")):
    """Get list of all uploaded files for this user"""
    if not user_id or user_id not in user_files:
        return {"files": [], "total": 0}
        
    return {
        "files": list(user_files[user_id].values()),
        "total": len(user_files[user_id])
    }

# âœ… CHANGED: Delete from user's list
@app.delete("/files/{file_id}")
def delete_file(file_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    """Delete a specific file"""
    if not user_id or user_id not in user_files:
        return {"message": "File not found"}

    if file_id in user_files[user_id]:
        del user_files[user_id][file_id]
        
        # Delete actual file
        file_path = os.path.join(UPLOAD_DIR, user_id, file_id)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")
            
        # Note: Vector store cleanup is skipped for simplicity, but file is gone from UI
    
    return {"message": "File deleted", "ok": True}

# âœ… CHANGED: Ask checks user's context
@app.post("/ask")
async def ask_question(request: QuestionRequest):
    """Ask a question about uploaded documents"""
    user_id = request.user_id # Get from body
    
    # Initialize session storage for user if needed
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    
    # Validate prerequisites
    store = user_vector_stores.get(user_id)
    if not store:
        # Return polite empty response if no docs
        return {
            "answer": "Please upload a document first.",
            "sources": [],
            "session_id": request.session_id
        }
    
    if not llm:
        raise HTTPException(500, "LLM not configured. Please set GROQ_API_KEY")
    
    # Handle session
    if request.session_id and request.session_id in user_sessions[user_id]:
        session_id = request.session_id
    else:
        session_id = f"s{int(time.time() * 1000)}"
        user_sessions[user_id][session_id] = {
            "id": session_id,
            "user_id": user_id,
            "messages": [],
            "title": "New Chat",
            "created": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    
    try:
        # Search for relevant documents in USER'S store
        docs = store.similarity_search(request.question, k=4)
        
        if not docs:
            return {
                "answer": "I couldn't find relevant information in the uploaded documents.",
                "sources": [],
                "session_id": session_id
            }
        
        # Build context and sources
        context = "\n\n".join([doc.page_content for doc in docs])
        sources = list(set([doc.metadata.get('source', 'Unknown') for doc in docs]))
        
        # Get conversation history
        history = ""
        current_session = user_sessions[user_id][session_id]
        if "messages" in current_session:
            for msg in current_session["messages"][-4:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                history += f"{role}: {msg['content']}\n"
        
        # Create prompt
        prompt = f"""You are an intelligent AI assistant. 

Instructions:
1. If the user asks for a SUMMARY, identify the main TOPICS and CONCEPTS in the documents. Do not just list the questions found in the text.
2. If the user asks a specific question, answer it strictly based on the provided Context.
3. If the answer is not in the context, say "I cannot find that information in the documents."

Context from documents:
{context}

Conversation history:
{history}

User question: {request.question}

Answer:"""
        
        # Get AI response
        response = llm.invoke(prompt)
        answer = response.content
        
        # Save to history
        current_session["messages"].append({
            "role": "user",
            "content": request.question,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        current_session["messages"].append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # Update session title
        if len(current_session["messages"]) == 2:
            current_session["title"] = request.question[:50] + ("..." if len(request.question) > 50 else "")
        
        save_session(user_id, session_id)
        
        return {
            "answer": answer,
            "sources": sources,
            "session_id": session_id,
            "status": "success"
        }
        
    except Exception as e:
        print(f"Ask error: {e}")
        raise HTTPException(500, f"Error processing question: {str(e)}")

# âœ… CHANGED: List only user's sessions
@app.get("/sessions")
def get_sessions(user_id: Optional[str] = Header(None, alias="user-id")):
    """Get all chat sessions for user"""
    if not user_id or user_id not in user_sessions:
        return {"sessions": [], "total": 0}

    sessions = list(user_sessions[user_id].values())
    sessions.sort(key=lambda x: x.get('created', ''), reverse=True)
    return {"sessions": sessions, "total": len(sessions)}

@app.get("/sessions/{session_id}")
def get_session(session_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    """Get a specific session"""
    if not user_id or user_id not in user_sessions:
        raise HTTPException(404, "Session not found")

    if session_id not in user_sessions[user_id]:
        raise HTTPException(404, "Session not found")
        
    return user_sessions[user_id][session_id]

# âœ… CHANGED: Create session for specific user
@app.post("/sessions/new")
def create_new_session(request: QuestionRequest):
    """Create a new chat session"""
    # We reuse QuestionRequest just to get the user_id from body easily
    user_id = request.user_id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {}

    session_id = f"s{int(time.time() * 1000)}"
    user_sessions[user_id][session_id] = {
        "id": session_id,
        "user_id": user_id,
        "messages": [],
        "title": "New Chat",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    save_session(user_id, session_id)
    
    return {
        "session_id": session_id,
        "message": "New session created"
    }

# âœ… CHANGED: Delete session
@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    """Delete a chat session"""
    if user_id in user_sessions and session_id in user_sessions[user_id]:
        del user_sessions[user_id][session_id]
        
        # Delete session file
        filepath = os.path.join(HISTORY_DIR, f"{session_id}.json")
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting session file: {e}")
    
    return {"message": "Session deleted", "ok": True}

# âœ… CHANGED: Clear only user's files
# ✅ UPDATED: Clear BOTH Files and Chat History
# FIND THIS FUNCTION AT THE BOTTOM AND REPLACE IT
@app.delete("/clear")
def clear_all_data(user_id: Optional[str] = Header(None, alias="user-id")):
    if not user_id:
        return {"ok": False}

    # Clear Memory
    if user_id in user_vector_stores:
        del user_vector_stores[user_id]
    if user_id in user_files:
        del user_files[user_id]
    
    # Clear Disk (Files)
    user_dir = os.path.join(UPLOAD_DIR, user_id)
    try:
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            os.makedirs(user_dir, exist_ok=True)
    except Exception as e:
        print(f"Error clearing user dir: {e}")

    # Clear Disk (History) - This was missing in older versions
    if user_id in user_sessions:
        for sid in list(user_sessions[user_id].keys()):
            path = os.path.join(HISTORY_DIR, f"{sid}.json")
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                print(f"Error deleting session {sid}: {e}")
        
        del user_sessions[user_id]
    
    return {"message": "All data cleared", "ok": True}
# For Render deployment
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)