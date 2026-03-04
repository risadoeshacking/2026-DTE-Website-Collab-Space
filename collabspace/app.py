import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "collabspace_secret_key"

DB = Path("collab_space.db")
SCHEMA = Path("schema.sql")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = db()
    conn.executescript(SCHEMA.read_text())
    conn.commit()
    conn.close()

@app.route("/")
def feed():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = db()
    posts = conn.execute().fetchall()
    conn.close()

    return render_template("feed.html", posts=posts)

@app.route("/register", methods=["GET", "POST"])
def register():
    init_db()

    if request.method == "POST":
        full_name = request.form["fullname"]
        email = request.form["email"]
        password = request.form["password"]
        year_level = request.form.get("year_level")
        bio = request.form.get("bio")

        hashed_password = generate_password_hash(password)

        conn = db()

        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing:
            conn.close()
            return "Email already exists"

        conn.execute(, (full_name, email, hashed_password, year_level, bio))

        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    init_db()

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            return redirect(url_for("feed"))

        return "Invalid email or password"

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)