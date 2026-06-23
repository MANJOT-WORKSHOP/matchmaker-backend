from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import json
import base64
import os
import secrets
from datetime import datetime

# Optional: If you want to use Gemini for the backend AI instead of heavy local models
import google.generativeai as genai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect('lost_and_found.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            location TEXT,
            type TEXT,
            image_url TEXT,
            has_image BOOLEAN,
            ai_tags TEXT,
            creator TEXT,
            status TEXT DEFAULT 'active',
            claimed_by TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Simple token dictionary for session management
active_tokens = {}

def create_token(username: str):
    token = secrets.token_hex(16)
    active_tokens[token] = username
    return token

def get_user_from_token(auth_header: str):
    if not auth_header or not auth_header.startswith("Bearer "):
        return "anonymous"
    token = auth_header.split(" ")[1]
    return active_tokens.get(token, "anonymous")

class UserCreate(BaseModel):
    username: str
    password: str
    email: str

class UserLogin(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(user: UserCreate):
    conn = sqlite3.connect('lost_and_found.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", 
                  (user.username, user.password, user.email))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    conn.close()
    return {"message": "User created successfully"}

@app.post("/login")
def login(user: UserLogin):
    conn = sqlite3.connect('lost_and_found.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (user.username, user.password))
    db_user = c.fetchone()
    conn.close()
    
    if db_user:
        token = create_token(user.username)
        return {"username": user.username, "token": token}
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/logout")
def logout(authorization: str = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        if token in active_tokens:
            del active_tokens[token]
    return {"message": "Logged out"}

@app.get("/profile")
def get_profile(authorization: str = Header(None)):
    current_user = get_user_from_token(authorization)
    if current_user == "anonymous":
        raise HTTPException(status_code=401, detail="Not logged in")
        
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get items I reported
    cursor.execute("SELECT * FROM items WHERE creator = ? ORDER BY id DESC", (current_user,))
    my_reports = [dict(row) for row in cursor.fetchall()]
    
    # Get items I claimed
    cursor.execute("SELECT * FROM items WHERE claimed_by = ? ORDER BY id DESC", (current_user,))
    my_claims = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # Parse tags
    for lst in [my_reports, my_claims]:
        for item in lst:
            try:
                item["ai_tags"] = json.loads(item["ai_tags"])
            except:
                item["ai_tags"] = []
            item["has_image"] = bool(item["has_image"])
            
    return {"reports": my_reports, "claims": my_claims}

def dummy_ai_analysis(description: str, name: str):
    """Fallback if no API key is present"""
    text = f"{name} {description}".lower()
    tags = []
    if "phone" in text or "iphone" in text: tags.append("smartphone")
    if "key" in text: tags.append("keys")
    if "wallet" in text: tags.append("wallet")
    if "bag" in text or "backpack" in text: tags.append("bag")
    if not tags: tags.append("misc")
    return tags

@app.get("/items")
def get_items():
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Only show active items on the public feed!
    cursor.execute("SELECT * FROM items WHERE status = 'active' ORDER BY id DESC")
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    for item in items:
        try:
            item["ai_tags"] = json.loads(item["ai_tags"])
        except:
            item["ai_tags"] = []
    return {"items": items}

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
    if current_user == "anonymous":
        raise HTTPException(status_code=401, detail="Please log in to report items")
        
    ai_tags = dummy_ai_analysis(description, name)
    image_url = None
    has_image = False
    
    # Optional: Save image logic here if needed
    
    conn = sqlite3.connect('lost_and_found.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO items (name, description, location, type, image_url, has_image, ai_tags, creator)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, description, location, type, image_url, has_image, json.dumps(ai_tags), current_user))
    conn.commit()
    conn.close()
    
    return {"message": "Item added successfully", "tags_generated": ai_tags}

@app.post("/scan-matches")
async def scan_matches(
    name: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    type: str = Form(...),
    file: UploadFile = File(None),
    authorization: str = Header(None)
):
    current_user = get_user_from_token(authorization)
    if current_user == "anonymous":
        raise HTTPException(status_code=401, detail="Please log in to scan items")
        
    # Basic keyword matching for demo purposes
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Look for the opposite type (if lost, look for found) that are active
    opposite_type = "found" if type == "lost" else "lost"
    cursor.execute("SELECT * FROM items WHERE type = ? AND status = 'active'", (opposite_type,))
    potential_matches = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    results = []
    search_terms = name.lower().split()
    for item in potential_matches:
        score = 0
        if any(term in item['name'].lower() for term in search_terms): score += 50
        if location.lower() in item['location'].lower() or item['location'].lower() in location.lower(): score += 30
        
        if score > 0:
            results.append({"item": item, "confidence_score": score + 10}) # base 10
            
    results.sort(key=lambda x: x["confidence_score"], reverse=True)
    return {"results": results}

@app.post("/claim/{item_id}")
def claim_item(item_id: int, authorization: str = Header(None)):
    current_user = get_user_from_token(authorization)
    if current_user == "anonymous":
        raise HTTPException(status_code=401, detail="Must be logged in to claim items")
        
    conn = sqlite3.connect('lost_and_found.db')
    c = conn.cursor()
    c.execute("UPDATE items SET status = 'claimed', claimed_by = ? WHERE id = ?", (current_user, item_id))
    conn.commit()
    conn.close()
    return {"message": "Item claimed successfully"}

@app.post("/analyze-frame")
async def analyze_frame(file: UploadFile = File(...)):
    # Mock tags for the camera scanner so it works instantly without crashing
    import random
    possible_tags = ["Smartphone", "Wallet", "Keys", "Water Bottle", "Backpack", "Headphones", "Laptop", "Glasses"]
    tags = random.sample(possible_tags, 2)
    return {"tags": tags}

class ChatRequest(BaseModel):
    message: str
    history: list

@app.post("/assistant/chat")
async def chat_assistant(req: ChatRequest):
    # Dummy NLP extraction for demo
    text = req.message.lower()
    name = ""
    if "iphone" in text: name = "iPhone"
    elif "wallet" in text: name = "Wallet"
    elif "keys" in text: name = "Keys"
    
    item_type = "unknown"
    if "lost" in text: item_type = "lost"
    elif "found" in text: item_type = "found"
    
    reply = "I understand you are talking about an item. Can you tell me exactly where it was?"
    if name:
        reply = f"I've noted that you are talking about a {name}. Where did this happen?"
        
    return {
        "reply": reply,
        "name": name,
        "description": req.message,
        "location": "Central Park" if "park" in text else "Unknown Location",
        "type": item_type
    }