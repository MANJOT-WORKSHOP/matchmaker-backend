from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3
import os
import shutil
import uuid

app = FastAPI()

# Allow the frontend to communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create the uploads folder automatically if it doesn't exist
os.makedirs("uploads", exist_ok=True)

# Tell FastAPI to serve the images to the internet
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Database Setup
def get_db():
    conn = sqlite3.connect("matchmaker.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Create Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
        )
    ''')
    
    # Create Items Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            title TEXT,
            description TEXT,
            image TEXT,
            bounty INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

class User(BaseModel):
    email: str
    password: str

@app.post("/register")
def register(user: User):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (email, password) VALUES (?, ?)", (user.email, user.password))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()
    return {"message": "User created successfully"}

@app.post("/login")
def login(user: User):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ? AND password = ?", (user.email, user.password))
    db_user = cursor.fetchone()
    conn.close()
    if not db_user:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    return {"message": "Login successful"}

@app.post("/add-item")
def add_item(
    type: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    bounty: int = Form(0),
    image: UploadFile = File(None)
):
    image_url = ""
    
    # Process the uploaded image
    if image:
        file_extension = image.filename.split(".")[-1]
        file_name = f"{uuid.uuid4()}.{file_extension}"
        file_path = f"uploads/{file_name}"
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
            
        image_url = f"/uploads/{file_name}"

    # Save to Database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO items (type, title, description, image, bounty, status) VALUES (?, ?, ?, ?, ?, ?)",
        (type, title, description, image_url, bounty, 'active')
    )
    conn.commit()
    conn.close()
    
    return {"message": "Item added successfully"}

@app.get("/items")
def get_items():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM items ORDER BY id DESC")
    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items