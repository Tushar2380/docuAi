import os
import time
import json
import shutil
import base64
from datetime import datetime
from typing import Optional, Dict, List
from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader
from dotenv import load_dotenv
import docx
import requests

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_groq import ChatGroq

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OCR_API_KEY = os.getenv("OCR_API_KEY", "K87899142388957")

if not GROQ_API_KEY:
    print("WARNING: GROQ_API_KEY not set")

app = FastAPI(title="DocuChat AI - Enhanced Vision + OCR")

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

user_vector_stores: Dict[str, FAISS] = {}
user_files: Dict[str, Dict] = {}
user_sessions: Dict[str, Dict] = {}

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

print("📄 Loading embeddings model...")
try:
    embeddings = FastEmbedEmbeddings()
    print("✅ Embeddings loaded successfully!")
except Exception as e:
    print(f"❌ Error loading embeddings: {e}")
    embeddings = None

class QuestionRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
    user_id: str

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

def analyze_image_with_vision_ai(file_content: bytes, filename: str) -> str:
    """Analyze image using Groq Vision API (llama-3.2-90b-vision-preview)"""
    try:
        if not GROQ_API_KEY:
            print("GROQ_API_KEY not available for vision analysis")
            return ""
        
        # Convert to base64
        base64_image = base64.b64encode(file_content).decode('utf-8')
        
        # Determine image format
        ext = filename.lower().split('.')[-1]
        mime_type = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }.get(ext, 'image/jpeg')
        
        # Use Groq Vision API
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.2-90b-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Analyze this image comprehensively and provide:

1. **Main Subject**: What is the primary focus of the image?
2. **Detailed Description**: Describe all visible elements, objects, people, scenery, colors, and composition.
3. **Text Content**: If there is any text visible in the image (signs, labels, captions, documents), transcribe it exactly.
4. **Context & Purpose**: What appears to be the purpose or context of this image?
5. **Notable Details**: Any important details, symbols, patterns, or features worth mentioning.

Provide a thorough analysis that would allow someone to understand the image without seeing it."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            description = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            
            if description and len(description) > 50:
                print(f"✅ Vision AI analyzed {filename}: {len(description)} chars")
                return f"[IMAGE ANALYSIS]\n{description}"
            else:
                print(f"⚠️ Vision AI returned insufficient content for {filename}")
                return ""
        else:
            print(f"❌ Vision API error {response.status_code}: {response.text}")
            return ""
            
    except requests.Timeout:
        print(f"⏱️ Vision API timeout for {filename}")
        return ""
    except Exception as e:
        print(f"❌ Vision analysis error for {filename}: {e}")
        return ""

def extract_image_ocr_cloud(file_content: bytes, filename: str) -> str:
    """Extract text from image using OCR.space API"""
    try:
        base64_image = base64.b64encode(file_content).decode('utf-8')
        
        url = "https://api.ocr.space/parse/image"
        
        payload = {
            'base64Image': f'data:image/png;base64,{base64_image}',
            'apikey': OCR_API_KEY,
            'language': 'eng',
            'isOverlayRequired': False,
            'detectOrientation': True,
            'scale': True,
            'OCREngine': 2
        }
        
        response = requests.post(url, data=payload, timeout=30)
        result = response.json()
        
        if result.get('IsErroredOnProcessing'):
            error_msg = result.get('ErrorMessage', ['Unknown error'])[0]
            print(f"OCR API error for {filename}: {error_msg}")
            return ""
        
        parsed_results = result.get('ParsedResults', [])
        if not parsed_results:
            return ""
        
        text = parsed_results[0].get('ParsedText', '').strip()
        
        if text and len(text) >= 10:
            print(f"✅ OCR extracted {len(text)} chars from {filename}")
            return f"[OCR TEXT]\n{text}"
        
        return ""
        
    except requests.Timeout:
        print(f"⏱️ OCR timeout for {filename}")
        return ""
    except Exception as e:
        print(f"❌ OCR extraction error for {filename}: {e}")
        return ""

