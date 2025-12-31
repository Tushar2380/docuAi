import os
import time
import json
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader
from dotenv import load_dotenv
import docx

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

# ---------------------------------------------------------
# ✅ CHANGED: Switched to FastEmbed (Lightweight for Render)
# ---------------------------------------------------------
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

# Global State
vector_store = None
uploaded_files = {}
chat_sessions = {}
current_session_id = None

# Initialize LLM
llm = None
if GROQ_API_KEY:
    try:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            api_key=GROQ_API_KEY,
            temperature=0.7,
        )
        print("✅ Groq LLM initialized")
    except Exception as e:
        print(f"❌ Error initializing LLM: {e}")

# ---------------------------------------------------------
# ✅ CHANGED: Initialize FastEmbed (No sentence_transformers needed)
# ---------------------------------------------------------
print("🔄 Loading embeddings model...")
try:
    embeddings = FastEmbedEmbeddings()
    print("✅ Embeddings loaded successfully!")
except Exception as e:
    print(f"❌ Error loading embeddings: {e}")
    embeddings = None

class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

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

def save_session(sid: str):
    """Save session to disk"""
    if sid in chat_sessions:
        try:
            filepath = os.path.join(HISTORY_DIR, f"{sid}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(chat_sessions[sid], f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving session {sid}: {e}")

def load_sessions():
    """Load all sessions from disk"""
    global chat_sessions
    if not os.path.exists(HISTORY_DIR):
        return
    
    for filename in os.listdir(HISTORY_DIR):
        if filename.endswith('.json'):
            try:
                filepath = os.path.join(HISTORY_DIR, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'id' in data:
                        chat_sessions[data['id']] = data
            except Exception as e:
                print(f"Error loading session {filename}: {e}")

# Load existing sessions on startup
load_sessions()
print(f"📚 Loaded {len(chat_sessions)} existing sessions")

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "DocuChat AI",
        "files": len(uploaded_files),
        "sessions": len(chat_sessions),
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
        "vector_store_loaded": vector_store is not None,
        "total_files": len(uploaded_files),
        "total_sessions": len(chat_sessions)
    }

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload and process PDF/DOCX file"""
    global vector_store, uploaded_files
    
    if not embeddings:
        raise HTTPException(500, "Embeddings not initialized")
    
    # Validate file type
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(400, "Only PDF and DOCX files are supported")
    
    file_id = f"{int(time.time() * 1000)}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)
    
    try:
        # Save uploaded file
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Extract text based on file type
        if file.filename.lower().endswith('.pdf'):
            text = extract_pdf(file_path)
        else:
            text = extract_docx(file_path)
        
        # Validate text extraction
        if not text or len(text.strip()) < 10:
            os.remove(file_path)
            raise HTTPException(400, "Could not extract text from file or file is empty")
        
        # Split text into chunks
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            length_function=len
        )
        chunks = text_splitter.split_text(text)
        
        # Create metadata for each chunk
        metadatas = [{"source": file.filename, "file_id": file_id} for _ in chunks]
        
        print(f"📄 Processing {file.filename}: {len(chunks)} chunks")
        
        # Create or merge vector store
        if vector_store is None:
            vector_store = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
            print("✅ Created new vector store")
        else:
            new_store = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
            vector_store.merge_from(new_store)
            print("✅ Merged into existing vector store")
        
        # Store file metadata
        uploaded_files[file_id] = {
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
            "chunks": len(chunks),
            "total_files": len(uploaded_files)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"Upload error: {e}")
        raise HTTPException(500, f"Error processing file: {str(e)}")

@app.get("/files")
def list_files():
    """Get list of all uploaded files"""
    return {
        "files": list(uploaded_files.values()),
        "total": len(uploaded_files)
    }

@app.delete("/files/{file_id}")
def delete_file(file_id: str):
    """Delete a specific file"""
    if file_id in uploaded_files:
        del uploaded_files[file_id]
        file_path = os.path.join(UPLOAD_DIR, file_id)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")
    
    return {"message": "File deleted", "ok": True}

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    """Ask a question about uploaded documents"""
    global current_session_id
    
    # Validate prerequisites
    if not vector_store:
        raise HTTPException(400, "Please upload documents first")
    
    if not llm:
        raise HTTPException(500, "LLM not configured. Please set GROQ_API_KEY")
    
    # Handle session
    if request.session_id:
        session_id = request.session_id
        if session_id not in chat_sessions:
            session_id = f"s{int(time.time() * 1000)}"
            chat_sessions[session_id] = {
                "id": session_id,
                "messages": [],
                "title": "New Chat",
                "created": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
    else:
        if current_session_id and current_session_id in chat_sessions:
            session_id = current_session_id
        else:
            session_id = f"s{int(time.time() * 1000)}"
            chat_sessions[session_id] = {
                "id": session_id,
                "messages": [],
                "title": "New Chat",
                "created": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
    
    current_session_id = session_id
    
    try:
        # Search for relevant documents
        docs = vector_store.similarity_search(request.question, k=4)
        
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
        if "messages" in chat_sessions[session_id]:
            for msg in chat_sessions[session_id]["messages"][-4:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                history += f"{role}: {msg['content']}\n"
        
        # Create prompt
        prompt = f"""You are a helpful AI assistant. Answer the question based on the provided context.

