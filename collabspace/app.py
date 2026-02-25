import sqlite3
from pathlib import Path
from flask import Flask, request, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "change-this-later"

DB = Path("collab_space.db")
SCHEMA = Path("schema.sql")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    if DB.exists():
        return
    conn = db()
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    conn.close()

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    return user

@app.route("/")
def home():
    init_db()
    user = current_user()
    if not user:
        return redirect("/login")
    return f"yo {user['full_name']} ✅ you logged in. (next: feed page)"

@app.route("/register", methods=["GET", "POST"])
def register():
    init_db()

    if request.method == "GET":
        return

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not full_name or not email or not password:
        return "fill all fields bro", 400

    pw_hash = generate_password_hash(password)

    conn = db()
    try:
        conn.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (?,?,?)",
            (full_name, email, pw_hash),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return "email already used", 400

    user = conn.execute(
        "SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    session["user_id"] = user["id"]
    return redirect("/")

@app.route("/login", methods=["GET", "POST"])
def login():
    init_db()

    if request.method == "GET":
        return

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    conn = db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return "wrong email or password", 401

    session["user_id"] = user["id"]
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

if __name__ == "__main__":
    app.run(debug=True)