def process_image_comprehensive(file_content: bytes, filename: str) -> str:
    """
    Process image with BOTH OCR and Vision AI for comprehensive understanding.
    Returns combined analysis.
    """
    print(f"🔍 Processing image: {filename}")
    
    # Try OCR first (for text extraction)
    ocr_text = extract_image_ocr_cloud(file_content, filename)
    
    # Try Vision AI (for image description and context)
    vision_text = analyze_image_with_vision_ai(file_content, filename)
    
    # Combine results
    combined_text = ""
    
    if vision_text:
        combined_text += vision_text + "\n\n"
    
    if ocr_text:
        combined_text += ocr_text + "\n\n"
    
    # If we got something, return it
    if combined_text.strip():
        final_text = f"=== IMAGE: {filename} ===\n\n{combined_text.strip()}"
        print(f"✅ Successfully processed {filename}: {len(final_text)} chars")
        return final_text
    
    print(f"❌ Failed to extract any information from {filename}")
    return ""

def is_image_file(filename: str) -> bool:
    """Check if file is an image"""
    return filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'))

def save_session(user_id: str, sid: str):
    """Save session to disk"""
    if user_id in user_sessions and sid in user_sessions[user_id]:
        try:
            data = user_sessions[user_id][sid]
            data['user_id'] = user_id 
            
            filepath = os.path.join(HISTORY_DIR, f"{sid}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving session {sid}: {e}")

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
                    owner = data.get('user_id', 'unknown_user')
                    
                    if owner not in user_sessions:
                        user_sessions[owner] = {}
                    
                    user_sessions[owner][sid] = data
            except Exception as e:
                print(f"Error loading session {filename}: {e}")

load_sessions()
print(f"📚 Loaded existing sessions into memory")

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "status": "online",
        "service": "DocuChat AI - Enhanced Vision + OCR",
        "active_users": len(user_sessions),
        "llm_ready": llm is not None,
        "embeddings_ready": embeddings is not None,
        "ocr_ready": True,
        "vision_ai_ready": GROQ_API_KEY is not None,
        "features": ["text_extraction", "ocr", "vision_ai", "image_analysis"]
    }

@app.get("/health")
def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "groq_configured": GROQ_API_KEY is not None,
        "llm_initialized": llm is not None,
        "embeddings_initialized": embeddings is not None,
        "ocr_available": True,
        "ocr_provider": "OCR.space",
        "vision_ai_available": GROQ_API_KEY is not None,
        "vision_model": "llama-3.2-90b-vision-preview"
    }

