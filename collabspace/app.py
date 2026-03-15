import sqlite3
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for

app = Flask(__name__)

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

@app.route("/")
def home():
    init_db()
    return redirect(url_for("login_page"))

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND password_hash=?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            return "Login successful"
        else:
            return "Wrong email or password"

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "POST":
        fullname = request.form["fullname"]
        email = request.form["email"]
        password = request.form["password"]

        conn = db()
        conn.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
            (fullname, email, password)
        )
        conn.commit()
        conn.close()

        return redirect(url_for("login_page"))

    return render_template("register.html")

if __name__ == "__main__":
    init_db()
    app.run(debug=True)