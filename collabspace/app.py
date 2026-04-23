import sqlite3
import time
import os
from flask import Flask, request, render_template, redirect, url_for, session, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "risa_dev_key")

DATABASE_FILE = "collab_space.db"

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()

def setup_db():
    try:
        with open('schema.sql', 'r') as f:
            sql_script = f.read()
        conn = sqlite3.connect(DATABASE_FILE)
        conn.executescript(sql_script)
        conn.commit()
        conn.close()
    except Exception as e:
        print("Database setup error:", e)

setup_db()

@app.route("/")
def home_page():
    if "user_id" in session:
        return redirect(url_for("feed"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_email = request.form.get("email")
        login_password = request.form.get("password")

        with get_db() as db:
            user_record = db.execute(
                "SELECT * FROM users WHERE email=?", (login_email,)).fetchone()
        if user_record and check_password_hash(user_record["password_hash"], login_password):
            session["user_id"] = user_record["id"]
            session["name"] = user_record["full_name"]
            session["username"] = user_record["username"] or ""

            return redirect(url_for("feed"))

        flash("Wrong email or password", "error")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        new_fullname = request.form.get("fullname")
        new_email = request.form.get("email")
        new_password = request.form.get("password")

        hashed_password = generate_password_hash(new_password)

        with get_db() as db:
            try:
                db.execute("INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                           (new_fullname, new_email, hashed_password))
                db.commit()
                flash("Account created successfully")
                return redirect(url_for("login"))
            except Exception as e:
                print("Email take, try another!")

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out!", "success")
    return redirect(url_for("login"))

@app.route("/home")
def feed():
    if "user_id" not in session:
        return redirect(url_for("login"))

    with get_db() as db:
        posts = db.execute(
            "SELECT p.*, u.full_name FROM posts p JOIN users u ON p.user_id = u.id ORDER BY p.created_at DESC LIMIT 10").fetchall()

    return render_template("home.html", posts=posts)

@app.route("/new", methods=["GET", "POST"])
def new_post():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        post_title = request.form["title"]
        post_desc = request.form.get("description", "")
        post_type = request.form.get("post_type", "need_help")
        current_user = session["user_id"]
        uploaded_image_path = None

        os.makedirs("static/posts", exist_ok=True)

        if "image" in request.files and request.files["image"].filename:
            f = request.files["image"]
            fname = "posts_{}_{}_{}".format(current_user, int(
                time.time()), secure_filename(f.filename))
            f.save(os.path.join("static/posts", fname))
            uploaded_image_path = "posts/{}".format(fname)

        with get_db() as db:
            db.execute("INSERT INTO posts (user_id, title, description, post_type, image_path, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                       (current_user, post_title, post_desc, post_type, uploaded_image_path))
            db.commit()

        flash("Post created successfully!", "success")
        return redirect(url_for("feed"))

    return render_template("upload.html")

@app.route("/request_collab/<int:post_id>", methods=["POST"])
def request_collab(post_id):
    print("DEBUG: request_collab called for post_id={}, user_id={}".format(
        post_id, session.get('user_id')))
    if "user_id" not in session:
        print("DEBUG: No user_id in session")
        return jsonify({'error': 'Login required'}), 401

    user_id = session["user_id"]

    try:
        with get_db() as db:
            post = db.execute(
                "SELECT user_id FROM posts WHERE id=?", (post_id,)).fetchone()
            if not post or post["user_id"] == user_id:
                print("DEBUG: Invalid post or own post")
                return jsonify({'error': "Can't request collab on your own post!"}), 400

            owner_id = post["user_id"]

            if db.execute("SELECT 1 FROM collab_requests WHERE post_id=? AND from_user_id=? AND status='pending'", (post_id, user_id)).fetchone():
                print("DEBUG: Duplicate request")
                return jsonify({'error': "Already requested this collab!"}), 400

            db.execute("INSERT INTO collab_requests (post_id, from_user_id, to_user_id, status) VALUES (?, ?, ?, 'pending')",
                       (post_id, user_id, owner_id))

            title = db.execute("SELECT title FROM posts WHERE id=?",
                               (post_id,)).fetchone()["title"]
            name = db.execute("SELECT full_name FROM users WHERE id=?",
                              (user_id,)).fetchone()["full_name"]
            create_notification(owner_id, "new_collab_request",
                                "{} wants to collab on '{}'".format(name, title))
            db.commit()
            print("DEBUG: Collab request created successfully")

        return jsonify({'success': True, 'message': 'Collab requested - check notifications!'})
    except Exception as e:
        print("DEBUG ERROR in request_collab: {}".format(e))
        return jsonify({'error': str(e)}), 500

def create_notification(user, typ, msg):

    with get_db() as db:
        db.execute(
            "INSERT INTO notifications (user_id, type, message) VALUES (?, ?, ?)",
            (user, typ, msg))
        db.commit()

@app.route("/approve_request/<int:request_id>", methods=["POST"])
def approve_request(request_id):

    if "user_id" not in session:
        return jsonify({"error": "Please login first!"}), 401

    owner_user_id = session["user_id"]

    with get_db() as db:
        req = db.execute(
            "SELECT * FROM collab_requests WHERE id=? AND to_user_id=? AND status='pending'",
            (request_id, owner_user_id)
        ).fetchone()
        if not req:
            return jsonify({"error": "No pending request"}), 404

        db.execute(
            "UPDATE collab_requests SET status='accepted' WHERE id=?", (request_id,))

        title = db.execute("SELECT title FROM posts WHERE id=?",
                           (req["post_id"],)).fetchone()["title"]
        create_notification(
            req["from_user_id"],
            "request_accepted",
            "Your collab request for '{}' was approved by {}".format(
                title, session['name'])
        )

        db.execute(
            "UPDATE notifications SET is_read=1 WHERE type='new_collab_request' AND user_id=? AND message LIKE ?",
            (owner_user_id, "%{}%".format(title))
        )
        db.commit()

    return jsonify({"success": True, "message": "Request approved!"})

@app.route("/decline_request/<int:request_id>", methods=["POST"])
def decline_request(request_id):

    if "user_id" not in session:
        return jsonify({"error": "Please login first!"}), 401

    owner_user_id = session["user_id"]

    with get_db() as db:
        req = db.execute(
            "SELECT * FROM collab_requests WHERE id=? AND to_user_id=? AND status='pending'",
            (request_id, owner_user_id)
        ).fetchone()
        if not req:
            return jsonify({"error": "No pending request"}), 404

        db.execute(
            "UPDATE collab_requests SET status='rejected' WHERE id=?", (request_id,))

        title = db.execute("SELECT title FROM posts WHERE id=?",
                           (req["post_id"],)).fetchone()["title"]
        create_notification(
            req["from_user_id"],
            "request_rejected",
            "Your collab request for '{}' was declined by {}".format(
                title, session['name'])
        )

        db.execute(
            "UPDATE notifications SET is_read=1 WHERE type='new_collab_request' AND user_id=? AND message LIKE ?",
            (owner_user_id, "%{}%".format(title))
        )
        db.commit()

    return jsonify({"success": True, "message": "Request declined"})

@app.route("/api/notif_count")
def api_notif_count():
    if "user_id" not in session:
        return jsonify({"count": 0})

    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(*) as unread FROM notifications WHERE user_id=? AND is_read=0",
            (session["user_id"],)
        ).fetchone()["unread"]

    return jsonify({"count": count})

@app.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    with get_db() as db:

        pending_requests = db.execute(, (user_id,)).fetchall()

        unread = db.execute(, (user_id,)).fetchall()

        read_notifs = db.execute(, (user_id,)).fetchall()

    return render_template("notifications.html",
                           pending_requests=pending_requests,
                           unread=unread,
                           read_notifs=read_notifs)

@app.route("/search")
def search():
    search_query = request.args.get('q', '').strip()

    with get_db() as db:
        term = "%{}%".format(search_query)
        posts = db.execute(
            "SELECT p.*, u.full_name FROM posts p JOIN users u ON p.user_id = u.id WHERE p.title LIKE ? OR p.description LIKE ? ORDER BY p.created_at DESC", (term, term)).fetchall()
        users = db.execute(
            "SELECT id, full_name, email, bio, created_at FROM users WHERE full_name LIKE ? OR email LIKE ? OR bio LIKE ? ORDER BY full_name", (term, term, term)).fetchall()

    return render_template('search.html', query=search_query, users=users, posts=posts)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)