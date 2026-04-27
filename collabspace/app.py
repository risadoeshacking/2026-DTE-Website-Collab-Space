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
        print("Database setup OK")
    except Exception as e:
        print("Database setup error:", e)

    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(notifications)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'type' in columns:
            print("Migrating notifications table: removing 'type' column...")
            cursor.executescript("""
                CREATE TABLE notifications_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                INSERT INTO notifications_new (id, user_id, message, is_read, created_at)
                SELECT id, user_id, message, is_read, created_at FROM notifications;
                DROP TABLE notifications;
                ALTER TABLE notifications_new RENAME TO notifications;
                CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC);
            """)
            conn.commit()
            print("Migration done.")
        conn.close()
    except Exception as e:
        print("Migration warning (can ignore if new DB):", e)

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
                print("Email taken, try another!", e)

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

    if "user_id" not in session:
        return jsonify({'error': 'Login required'}), 401

    user_id = session["user_id"]

    try:
        with get_db() as db:
            post = db.execute(
                "SELECT user_id, title FROM posts WHERE id=?", (post_id,)).fetchone()
            if not post or post["user_id"] == user_id:
                return jsonify({'error': "Can't request collab on your own post!"}), 400

            owner_id = post["user_id"]

            if db.execute("SELECT 1 FROM collab_requests WHERE post_id=? AND from_user_id=? AND status='pending'", (post_id, user_id)).fetchone():
                return jsonify({'error': "Already requested this collab!"}), 400

            db.execute("INSERT INTO collab_requests (post_id, from_user_id, to_user_id, status) VALUES (?, ?, ?, 'pending')",
                       (post_id, user_id, owner_id))

            name = db.execute(
                "SELECT full_name FROM users WHERE id=?", (user_id,)).fetchone()["full_name"]
            title = post["title"]
            msg = "{} wants to collab on '{}'".format(name, title)
            create_notification(db, owner_id, msg)

            db.commit()

        return jsonify({'success': True, 'message': 'Collab requested - check notifications!'})
    except Exception as e:
        print("ERROR in request_collab:", e)
        return jsonify({'error': str(e)}), 500

def create_notification(db, user_id, message):
    """Insert a notification using the EXISTING db connection.
    This prevents nested connections which caused network errors."""
    db.execute(
        "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
        (user_id, message))

@app.route("/approve_request/<int:request_id>", methods=["POST"])
def approve_request(request_id):

    if "user_id" not in session:
        return jsonify({"error": "Please login first!"}), 401

    owner_user_id = session["user_id"]

    try:
        with get_db() as db:
            req = db.execute(
                "SELECT * FROM collab_requests WHERE id=? AND to_user_id=? AND status='pending'",
                (request_id, owner_user_id)
            ).fetchone()
            if not req:
                return jsonify({"error": "No pending request found"}), 404

            db.execute(
                "UPDATE collab_requests SET status='accepted' WHERE id=?", (request_id,))

            title = db.execute("SELECT title FROM posts WHERE id=?",
                               (req["post_id"],)).fetchone()["title"]
            msg = "Your collab request for '{}' was approved by {}".format(
                title, session['name'])
            create_notification(db, req["from_user_id"], msg)

            db.commit()

        return jsonify({"success": True, "message": "Request approved!"})
    except Exception as e:
        print("ERROR in approve_request:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/decline_request/<int:request_id>", methods=["POST"])
def decline_request(request_id):

    if "user_id" not in session:
        return jsonify({"error": "Please login first!"}), 401

    owner_user_id = session["user_id"]

    try:
        with get_db() as db:
            req = db.execute(
                "SELECT * FROM collab_requests WHERE id=? AND to_user_id=? AND status='pending'",
                (request_id, owner_user_id)
            ).fetchone()
            if not req:
                return jsonify({"error": "No pending request found"}), 404

            db.execute(
                "UPDATE collab_requests SET status='rejected' WHERE id=?", (request_id,))

            title = db.execute("SELECT title FROM posts WHERE id=?",
                               (req["post_id"],)).fetchone()["title"]
            msg = "Your collab request for '{}' was declined by {}".format(
                title, session['name'])
            create_notification(db, req["from_user_id"], msg)

            db.commit()

        return jsonify({"success": True, "message": "Request declined"})
    except Exception as e:
        print("ERROR in decline_request:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/api/notif_count")
def api_notif_count():

    if "user_id" not in session:
        return jsonify({"count": 0})

    try:
        with get_db() as db:
            count = db.execute(
                "SELECT COUNT(*) as unread FROM notifications WHERE user_id=? AND is_read=0",
                (session["user_id"],)
            ).fetchone()["unread"]
        return jsonify({"count": count})
    except Exception as e:
        print("ERROR in api_notif_count:", e)
        return jsonify({"count": 0})

@app.route("/notifications")
def notifications():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    try:
        with get_db() as db:

            pending_requests = db.execute("""
                SELECT cr.id, cr.created_at, p.title as post_title, u.full_name as from_name
                FROM collab_requests cr
                JOIN posts p ON cr.post_id = p.id
                JOIN users u ON cr.from_user_id = u.id
                WHERE cr.to_user_id = ? AND cr.status = 'pending'
                ORDER BY cr.created_at DESC
            """, (user_id,)).fetchall()

            unread = db.execute("""
                SELECT * FROM notifications
                WHERE user_id = ? AND is_read = 0
                ORDER BY created_at DESC
            """, (user_id,)).fetchall()

            read_notifs = db.execute("""
                SELECT * FROM notifications
                WHERE user_id = ? AND is_read = 1
                ORDER BY created_at DESC
                LIMIT 20
            """, (user_id,)).fetchall()

        return render_template("notifications.html",
                               pending_requests=pending_requests,
                               unread=unread,
                               read_notifs=read_notifs)
    except Exception as e:
        print("ERROR in notifications route:", e)
        flash("Could not load notifications", "error")
        return redirect(url_for("feed"))

@app.route("/mark_read/<int:notif_id>", methods=["POST"])
def mark_read(notif_id):

    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    try:
        with get_db() as db:
            db.execute(
                "UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
                (notif_id, session["user_id"])
            )
            db.commit()
        return jsonify({"success": True})
    except Exception as e:
        print("ERROR in mark_read:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/mark_all_read", methods=["POST"])
def mark_all_read():

    if "user_id" not in session:
        return jsonify({"error": "Login required"}), 401

    try:
        with get_db() as db:
            db.execute(
                "UPDATE notifications SET is_read=1 WHERE user_id=?",
                (session["user_id"],)
            )
            db.commit()
        return jsonify({"success": True})
    except Exception as e:
        print("ERROR in mark_all_read:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        posts = db.execute(
            "SELECT * FROM posts WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)).fetchall()

    return render_template("profile.html", user=user, posts=posts)

@app.route("/profile/edit", methods=["GET", "POST"])
def edit_profile():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    if request.method == "POST":
        new_name = request.form.get("full_name", "").strip()
        new_bio = request.form.get("bio", "").strip()

        with get_db() as db:
            db.execute(
                "UPDATE users SET full_name=?, bio=? WHERE id=?",
                (new_name, new_bio, user_id))
            db.commit()

            session["name"] = new_name

        flash("Profile updated!", "success")
        return redirect(url_for("profile"))

    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    return render_template("edit_profile.html", user=user)

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