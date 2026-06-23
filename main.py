from fastapi import FastAPI, Form, UploadFile, File, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from thefuzz import fuzz
import uuid
import io
import os
import sqlite3
import json
import hashlib
import asyncio
import urllib.request
from fastapi.staticfiles import StaticFiles
from PIL import Image
from transformers import pipeline

# --- GEMINI API SETUP ---
# Empty string by default; execution environment provides the key or can fall back to environment variables
const_apiKey = ""
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", const_apiKey)

print("🧠 Loading Computer Vision Model... (This takes a few seconds)")
# This downloads a real pre-trained AI model to your computer!
vision_ai = pipeline("image-classification", model="google/vit-base-patch16-224")
print("✅ AI Model Loaded and Ready!")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create folders and serve static files
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# --- INITIALIZE SQLITE DATABASE & TABLES ---
def init_db():
    conn = sqlite3.connect('lost_and_found.db')
    cursor = conn.cursor()
    
    # 1. Items Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id TEXT PRIMARY KEY,
            name TEXT,
            description TEXT,
            location TEXT,
            type TEXT,
            ai_tags TEXT,
            has_image BOOLEAN,
            image_url TEXT,
            status TEXT DEFAULT 'active',
            creator TEXT DEFAULT 'anonymous',
            claimed_by TEXT
        )
    ''')
    
    # 2. Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT,
            salt TEXT,
            email TEXT
        )
    ''')
    
    # 3. Sessions Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Safely apply migrations if database already existed
    try:
        cursor.execute("ALTER TABLE items ADD COLUMN status TEXT DEFAULT 'active'")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE items ADD COLUMN creator TEXT DEFAULT 'anonymous'")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE items ADD COLUMN claimed_by TEXT")
    except:
        pass
        
    conn.commit()
    conn.close()

init_db()

# --- SECURITY & AUTHENTICATION HELPERS ---
def get_user_from_token(authorization: str):
    if not authorization or not authorization.startswith("Bearer "):
        return "anonymous"
    token = authorization.split(" ")[1]
    conn = sqlite3.connect('lost_and_found.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM sessions WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return "anonymous"

# --- PYDANTIC SCHEMAS ---
class RegisterModel(BaseModel):
    username: str
    password: str
    email: str

class LoginModel(BaseModel):
    username: str
    password: str

class AssistantChatRequest(BaseModel):
    message: str
    history: list # formatted history of conversations

# --- REAL GEMINI NLP CHAT CALL (Option 3) ---
def call_gemini_api(payload):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={GEMINI_API_KEY}"
    req = urllib.request.Request(url, method="POST")
    req.add_header("Content-Type", "application/json")
    data = json.dumps(payload).encode("utf-8")
    
    # Exponential backoff up to 5 times (1s, 2s, 4s, 8s)
    import time
    for delay in [1, 2, 4, 8]:
        try:
            with urllib.request.urlopen(req, data=data, timeout=15) as response:
                res_body = response.read().decode("utf-8")
                return json.loads(res_body)
        except Exception as e:
            print(f"Gemini API Error, retrying in {delay}s: {e}")
            time.sleep(delay)
    return None

async def call_gemini_async(payload):
    return await asyncio.to_thread(call_gemini_api, payload)

# --- COMPUTER VISION AGENT ---
def analyze_image_with_ai(image_bytes):
    try:
        image = Image.open(io.BytesIO(image_bytes))
        predictions = vision_ai(image)
        tags = []
        for guess in predictions[:3]:
            clean_tag = guess["label"].split(",")[0].lower()
            tags.append(clean_tag)
        print(f"🤖 AI saw: {tags}")
        return tags
    except Exception as e:
        print(f"AI Error: {e}")
        return []

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"message": "AI, Accounts, and Smart Assistant are running perfectly!"}