@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...), 
    user_id: Optional[str] = Header(None, alias="user-id")
):
    if not user_id:
        raise HTTPException(400, "User ID header missing")

    if not embeddings:
        raise HTTPException(500, "Embeddings not initialized")
    
    is_image = is_image_file(file.filename)
    is_document = file.filename.lower().endswith(('.pdf', '.docx', '.doc'))
    
    if not (is_image or is_document):
        raise HTTPException(400, "Only PDF, DOCX, and Image files (PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP) are supported")
    
    user_dir = os.path.join(UPLOAD_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)

    file_id = f"{int(time.time() * 1000)}_{file.filename}"
    file_path = os.path.join(user_dir, file_id)
    
    try:
        content = await file.read()
        
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(400, "File is too large (Max 10MB)")
            
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Extract text based on file type
        text = ""
        if is_image:
            # Use comprehensive image processing (OCR + Vision AI)
            text = process_image_comprehensive(content, file.filename)
            
            if not text or len(text.strip()) < 50:
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise HTTPException(400, "Could not analyze image. Image might be corrupted, too low quality, or processing failed.")
        
        elif file.filename.lower().endswith('.pdf'):
            text = extract_pdf(file_path)
        else:
            text = extract_docx(file_path)
        
        if not text or len(text.strip()) < 50:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(400, "Could not extract sufficient content. File might be empty, corrupted, or unreadable.")
        
        # Process embeddings
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len
        )
        chunks = text_splitter.split_text(text)
        
        if not chunks:
            raise HTTPException(400, "File contains no processable content.")

        metadatas = [{"source": file.filename, "file_id": file_id} for _ in chunks]
        
        if user_id not in user_vector_stores:
            user_vector_stores[user_id] = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
        else:
            new_store = FAISS.from_texts(chunks, embeddings, metadatas=metadatas)
            user_vector_stores[user_id].merge_from(new_store)
        
        if user_id not in user_files:
            user_files[user_id] = {}

        file_type = "image" if is_image else ("pdf" if file.filename.lower().endswith('.pdf') else "docx")
        
        user_files[user_id][file_id] = {
            "filename": file.filename,
            "file_id": file_id,
            "file_type": file_type,
            "chunks": len(chunks),
            "size": len(content),
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return {
            "message": f"{'Image' if is_image else 'File'} processed successfully",
            "filename": file.filename,
            "file_id": file_id,
            "file_type": file_type,
            "chunks": len(chunks),
            "processing": "vision_ai_ocr" if is_image else "text_extraction"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"Upload error: {e}")
        raise HTTPException(500, f"Error processing file: {str(e)}")

@app.get("/files")
def list_files(user_id: Optional[str] = Header(None, alias="user-id")):
    """Get list of all uploaded files for this user"""
    if not user_id or user_id not in user_files:
        return {"files": [], "total": 0}
        
    return {
        "files": list(user_files[user_id].values()),
        "total": len(user_files[user_id])
    }

@app.delete("/files/{file_id}")
def delete_file(file_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    """Delete a specific file"""
    if not user_id or user_id not in user_files:
        return {"message": "File not found"}

    if file_id in user_files[user_id]:
        del user_files[user_id][file_id]
        
        file_path = os.path.join(UPLOAD_DIR, user_id, file_id)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Error deleting file: {e}")
    
    return {"message": "File deleted", "ok": True}

@app.post("/ask")
async def ask_question(request: QuestionRequest):
    """Ask a question about uploaded documents"""
    user_id = request.user_id
    
    if user_id not in user_sessions:
        user_sessions[user_id] = {}
    
    store = user_vector_stores.get(user_id)
    if not store:
        return {
            "answer": "Please upload a document or image first.",
            "sources": [],
            "session_id": request.session_id
        }
    
    if not llm:
        raise HTTPException(500, "LLM not configured. Please set GROQ_API_KEY")
    
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
        docs = store.similarity_search(request.question, k=5)
        
        if not docs:
            return {
                "answer": "I couldn't find relevant information in the uploaded documents.",
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
        
        prompt = f"""You are an intelligent AI assistant with multimodal understanding capabilities.

Instructions:
1. For SUMMARIES: Identify main topics, concepts, and key information from the documents/images.
2. For SPECIFIC QUESTIONS: Answer strictly based on the provided context.
3. For IMAGE-related queries: Use the [IMAGE ANALYSIS] and [OCR TEXT] sections to provide comprehensive answers about what's shown in images, including visual elements, text content, and context.
4. If the answer is not in the context, clearly state "I cannot find that information in the provided documents/images."
5. Be thorough and specific when describing images or answering questions about visual content.

Context from documents and images:
{context}

Conversation history:
{history}

User question: {request.question}

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
        raise HTTPException(500, f"Error processing question: {str(e)}")

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

@app.post("/sessions/new")
def create_new_session(request: QuestionRequest):
    """Create a new chat session"""
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

@app.post("/sessions/{session_id}/clear")
def clear_session_messages(session_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    """Clear messages from a specific session but keep the session"""
    if user_id in user_sessions and session_id in user_sessions[user_id]:
        user_sessions[user_id][session_id]["messages"] = []
        save_session(user_id, session_id)
        return {"message": "Chat cleared", "ok": True}
    return {"message": "Session not found", "ok": False}

@app.delete("/sessions/{session_id}")
def delete_session(session_id: str, user_id: Optional[str] = Header(None, alias="user-id")):
    """Delete a chat session"""
    if user_id in user_sessions and session_id in user_sessions[user_id]:
        del user_sessions[user_id][session_id]
        
        filepath = os.path.join(HISTORY_DIR, f"{session_id}.json")
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            print(f"Error deleting session file: {e}")
    
    return {"message": "Session deleted", "ok": True}

@app.delete("/clear")
def clear_all_data(user_id: Optional[str] = Header(None, alias="user-id")):
    if not user_id:
        return {"ok": False}

    if user_id in user_vector_stores:
        del user_vector_stores[user_id]
    if user_id in user_files:
        del user_files[user_id]
    
    user_dir = os.path.join(UPLOAD_DIR, user_id)
    try:
        if os.path.exists(user_dir):
            shutil.rmtree(user_dir)
            os.makedirs(user_dir, exist_ok=True)
    except Exception as e:
        print(f"Error clearing user dir: {e}")

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)