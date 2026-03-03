import sqlite3
from pathlib import Path
from flask import Flask, render_template

app = Flask(__name__, static_folder='static', static_url_path='/static')

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
def feed():
    init_db()
    conn = db()
    rows = conn.execute().fetchall()
    conn.close()

    if not rows:
        return "working"
    return "Nice \n\n" + "\n".join(
        [f"- [{r['post_type']}] {r['title']} (by {r['full_name']})" for r in rows]
    )

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/register")
def register():
    return render_template("register.html")

if __name__ == "__main__":
    app.run(debug=True)