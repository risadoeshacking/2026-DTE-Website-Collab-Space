import sqlite3
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "collab_space_nz_2026_secure_key"

DB = Path("collab_space.db")

def get_db():

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("home_feed"))
    return redirect(url_for("login_page"))

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email=?",
                          (email,)).fetchone()
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("home_feed"))

        flash("Invalid email or password", "error")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register_page():
    if request.method == "POST":
        fullname = request.form.get("fullname")
        email = request.form.get("email")
        password = request.form.get("password")

        hashed_pw = generate_password_hash(password)

        db = get_db()
        try:
            db.execute("INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                       (fullname, email, hashed_pw))
            db.commit()
            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login_page"))
        except sqlite3.IntegrityError:
            flash("Email already exists.", "error")
        finally:
            db.close()
    return render_template("register.html")

@app.route("/home")
def home_feed():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    db = get_db()
    uid = session["user_id"]

    query =
    posts = db.execute(query, (uid, uid)).fetchall()
    db.close()

    return render_template("home.html", posts=posts)

@app.route("/posts/<int:post_id>/comments")
def get_comments(post_id):
    db = get_db()
    comments = db.execute(, (post_id,)).fetchall()
    db.close()
    return jsonify({"comments": [dict(c) for c in comments]})

@app.route("/posts/<int:post_id>/like", methods=["POST"])
def toggle_like(post_id):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Auth required"}), 401

    db = get_db()
    existing = db.execute(
        "SELECT 1 FROM likes WHERE post_id=? AND user_id=?", (post_id, uid)).fetchone()
    if existing:
        db.execute(
            "DELETE FROM likes WHERE post_id=? AND user_id=?", (post_id, uid))
    else:
        db.execute(
            "INSERT INTO likes (post_id, user_id) VALUES (?, ?)", (post_id, uid))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

if __name__ == "__main__":
    app.run(debug=True)