Context from documents:
{context}

Conversation history:
{history}

User question: {request.question}

Provide a clear, well-formatted answer. At the end, mention the source document(s).

Answer:"""
        
        # Get AI response
        response = llm.invoke(prompt)
        answer = response.content
        
        # Initialize messages if needed
        if "messages" not in chat_sessions[session_id]:
            chat_sessions[session_id]["messages"] = []
        
        # Save to history
        chat_sessions[session_id]["messages"].append({
            "role": "user",
            "content": request.question,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        chat_sessions[session_id]["messages"].append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        # Update session title
        if len(chat_sessions[session_id]["messages"]) == 2:
            chat_sessions[session_id]["title"] = request.question[:50] + ("..." if len(request.question) > 50 else "")
        
        save_session(session_id)
        
        return {
            "answer": answer,
            "sources": sources,
            "session_id": session_id,
            "status": "success"
        }
        
    except Exception as e:
        print(f"Ask error: {e}")
        raise HTTPException(500, f"Error processing question: {str(e)}")

@app.get("/sessions")
def get_sessions():
    """Get all chat sessions"""
    sessions = list(chat_sessions.values())
    sessions.sort(key=lambda x: x.get('created', ''), reverse=True)
    return {"sessions": sessions, "total": len(sessions)}

@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    """Get a specific session"""
    if session_id not in chat_sessions:
        raise HTTPException(404, "Session not found")
    return chat_sessions[session_id]

@app.post("/sessions/new")
def create_new_session():
    """Create a new chat session"""
    global current_session_id
    
    session_id = f"s{int(time.time() * 1000)}"
    chat_sessions[session_id] = {
        "id": session_id,
        "messages": [],
        "title": "New Chat",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
    current_session_id = session_id
    save_session(session_id)
    
    return {
        "session_id": session_id,
        "message": "New session created"
    }

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """Delete a chat session"""
    global current_session_id
    
    if session_id in chat_sessions:
        del chat_sessions[session_id]
        
        # Delete session file
        filepath = os.path.join(HISTORY_DIR, f"{session_id}.json")
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting session file: {e}")
    
    if current_session_id == session_id:
        current_session_id = None
    
    return {"message": "Session deleted", "ok": True}

@app.delete("/clear")
def clear_all_files():
    """Clear all uploaded files"""
    global vector_store, uploaded_files
    
    vector_store = None
    uploaded_files = {}
    
    # Clear upload directory
    for filename in os.listdir(UPLOAD_DIR):
        try:
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting file: {e}")
    
    return {"message": "All files cleared", "ok": True}

# For Render deployment
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)