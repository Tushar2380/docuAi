import os
import time
import json
import shutil
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader
from dotenv import load_dotenv
import docx

# LangChain & Lightweight Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_groq import ChatGroq

load_dotenv()

# Verify API Key
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY not found.")

app = FastAPI(title="DocuChat AI")

# Enable connection from your Mobile/Netlify
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

# AI Setup
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    api_key=GROQ_API_KEY,
    temperature=0.7,
)

# LIGHTWEIGHT EMBEDDINGS (Crucial for Mobile/Render Free Tier)
print("Loading lightweight embedding model...")
embeddings = FastEmbedEmbeddings()
print("Model loaded!")

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
        print(f"PDF Error: {e}")
        return ""

def extract_text_from_docx(file_path: str) -> str:
    try:
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs])
        return text
    except Exception as e:
        print(f"DOCX Error: {e}")
        return ""

def save_session(session_id: str):
    if session_id in chat_sessions:
        path = os.path.join(HISTORY_DIR, f"{session_id}.json")
        with open(path, 'w') as f:
            json.dump(chat_sessions[session_id], f, indent=2)

def load_session_from_disk(session_id: str):
    global chat_sessions
    path = os.path.join(HISTORY_DIR, f"{session_id}.json")
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                chat_sessions[data['id']] = data
                return True
        except:
            pass
    return False

# --- Routes ---
@app.get("/")
async def root():
    return {"status": "healthy", "service": "DocuChat Mobile Ready"}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    global vector_store, uploaded_files

    file_id = f"{int(time.time() * 1000)}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if file.filename.lower().endswith('.pdf'):
            text = extract_text_from_pdf(file_path)
        elif file.filename.lower().endswith(('.docx', '.doc')):
            text = extract_text_from_docx(file_path)
        else:
            os.remove(file_path)
            raise HTTPException(400, "Unsupported file type")

        if not text or len(text.strip()) < 10:
            os.remove(file_path)
            raise HTTPException(400, "File is empty")

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_text(text)
        
        metadatas = [{"source": file.filename, "file_id": file_id} for _ in chunks]

        if vector_store is None:
            vector_store = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
        else:
            new_store = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
            vector_store.merge_from(new_store)

        uploaded_files[file_id] = {"filename": file.filename, "chunks": len(chunks)}
        os.remove(file_path)

        return {"message": "File processed", "file_id": file_id}

    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(500, f"Error: {str(e)}")

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    global current_session_id
    
    if not vector_store:
        raise HTTPException(400, "Please upload a document first.")

    session_id = request.session_id or current_session_id
    if not session_id or session_id not in chat_sessions:
        session_id = f"session_{int(time.time() * 1000)}"
        chat_sessions[session_id] = {"id": session_id, "messages": [], "title": "New Chat"}
        current_session_id = session_id

    docs = vector_store.similarity_search(request.question, k=4)
    context = "\n\n".join([doc.page_content for doc in docs])
    
    history_text = ""
    for msg in chat_sessions[session_id]["messages"][-4:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_text += f"{role}: {msg['content']}\n"

    prompt = f"""You are a helpful AI assistant. Answer based on context.
    Context: {context}
    History: {history_text}
    Question: {request.question}
    Answer:"""

    response = llm.invoke(prompt)
    answer = response.content

    chat_sessions[session_id]["messages"].append({"role": "user", "content": request.question})
    chat_sessions[session_id]["messages"].append({"role": "assistant", "content": answer})
    save_session(session_id)
    
    return {"answer": answer, "session_id": session_id}

@app.get("/sessions")
async def get_sessions():
    return {"sessions": list(chat_sessions.values())}

if __name__ == "__main__":
    import uvicorn
    # This reads the PORT from Render automatically
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)