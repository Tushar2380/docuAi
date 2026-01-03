
📄 DocuAI – AI-Powered Document Question Answering System

DocuAI is an AI-based web application that allows users to upload documents (PDF/DOCX) and ask questions about their content using natural language.
The system processes documents, stores semantic embeddings in a vector database, and uses a Large Language Model (LLM) to generate accurate, context-aware answers.


🚀 Features

📂 Upload PDF and DOCX documents
🔍 Automatic text extraction from documents
✂️ Text chunking for better context understanding
🧠 Semantic search using vector embeddings
🤖 AI-powered question answering
💬 Session-based chat history
🌐 Deployed backend and frontend
🧩 Simple and user-friendly interface

🛠️ Tech Stack

Backend
Python
FastAPI
LangChain
FAISS (Vector Database)
HuggingFace Embeddings
Groq / OpenAI-compatible LLM

Frontend
HTML
JavaScript

Deployment
Backend: Render
Frontend: Vercel


⚙️ System Architecture (Workflow)

User uploads a document                          
Text is extracted from the document
Text is split into smaller chunks
Embeddings are generated for each chunk
Embeddings are stored in FAISS vector database
User asks a question
Relevant chunks are retrieved using similarity search
LLM generates an answer using retrieved context


Project Structure:

docuAi/
│
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── uploads/
│   └── history/
│
├── frontend/
│   └── index.html
│
└── README.md

📌 Future Enhancements
Support for multiple documents simultaneously
User authentication
Improved UI/UX
Multi-language document support
Advanced chat memory optimization

👤 Author
Tushar Wangari
Second-Year IT Engineering Student

🔗 GitHub: https://github.com/Tushar2380
🔗 LinkedIn: https://www.linkedin.com/in/tushar-wangari-a940b232a

⭐ Acknowledgements
LangChain
HuggingFace
FAISS
FastAPI
Groq API
