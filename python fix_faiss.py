# fix_faiss.py
print("🔧 Fixing faiss-cpu version for Render...")

# New requirements content
new_content = """fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
python-dotenv==1.0.0
pypdf==3.17.4
python-docx==0.8.11
langchain==0.0.353
langchain-community==0.0.10
langchain-groq==0.0.1
faiss-cpu>=1.7.2
sentence-transformers==2.2.2
numpy==1.24.3"""

# Update root file
with open('requirements.txt', 'w') as f:
    f.write(new_content)
print("✅ Updated root/requirements.txt")

# Update backend file
with open('backend/requirements.txt', 'w') as f:
    f.write(new_content)
print("✅ Updated backend/requirements.txt")

print("\n📤 Now run these commands:")
print("git add .")
print('git commit -m "FIX: faiss-cpu version for Render"')
print("git push origin main")