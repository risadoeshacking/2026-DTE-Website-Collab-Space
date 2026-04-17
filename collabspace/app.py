import sqlite3
import time
from werkzeug.utils import secure_filename
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
import os

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

        flash("Wrong email or pw lol", "error")
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
            flash("Account made! Login now", "success")
            return redirect(url_for("login_page"))
        except:
            flash("Email used already", "error")
        finally:
            db.close()
    return render_template("register.html")

@app.route("/home")
def home_feed():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    db = get_db()
    posts = db.execute(
        "SELECT p.*, u.full_name FROM posts p JOIN users u ON p.user_id = u.id ORDER BY p.created_at DESC LIMIT 10"
    ).fetchall()
    db.close()
    return render_template("home.html", posts=posts)

@app.route("/new", methods=["GET", "POST"])
def new_post():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    if request.method == "POST":
        title = request.form["title"]
        desc = request.form.get("description", "")
        post_type = request.form.get("post_type", "need_help")
        uid = session["user_id"]
        image_path = None

        os.makedirs("static/posts", exist_ok=True)

        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename:
                filename = f"posts_{uid}_{int(time.time())}_{secure_filename(file.filename)}"
                filepath = f"static/posts/{filename}"
                file.save(filepath)
                image_path = f"posts/{filename}"

        db = get_db()
        db.execute("INSERT INTO posts (user_id, title, description, post_type, image_path, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                   (uid, title, desc, post_type, image_path))
        db.commit()
        db.close()
        flash("Post created!", "success")
        return redirect(url_for("home_feed"))

    return render_template("upload.html")

@app.route("/search")
def search():


    query = request.args.get('q', '').strip()
    type_filter = request.args.get('type_filter', 'all').strip()

    db = get_db()

    sql =
    params = []

    if query:
        sql += " AND (p.title LIKE ? OR p.description LIKE ?)"
        params.extend(['%' + query + '%', '%' + query + '%'])

    if type_filter != 'all':
        sql += " AND p.post_type = ?"
        params.append(type_filter)

    sql += " ORDER BY p.created_at DESC"

    posts = db.execute(sql, params).fetchall()
    db.close()

    return render_template('search.html', posts=posts, query=query, type_filter=type_filter)

@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return "<h1>no notifs</h1>"

@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return "<h1>my profile soon</h1>"

@app.route("/about")
def about():
    return "<h1>about collab space - i made it</h1>"

@app.route("/posts/<int:post_id>/comments")
def get_comments(post_id):
    db = get_db()
    comments = db.execute(
        "SELECT c.content, u.full_name FROM comments c JOIN users u ON c.user_id = u.id WHERE c.post_id = ? ORDER BY c.id ASC", (post_id,)).fetchall()
    db.close()
    return jsonify({"comments": [dict(c) for c in comments]})

@app.route("/posts/<int:post_id>/like", methods=["POST"])
def toggle_like(post_id):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "log in"}), 401

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
    return jsonify({"ok": True})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

if __name__ == "__main__":
    app.run(debug=True)