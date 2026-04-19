import sqlite3
import time
from pathlib import Path
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.secret_key = "collab_space_nz_2026_secure_key"

DB = Path("collab_space.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    try:
        db = get_db()
        with open('schema.sql', 'r') as f:
            db.executescript(f.read())
        db.commit()
        print(" * DB tables created/updated!")
    except Exception as e:
        print(" * DB already good or error:", e)
    finally:
        db.close()

init_db()

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
            session["username"] = user["username"] or ""
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
            flash("Account made! Login now :)", "success")
            return redirect(url_for("login_page"))
        except:
            flash("Email already used sorry", "error")
        db.close()
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out ok!", "success")
    return redirect(url_for("login_page"))

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
                filename = "posts_%s_%d_%s" % (
                    uid, int(time.time()), secure_filename(file.filename))
                filepath = "static/posts/" + filename
                file.save(filepath)
                image_path = "posts/" + filename

        db = get_db()
        db.execute("INSERT INTO posts (user_id, title, description, post_type, image_path, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                   (uid, title, desc, post_type, image_path))
        db.commit()
        db.close()
        flash("Post made!", "success")
        return redirect(url_for("home_feed"))

    return render_template("upload.html")

@app.route("/request_collab/<int:post_id>", methods=["POST"])
def request_collab(post_id):
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    from_user = session["user_id"]
    db = get_db()

    post = db.execute("SELECT user_id FROM posts WHERE id=?",
                      (post_id,)).fetchone()
    if not post or post["user_id"] == from_user:
        flash("Bad post!")
        db.close()
        return redirect(url_for("home_feed"))

    existing = db.execute(
        "SELECT id FROM collab_requests WHERE post_id=? AND from_user_id=? AND status='pending'", (post_id, from_user)).fetchone()
    if existing:
        flash("Already asked!")
        db.close()
        return redirect(url_for("home_feed"))

    db.execute("INSERT INTO collab_requests (post_id, from_user_id, to_user_id, status) VALUES (?, ?, ?, 'pending')",
               (post_id, from_user, post["user_id"]))
    db.commit()

    post_title = db.execute(
        "SELECT title FROM posts WHERE id=?", (post_id,)).fetchone()["title"]
    requester_name = db.execute(
        "SELECT full_name FROM users WHERE id=?", (from_user,)).fetchone()["full_name"]
    create_notification(post["user_id"], "new_collab_request",
                        "{} wants to collab on '{}'".format(requester_name, post_title))

    db.close()
    flash("Request sent!")
    return redirect(url_for("home_feed"))

@app.route("/approve_request/<int:req_id>", methods=["POST"])
def approve_request(req_id):
    if "user_id" not in session:
        return jsonify({"error": "Login!"}), 401

    to_user = session["user_id"]
    db = get_db()
    req = db.execute(
        "SELECT * FROM collab_requests WHERE id=? AND to_user_id=? AND status='pending'", (req_id, to_user)).fetchone()
    if not req:
        db.close()
        return jsonify({"error": "No request"}), 404

    db.execute(
        "UPDATE collab_requests SET status='accepted' WHERE id=?", (req_id,))
    post_title = db.execute(
        "SELECT title FROM posts WHERE id=?", (req["post_id"],)).fetchone()["title"]
    create_notification(req["from_user_id"], "request_accepted",
                        "Your collab request for '{}' accepted by {}".format(post_title, session["full_name"]))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/decline_request/<int:req_id>", methods=["POST"])
def decline_request(req_id):
    if "user_id" not in session:
        return jsonify({"error": "Login!"}), 401

    to_user = session["user_id"]
    db = get_db()
    req = db.execute(
        "SELECT * FROM collab_requests WHERE id=? AND to_user_id=? AND status='pending'", (req_id, to_user)).fetchone()
    if not req:
        db.close()
        return jsonify({"error": "No request"}), 404

    db.execute(
        "UPDATE collab_requests SET status='rejected' WHERE id=?", (req_id,))
    post_title = db.execute(
        "SELECT title FROM posts WHERE id=?", (req["post_id"],)).fetchone()["title"]
    create_notification(req["from_user_id"], "request_rejected",
                        "Your collab request for '{}' was declined.".format(post_title))
    db.commit()
    db.close()
    return jsonify({"success": True})

@app.route("/search")
def search():
    query = request.args.get('q', '').strip()
    db = get_db()

    posts = []
    if query:
        posts_sql =
        posts = db.execute(posts_sql, ('%' + query + '%',
                           '%' + query + '%')).fetchall()

    users = []
    if query:
        users_sql =
        users = db.execute(users_sql, ('%' + query + '%',
                           '%' + query + '%', '%' + query + '%')).fetchall()

    db.close()
    return render_template('search.html', query=query, users=users, posts=posts)

def create_notification(user_id, notif_type, message):
    db = get_db()
    db.execute("INSERT INTO notifications (user_id, type, message, is_read) VALUES (?, ?, ?, 0)",
               (user_id, notif_type, message))
    db.commit()
    db.close()

@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    user_id = session["user_id"]
    db = get_db()
    pending_requests = db.execute(, (user_id,)).fetchall()
    all_notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY is_read ASC, created_at DESC", (user_id,)).fetchall()
    unread = [n for n in all_notifs if n['is_read'] == 0]
    read_notifs = [n for n in all_notifs if n['is_read'] == 1]
    db.close()
    return render_template("notifications.html", pending_requests=pending_requests, unread=unread, read_notifs=read_notifs)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')