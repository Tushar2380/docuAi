import os
import time
import json
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pypdf import PdfReader
from dotenv import load_dotenv
import docx

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
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

vector_store = None
uploaded_files = {}
chat_sessions = {}
current_session_id = None

llm = ChatGroq(
    model="llama-3.1-8b-instant",
    api_key=GROQ_API_KEY,
    temperature=0.7,
) if GROQ_API_KEY else None

print("Loading embeddings...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
)
print("Ready!")

class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

def extract_pdf(path):
    try:
        reader = PdfReader(path)
        return "\n".join([p.extract_text() or "" for p in reader.pages])
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return ""

def extract_docx(path):
    try:
        doc = docx.Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        print(f"Error extracting DOCX: {e}")
        return ""

def save_session(sid):
    if sid in chat_sessions:
        try:
            with open(f"{HISTORY_DIR}/{sid}.json", 'w') as f:
                json.dump(chat_sessions[sid], f)
        except Exception as e:
            print(f"Error saving session {sid}: {e}")

def load_sessions():
    global chat_sessions
    for f in os.listdir(HISTORY_DIR):
        if f.endswith('.json'):
            try:
                with open(f"{HISTORY_DIR}/{f}") as file:
                    data = json.load(file)
                    chat_sessions[data['id']] = data
            except Exception as e:
                print(f"Error loading session {f}: {e}")

load_sessions()

@app.get("/")
def root():
    return {"status": "online", "files": len(uploaded_files)}

@app.get("/current-session")
def get_current_session():
    """Get the current active session ID"""
    return {
        "session_id": current_session_id,
        "has_session": current_session_id is not None,
        "session_exists": current_session_id in chat_sessions if current_session_id else False,
        "total_sessions": len(chat_sessions)
    }

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global vector_store, uploaded_files
    
    if not file.filename.lower().endswith(('.pdf', '.docx', '.doc')):
        raise HTTPException(400, "PDF/DOCX only")
    
    fid = f"{int(time.time()*1000)}_{file.filename}"
    fpath = f"{UPLOAD_DIR}/{fid}"
    
    try:
        content = await file.read()
        with open(fpath, "wb") as f:
            f.write(content)
        
        text = extract_pdf(fpath) if fpath.endswith('.pdf') else extract_docx(fpath)
        
        if len(text.strip()) < 10:
            os.remove(fpath)
            raise HTTPException(400, "Empty file")
        
        splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=150)
        chunks = splitter.split_text(text)
        metas = [{"source": file.filename, "fid": fid} for _ in chunks]
        
        if not vector_store:
            vector_store = FAISS.from_texts(chunks, embeddings, metadatas=metas)
        else:
            new = FAISS.from_texts(chunks, embeddings, metadatas=metas)
            vector_store.merge_from(new)
        
        uploaded_files[fid] = {
            "filename": file.filename,
            "fid": fid,
            "chunks": len(chunks),
            "size": len(content)
        }
        
        return {
            "message": "OK", 
            "filename": file.filename,
            # IMPORTANT: Return current session so frontend knows it's unchanged
            "current_session_id": current_session_id
        }
    except Exception as e:
        if os.path.exists(fpath):
            os.remove(fpath)
        raise HTTPException(500, str(e))

@app.get("/files")
def list_files():
    return {"files": list(uploaded_files.values())}

@app.delete("/files/{fid}")
def delete_file(fid: str):
    if fid in uploaded_files:
        del uploaded_files[fid]
        try:
            os.remove(f"{UPLOAD_DIR}/{fid}")
        except:
            pass
    return {"ok": True}

@app.post("/ask")
async def ask(req: QuestionRequest):
    global current_session_id
    
    if not vector_store:
        raise HTTPException(400, "Upload docs first")
    
    if not llm:
        raise HTTPException(500, "API key missing")
    
    # If session_id provided, use it
    if req.session_id:
        sid = req.session_id
        if sid not in chat_sessions:
            # Create new session if provided ID doesn't exist
            sid = f"s{int(time.time()*1000)}"
            chat_sessions[sid] = {
                "id": sid,
                "messages": [],
                "title": "New Chat",
                "created": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
    else:
        # If no session_id, check if we have a current session
        if current_session_id and current_session_id in chat_sessions:
            sid = current_session_id
        else:
            # Create new session
            sid = f"s{int(time.time()*1000)}"
            chat_sessions[sid] = {
                "id": sid,
                "messages": [],
                "title": "New Chat",
                "created": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
    
    # Set as current session
    current_session_id = sid
    
    try:
        docs = vector_store.similarity_search(req.question, k=4)
        context = "\n\n".join([d.page_content for d in docs])
        sources = list(set([d.metadata.get('source', 'Unknown') for d in docs]))
        
        history = ""
        if "messages" in chat_sessions[sid]:
            for m in chat_sessions[sid]["messages"][-4:]:
                history += f"{'User' if m['role']=='user' else 'AI'}: {m['content']}\n"
        
        prompt = f"""Answer based on context. Use history for references.

Context:
{context}

History:
{history}

Question: {req.question}

Answer clearly with source at end like "Source: filename.pdf":"""
        
        resp = llm.invoke(prompt)
        answer = resp.content
        
        # Initialize messages array if needed
        if "messages" not in chat_sessions[sid]:
            chat_sessions[sid]["messages"] = []
        
        chat_sessions[sid]["messages"].append({
            "role": "user",
            "content": req.question,
            "time": datetime.now().strftime("%H:%M")
        })
        
        chat_sessions[sid]["messages"].append({
            "role": "assistant",
            "content": answer,
            "sources": sources,
            "time": datetime.now().strftime("%H:%M")
        })
        
        if len(chat_sessions[sid]["messages"]) == 2:
            chat_sessions[sid]["title"] = req.question[:40] + "..."
        
        save_session(sid)
        
        return {
            "answer": answer,
            "sources": sources,
            "session_id": sid
        }
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/sessions")
def get_sessions():
    sessions = list(chat_sessions.values())
    sessions.sort(key=lambda x: x.get('created', ''), reverse=True)
    return {"sessions": sessions}

@app.get("/sessions/{sid}")
def get_session(sid: str):
    if sid not in chat_sessions:
        raise HTTPException(404, "Not found")
    return chat_sessions[sid]

@app.post("/sessions/new")
def new_session():
    global current_session_id
    sid = f"s{int(time.time()*1000)}"
    chat_sessions[sid] = {
        "id": sid,
        "messages": [],
        "title": "New Chat",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    current_session_id = sid
    save_session(sid)
    return {"session_id": sid}

@app.delete("/sessions/{sid}")
def delete_session(sid: str):
    global current_session_id
    if sid in chat_sessions:
        del chat_sessions[sid]
        try:
            os.remove(f"{HISTORY_DIR}/{sid}.json")
        except:
            pass
    if current_session_id == sid:
        current_session_id = None
    return {"ok": True}

@app.delete("/clear")
def clear_all():
    global vector_store, uploaded_files
    vector_store = None
    uploaded_files = {}
    for f in os.listdir(UPLOAD_DIR):
        try:
            os.remove(f"{UPLOAD_DIR}/{f}")
        except:
            pass
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)