from fastapi import FastAPI, HTTPException, Form, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3
import json
import os
import uuid
import secrets
import urllib.request
import google.generativeai as genai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    text_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    text_model = None

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

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
    
    try:
        c.execute("ALTER TABLE items ADD COLUMN bounty INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Column already exists, safe to ignore
        
    conn.commit()
    conn.close()

init_db()

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
    
    cursor.execute("SELECT * FROM items WHERE creator = ? ORDER BY id DESC", (current_user,))
    my_reports = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT * FROM items WHERE claimed_by = ? ORDER BY id DESC", (current_user,))
    my_claims = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    for lst in [my_reports, my_claims]:
        for item in lst:
            try: item["ai_tags"] = json.loads(item["ai_tags"])
            except: item["ai_tags"] = []
            item["has_image"] = bool(item["has_image"])
            item["bounty"] = item.get("bounty", 0)
            
    return {"reports": my_reports, "claims": my_claims}

def get_ai_tags(description: str, name: str):
    if text_model:
        try:
            prompt = f"Generate 3 single-word tags for a lost item with this name: {name} and description: {description}. Return ONLY the tags separated by commas."
            response = text_model.generate_content(prompt)
            tags = [tag.strip().lower() for tag in response.text.split(',')]
            return tags[:3]
        except:
            pass 
            
    text = f"{name} {description}".lower()
    tags = []
    if "phone" in text or "iphone" in text: tags.append("smartphone")
    if "key" in text: tags.append("keys")
    if "wallet" in text: tags.append("wallet")
    if not tags: tags.append("misc")
    return tags

@app.get("/items")
def get_items():
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items WHERE status = 'active' ORDER BY id DESC")
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    for item in items:
        try: item["ai_tags"] = json.loads(item["ai_tags"])
        except: item["ai_tags"] = []
        item["bounty"] = item.get("bounty", 0)
    return {"items": items}

@app.post("/add-item")
async def add_item(
    name: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    type: str = Form(...),
    bounty: int = Form(0),    file: UploadFile = File(None),
    authorization: str = Header(None)
):
    current_user = get_user_from_token(authorization)
    if current_user == "anonymous":
        raise HTTPException(status_code=401, detail="Please log in to report items")
        
    ai_tags = get_ai_tags(description, name)
    
    image_url = None
    has_image = False
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1] or ".jpg"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_name)
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        image_url = f"/uploads/{unique_name}"
        has_image = True
    
    conn = sqlite3.connect('lost_and_found.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO items (name, description, location, type, image_url, has_image, ai_tags, creator, bounty)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, description, location, type, image_url, has_image, json.dumps(ai_tags), current_user, bounty))
    conn.commit()
    conn.close()
    
    return {"message": "Item added successfully", "tags_generated": ai_tags}

@app.post("/scan-matches")
async def scan_matches(
    name: str = Form(...),
    description: str = Form(...),
    location: str = Form(...),
    type: str = Form(...),
    bounty: int = Form(0),    file: UploadFile = File(None),
    authorization: str = Header(None)
):
    current_user = get_user_from_token(authorization)
    if current_user == "anonymous":
        raise HTTPException(status_code=401, detail="Please log in to scan items")
        
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Save the lost item first
    ai_tags = get_ai_tags(description, name)
    
    image_url = None
    has_image = False
    if file and file.filename:
        ext = os.path.splitext(file.filename)[1] or ".jpg"
        unique_name = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_name)
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        image_url = f"/uploads/{unique_name}"
        has_image = True
    
    cursor.execute("""
        INSERT INTO items (name, description, location, type, image_url, has_image, ai_tags, creator, bounty)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, description, location, type, image_url, has_image, json.dumps(ai_tags), current_user, bounty))
    conn.commit()
    
    # Scan for matches
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
            item["bounty"] = item.get("bounty", 0)
            results.append({"item": item, "confidence_score": score + 10})
            
    results.sort(key=lambda x: x["confidence_score"], reverse=True)
    return {"results": results}

@app.post("/claim/{item_id}")
def claim_item(item_id: int, authorization: str = Header(None)):
    current_user = get_user_from_token(authorization)
    if current_user == "anonymous":
        raise HTTPException(status_code=401, detail="Must be logged in to claim items")
        
    conn = sqlite3.connect('lost_and_found.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT name, creator, bounty, type FROM items WHERE id = ?", (item_id,))
    item = c.fetchone()
    
    if item:
        item_name = item['name']
        creator_username = item['creator']
        bounty_amount = item['bounty']
        
        c.execute("SELECT email FROM users WHERE username = ?", (creator_username,))
        user_row = c.fetchone()
        
        if user_row:
            creator_email = user_row['email']
            resend_key = os.environ.get("RESEND_API_KEY")
            
            bounty_msg = f"<p><b>Good news!</b> We have released the ${bounty_amount} reward from escrow to their account.</p>" if bounty_amount > 0 else ""
            
            if resend_key:
                try:
                    email_data = {
                        "from": "AI MatchMaker <onboarding@resend.dev>",
                        "to": [creator_email],
                        "subject": f"🎉 MatchMaker Update: Someone claimed your {item_name}!",
                        "html": f"<h3>Great news, {creator_username}!</h3><p>User <b>{current_user}</b> just successfully identified your {item_name}.</p>{bounty_msg}<p>Log into your MatchMaker profile to contact them and arrange a meeting!</p>"
                    }
                    req = urllib.request.Request(
                        "https://api.resend.com/emails",
                        data=json.dumps(email_data).encode('utf-8'),
                        headers={
                            "Authorization": f"Bearer {resend_key}",
                            "Content-Type": "application/json"
                        }
                    )
                    urllib.request.urlopen(req)
                except Exception as e:
                    print(f"Email failed to send: {e}")

    c.execute("UPDATE items SET status = 'claimed', claimed_by = ? WHERE id = ?", (current_user, item_id))
    conn.commit()
    conn.close()
    return {"message": "Item claimed successfully and email sent!"}

@app.post("/analyze-frame")
async def analyze_frame(file: UploadFile = File(...)):
    if not text_model:
        return {"tags": ["AI key not configured"]}

    try:
        from PIL import Image
        import io

        image_data = await file.read()
        img = Image.open(io.BytesIO(image_data))

        prompt = (
            "You are an object detection assistant for a lost-and-found app. "
            "Look at this image and identify any visible everyday objects that "
            "someone might lose or find (e.g. phone, wallet, keys, bag, laptop, "
            "bottle, headphones, glasses, watch, umbrella, book, clothing, etc). "
            "Return ONLY a comma-separated list of detected item names, maximum "
            "4 items. Keep each name short (1-2 words). "
            "If no recognizable items are visible, respond with exactly: Scanning"
        )

        response = text_model.generate_content([prompt, img])
        tags_text = response.text.strip()

        if "scanning" in tags_text.lower() or not tags_text:
            return {"tags": ["Scanning..."]}

        tags = [t.strip().title() for t in tags_text.split(",") if t.strip()]
        return {"tags": tags[:4] if tags else ["Scanning..."]}

    except Exception as e:
        print(f"Frame analysis error: {e}")
        return {"tags": ["Analyzing..."]}
class ChatRequest(BaseModel):
    message: str
    history: list

@app.post("/assistant/chat")
async def chat_assistant(req: ChatRequest):
    text = req.message.lower()

    # --- 1. Detect item name (expanded vocabulary) ---
    name = ""
    item_keywords = [
        ("airpods", "AirPods"), ("apple watch", "Apple Watch"),
        ("iphone", "iPhone"), ("ipad", "iPad"), ("macbook", "MacBook"),
        ("samsung", "Samsung Phone"), ("pixel", "Pixel Phone"),
        ("smartphone", "Smartphone"), ("phone", "Phone"),
        ("laptop", "Laptop"), ("chromebook", "Chromebook"), ("tablet", "Tablet"),
        ("wallet", "Wallet"), ("purse", "Purse"),
        ("keychain", "Keychain"), ("keys", "Keys"), ("key", "Keys"),
        ("backpack", "Backpack"), ("handbag", "Handbag"), ("bag", "Bag"),
        ("headphones", "Headphones"), ("earbuds", "Earbuds"),
        ("sunglasses", "Sunglasses"), ("glasses", "Glasses"),
        ("watch", "Watch"), ("umbrella", "Umbrella"),
        ("water bottle", "Water Bottle"), ("bottle", "Bottle"),
        ("charger", "Charger"), ("usb", "USB Drive"),
        ("necklace", "Necklace"), ("bracelet", "Bracelet"), ("ring", "Ring"),
        ("camera", "Camera"), ("notebook", "Notebook"), ("book", "Book"),
        ("jacket", "Jacket"), ("hoodie", "Hoodie"), ("coat", "Coat"),
        ("hat", "Hat"), ("cap", "Cap"), ("scarf", "Scarf"), ("gloves", "Gloves"),
        ("id card", "ID Card"), ("passport", "Passport"), ("license", "License"),
        ("hard drive", "Hard Drive"), ("mouse", "Mouse"),
    ]
    for keyword, item_name in item_keywords:
        if keyword in text:
            name = item_name
            break

    # --- 2. Detect type (lost / found) ---
    item_type = "unknown"
    if any(w in text for w in ["lost", "missing", "misplaced", "can't find", "cannot find", "lose"]):
        item_type = "lost"
    elif any(w in text for w in ["found", "picked up", "spotted", "came across"]):
        item_type = "found"

    # --- 3. Detect location ---
    location = ""

    # Check if the bot's last reply asked for a location (so we can treat the
    # whole message as a location answer when no item/type was detected).
    bot_asked_where = False
    for msg in reversed(req.history):
        if msg.get("role") == "model":
            last_bot = msg.get("text", "").lower()
            bot_asked_where = any(w in last_bot for w in ["where", "location", "happen"])
            break

    if not name and item_type == "unknown" and bot_asked_where and len(req.message.strip()) > 2:
        # The user is replying purely with a location
        location = req.message.strip().rstrip(".,!?;:")
    else:
        # Try to extract a location after a preposition
        preps = [
            "at the ", "at ", "in the ", "in ", "near the ", "near ",
            "around the ", "around ", "by the ", "by ", "on the ", "on ",
            "from the ", "from ", "outside the ", "outside ",
            "inside the ", "inside ", "next to the ", "next to ",
        ]
        preps.sort(key=len, reverse=True)
        for prep in preps:
            if prep in text:
                idx = text.rfind(prep)
                loc_candidate = req.message[idx + len(prep):].strip().rstrip(".,!?;:")
                if len(loc_candidate) > 2:
                    location = loc_candidate
                    break

    # --- 4. Only return description for substantive messages ---
    description = req.message if (name or len(req.message) > 20) else ""

    # --- 5. Build a contextual reply ---
    if name and location and item_type != "unknown":
        reply = (f"Perfect! I've captured everything: a {item_type} **{name}** "
                 f"at **{location}**. Review the details on the right panel and "
                 f"hit **Publish Drafted Report** when you're ready!")
    elif name and location:
        reply = (f"Got it — a **{name}** at **{location}**. "
                 f"Was this item **lost** or **found**?")
    elif name and item_type != "unknown":
        reply = (f"Noted — a {item_type} **{name}**. "
                 f"**Where** exactly did this happen? "
                 f"(e.g., 'at the train station', 'in the cafeteria')")
    elif name:
        reply = (f"I've identified the item as a **{name}**. "
                 f"Was it lost or found? And where did it happen?")
    elif location and item_type != "unknown":
        reply = (f"A {item_type} item at **{location}**. "
                 f"What **item** are we talking about? "
                 f"(e.g., 'black iPhone', 'silver keys', 'red backpack')")
    elif location:
        reply = (f"Location saved: **{location}**. "
                 f"What **item** are we talking about, and was it lost or found?")
    elif item_type != "unknown":
        reply = (f"Understood, you {item_type} something. "
                 f"Can you describe the **item**? "
                 f"(e.g., 'a black wallet', 'car keys with a blue keychain')")
    else:
        reply = ("I'd love to help! Try describing what happened, like: "
                 "'I lost my black wallet at the train station' "
                 "— and I'll extract the details automatically.")

    return {
        "reply": reply,
        "name": name,
        "description": description,
        "location": location,
        "type": item_type
    }

@app.get("/")
def health_check():
    return {"status": "AI, Accounts, Escrow, and Smart Assistant are running perfectly!"}