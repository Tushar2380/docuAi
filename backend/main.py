import os
import time
import json
from datetime import datetime
from typing import Optional
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

app = FastAPI(title="DocuChat AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
HISTORY_DIR = "history"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)

# User-specific storage
user_vector_stores = {}
user_files = {}
user_sessions = {}

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
        print(f"❌ LLM Error: {e}")

print("🔄 Loading embeddings...")
try:
    embeddings = FastEmbedEmbeddings()
    print("✅ Embeddings ready!")
except Exception as e:
    print(f"❌ Embeddings Error: {e}")
    embeddings = None

class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    user_id: str

def extract_pdf(path: str) -> str:
    try:
        reader = PdfReader(path)
        return "\n".join([p.extract_text() or "" for p in reader.pages])
    except Exception as e:
        print(f"PDF error: {e}")
        return ""

def extract_docx(path: str) -> str:
    try:
        doc = docx.Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        print(f"DOCX error: {e}")
        return ""

def save_session(user_id: str, sid: str):
    if user_id in user_sessions and sid in user_sessions[user_id]:
        try:
            data = user_sessions[user_id][sid]
            data['user_id'] = user_id
            with open(f"{HISTORY_DIR}/{sid}.json", 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Session save error: {e}")

def load_sessions():
    global user_sessions
    if not os.path.exists(HISTORY_DIR):
        return
    
    for filename in os.listdir(HISTORY_DIR):
        if filename.endswith('.json'):
            try:
                with open(f"{HISTORY_DIR}/{filename}") as f:
                    data = json.load(f)
                    owner = data.get('user_id', 'unknown')
                    if owner not in user_sessions:
                        user_sessions[owner] = {}
                    user_sessions[owner][data['id']] = data
            except Exception as e:
                print(f"Load error: {e}")

load_sessions()

@app.get("/")
def root():
    return {
        "status": "online",
        "service": "DocuChat AI",
        "llm_ready": llm is not None,
        "embeddings_ready": embeddings is not None
    }

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), user_id: Optional[str] = Header(None, alias="user-id")):
    if not user_id:
        raise HTTPException(400, "User ID required")
    
    if not embeddings:
        raise HTTPException(500, "Embeddings not initialized")
    
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(400, "Only PDF/DOCX supported")
    
    user_dir = os.path.join(UPLOAD_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)
    
    file_id = f"{int(time.time() * 1000)}_{file.filename}"
    file_path = os.path.join(user_dir, file_id)
    
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        text = extract_pdf(file_path) if file_path.endswith('.pdf') else extract_docx(file_path)
        
        if len(text.strip()) < 10:
            os.remove(file_path)
            raise HTTPException(400, "Empty file")
        
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
        chunks = splitter.split_text(text)
        metas = [{"source": file.filename, "file_id": file_id} for _ in chunks]
        
        print(f"📄 Processing {file.filename} for user {user_id}: {len(chunks)} chunks")
        
        # CRITICAL FIX: Proper vector store merging
        new_store = FAISS.from_texts(chunks, embeddings, metadatas=metas)
        
        if user_id not in user_vector_stores or user_vector_stores[user_id] is None:
            user_vector_stores[user_id] = new_store
            print(f"✅ Created new store for {user_id}")
        else:
            # Merge into existing store
            user_vector_stores[user_id].merge_from(new_store)
            print(f"✅ Merged into existing store for {user_id}")
        
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
            "message": "Success",
            "filename": file.filename,
            "file_id": file_id,
            "chunks": len(chunks),
            "total_files": len(user_files[user_id])
        }
    
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"Upload error: {e}")
        raise HTTPException(500, str(e))

@app.get("/files")
def list_files(user_id: Optional[str] = Header(None, alias="user-id")):
    if not user_id or user_id not in user_files:
        return {"files": [], "total": 0}
    return {"files": list(user_files[user_id].values()), "total": len(user_files[user_id])}

@app.delete("/files/{file_id}")
def delete_file(file_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    if user_id in user_files and file_id in user_files[user_id]:
        del user_files[user_id][file_id]
        try:
            os.remove(f"{UPLOAD_DIR}/{user_id}/{file_id}")
        except:
            pass
    return {"ok": True}

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    user_id = request.user_id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    
    store = user_vector_stores.get(user_id)
    
    # CRITICAL FIX: Handle greetings without documents
    greetings = ['hi', 'hello', 'hey', 'hola', 'greetings', 'good morning', 'good evening']
    is_greeting = request.question.lower().strip() in greetings
    
    if is_greeting:
        # Handle greetings specially
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
        
        greeting_response = "Hello! 👋 I'm DocuChat AI, your document assistant. Upload a PDF or DOCX file and I'll help you understand it by answering your questions!"
        
        user_sessions[user_id][session_id]["messages"].append({
            "role": "user",
            "content": request.question,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        user_sessions[user_id][session_id]["messages"].append({
            "role": "assistant",
            "content": greeting_response,
            "sources": [],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        save_session(user_id, session_id)
        
        return {
            "answer": greeting_response,
            "sources": [],
            "session_id": session_id,
            "status": "success"
        }
    
    if not store:
        return {
            "answer": "Please upload a document first so I can help you!",
            "sources": [],
            "session_id": request.session_id
        }
    
    if not llm:
        raise HTTPException(500, "LLM not configured")
    
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
        # CRITICAL FIX: Search across ALL documents
        docs = store.similarity_search(request.question, k=5)
        
        if not docs:
            return {
                "answer": "I couldn't find relevant information in your documents.",
                "sources": [],
                "session_id": session_id
            }
        
        context = "\n\n".join([doc.page_content for doc in docs])
        sources = list(set([doc.metadata.get('source', 'Unknown') for doc in docs]))
        
        history = ""
        current_session = user_sessions[user_id][session_id]
        if "messages" in current_session:
            for msg in current_session["messages"][-4:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                history += f"{role}: {msg['content']}\n"
        
        prompt = f"""You are a helpful AI assistant analyzing documents.

Context from documents ({len(sources)} sources):
{context}

Conversation history:
{history}

Question: {request.question}

Answer the question based on the context. Be conversational and helpful.

Answer:"""
        
        response = llm.invoke(prompt)
        answer = response.content
        
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
        raise HTTPException(500, str(e))

@app.get("/sessions")
def get_sessions(user_id: Optional[str] = Header(None, alias="user-id")):
    if not user_id or user_id not in user_sessions:
        return {"sessions": [], "total": 0}
    
    sessions = list(user_sessions[user_id].values())
    sessions.sort(key=lambda x: x.get('created', ''), reverse=True)
    return {"sessions": sessions, "total": len(sessions)}

@app.get("/sessions/{session_id}")
def get_session(session_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    if not user_id or user_id not in user_sessions or session_id not in user_sessions[user_id]:
        raise HTTPException(404, "Not found")
    return user_sessions[user_id][session_id]

@app.post("/sessions/new")
def create_new_session(request: QuestionRequest):
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
    return {"session_id": session_id}

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    if user_id in user_sessions and session_id in user_sessions[user_id]:
        del user_sessions[user_id][session_id]
        try:
            os.remove(f"{HISTORY_DIR}/{session_id}.json")
        except:
            pass
    return {"ok": True}

@app.delete("/clear")
def clear_all_files(user_id: Optional[str] = Header(None, alias="user-id")):
    if not user_id:
        return {"ok": False}
    
    if user_id in user_vector_stores:
        del user_vector_stores[user_id]
    if user_id in user_files:
        del user_files[user_id]
    
    try:
        import shutil
        user_dir = f"{UPLOAD_DIR}/{user_id}"
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
    except:
        pass
    
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)