# --- AUTH SYSTEM (Option 2) ---
@app.post("/register")
def register_user(data: RegisterModel):
    conn = sqlite3.connect('lost_and_found.db')
    cursor = conn.cursor()
    
    # Check if username exists
    cursor.execute("SELECT username FROM users WHERE username = ?", (data.username,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
        
    salt = uuid.uuid4().hex
    password_hash = hashlib.sha256((data.password + salt).encode()).hexdigest()
    
    cursor.execute('''
        INSERT INTO users (username, password_hash, salt, email)
        VALUES (?, ?, ?, ?)
    ''', (data.username, password_hash, salt, data.email))
    conn.commit()
    conn.close()
    return {"message": "Registration successful!"}

@app.post("/login")
def login_user(data: LoginModel):
    conn = sqlite3.connect('lost_and_found.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT password_hash, salt FROM users WHERE username = ?", (data.username,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid username or password")
        
    stored_hash, salt = row
    test_hash = hashlib.sha256((data.password + salt).encode()).hexdigest()
    
    if test_hash != stored_hash:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid username or password")
        
    # Create secure token
    token = uuid.uuid4().hex
    cursor.execute("INSERT INTO sessions (token, username) VALUES (?, ?)", (token, data.username))
    conn.commit()
    conn.close()
    
    return {"token": token, "username": data.username}

@app.post("/logout")
def logout_user(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        conn = sqlite3.connect('lost_and_found.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        conn.close()
    return {"message": "Logged out successfully"}

@app.get("/me")
def get_me(authorization: str = Header(None)):
    username = get_user_from_token(authorization)
    if username == "anonymous":
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"username": username}

# --- AI CHAT ASSISTANT & COGNITIVE PARSER (Option 3) ---
@app.post("/assistant/chat")
async def assistant_chat(req: AssistantChatRequest):
    # Construct history payload for Gemini
    formatted_contents = []
    for turn in req.history:
        formatted_contents.append({
            "role": "user" if turn["role"] == "user" else "model",
            "parts": [{"text": turn["text"]}]
        })
        
    # Append current message
    formatted_contents.append({
        "role": "user",
        "parts": [{"text": req.message}]
    })
    
    # System Instructions to teach Gemini how to reply and extract structured data
    system_prompt = (
        "You are the friendly AI MatchMaker Assistant. Help users find their lost items or report items they found. "
        "Engage in conversational chat. At the same time, look at what the user says and extract these fields if mentioned: "
        "1. name (name of the item, e.g. 'iPhone 15', 'water bottle') "
        "2. description (color, brand, distinguishing marks) "
        "3. location (where it was lost/found) "
        "4. type ('lost', 'found', or 'unknown') "
        "If some fields are not mentioned, set them to empty strings. Provide a warm, conversational reply in the 'reply' field. "
        "Ask clarifying questions if key details are missing."
    )
    
    payload = {
        "contents": formatted_contents,
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Name of the item if mentioned, else empty string"},
                    "description": {"type": "STRING", "description": "Traits and features if mentioned, else empty string"},
                    "location": {"type": "STRING", "description": "Specific location if mentioned, else empty string"},
                    "type": {"type": "STRING", "enum": ["lost", "found", "unknown"]},
                    "reply": {"type": "STRING", "description": "Conversational reply directly addressing the user"}
                },
                "required": ["name", "description", "location", "type", "reply"]
            }
        }
    }
    
    response_data = await call_gemini_async(payload)
    if not response_data:
        return {
            "reply": "Sorry, I am having trouble connecting to my AI core right now.",
            "name": "", "description": "", "location": "", "type": "unknown"
        }
        
    try:
        # Extract the structured JSON from the first candidate
        raw_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
        parsed_result = json.loads(raw_text)
        return parsed_result
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        return {
            "reply": "I heard you, but my cognitive processor hit a small bump!",
            "name": "", "description": "", "location": "", "type": "unknown"
        }

# --- BROWSE LIVE FEED ---
@app.get("/items")
def get_all_items():
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items WHERE status = 'active' ORDER BY rowid DESC")
    rows = cursor.fetchall()
    conn.close()
    
    items = []
    for row in rows:
        item = dict(row)
        item["ai_tags"] = json.loads(item["ai_tags"])
        item["has_image"] = bool(item["has_image"])
        items.append(item)
    return {"items": items}

# --- CLAIM / DELETE AN ITEM ---
@app.post("/claim/{item_id}")
def claim_item(item_id: str, authorization: str = Header(None)):
    current_user = get_user_from_token(authorization)
    conn = sqlite3.connect('lost_and_found.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE items SET status = 'claimed', claimed_by = ? WHERE id = ?", (current_user, item_id))
    conn.commit()
    conn.close()
    return {"message": "Item successfully claimed!"}

# --- ADD REPORTED ITEM ---
@app.post("/add-item")
async def add_item(
    name: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    type: str = Form(...),
    file: UploadFile = File(None),
    authorization: str = Header(None)
):
    current_user = get_user_from_token(authorization)
    ai_tags = []
    image_url = None
    
    if file:
        image_bytes = await file.read()
        ai_tags = analyze_image_with_ai(image_bytes)
        
        file_extension = file.filename.split(".")[-1]
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        file_path = f"uploads/{unique_filename}"
        
        with open(file_path, "wb") as f:
            f.write(image_bytes)
            
        image_url = f"http://127.0.0.1:8000/uploads/{unique_filename}"
        
    item_id = str(uuid.uuid4())
    has_image = True if file else False
    
    conn = sqlite3.connect('lost_and_found.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO items (id, name, description, location, type, ai_tags, has_image, image_url, status, creator)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
    ''', (item_id, name, description, location, type, json.dumps(ai_tags), has_image, image_url, current_user))
    conn.commit()
    conn.close()
        
    new_item = {
        "id": item_id,
        "name": name,
        "description": description,
        "location": location,
        "type": type,
        "ai_tags": ai_tags, 
        "has_image": has_image,
        "image_url": image_url,
        "creator": current_user
    }
    return {"message": "Item saved successfully", "item": new_item}

# --- SCAN AI MATCHES ---
@app.post("/scan-matches")
async def scan_matches(
    name: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    type: str = Form(...),
    file: UploadFile = File(None)
):
    matches = []
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items WHERE type = 'found' AND status = 'active'")
    rows = cursor.fetchall()
    conn.close()
    
    for row in rows:
        stored_item = dict(row)
        stored_item["ai_tags"] = json.loads(stored_item["ai_tags"])
        stored_item["has_image"] = bool(stored_item["has_image"])

        text_score = fuzz.token_set_ratio(description, stored_item["description"])
        loc_score = 100 if location.lower() == stored_item["location"].lower() else 50
        
        visual_bonus = 0
        for tag in stored_item["ai_tags"]:
            if tag in description.lower() or tag in name.lower():
                visual_bonus += 20 

        final_score = int((text_score * 0.5) + (loc_score * 0.3) + visual_bonus)
        if final_score > 99: final_score = 99
        
        if final_score > 30:
            matches.append({
                "item": stored_item,
                "confidence_score": final_score
            })
                
    matches.sort(key=lambda x: x["confidence_score"], reverse=True)
    return {"results": matches}