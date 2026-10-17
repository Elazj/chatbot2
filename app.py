"""
Web app for Nocturna: a login-protected, chat-centred AI-free study assistant
for UTG students.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser. You'll be sent to the login
page; create an account on the sign-up page the first time.

Layout:
    auth.py          sign up / log in / log out, CSRF protection, login_required
    api_chat.py      conversations, chat, feedback, settings, profile
    api_learning.py  documents, notes, quizzes, flashcards, plans, progress...
    chatbot.py       the assistant's routing (text in, text out)
    learning/        document ingestion, retrieval, quiz/flashcard generation,
                     planner, progress, past-exam analysis, code help (no AI/LLM anywhere)
    db.py            SQLite storage

The page has exactly five navigation items (New Chat, Chat History, Settings,
User Profile, Clear Chat History). Every learning feature is reached from
inside the chat: the composer's ＋ menu, document cards, reply buttons, or
chat commands.
"""

from datetime import timedelta

from flask import Flask, g, jsonify, render_template, request

import api_chat
import api_learning
import auth
import db
from config import COOKIE_SECURE, SECRET_KEY, SESSION_DAYS

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),
    MAX_CONTENT_LENGTH=20 * 1024 * 1024,   # room for a 15 MB document plus the form
)

db.init_db()
auth.init_app(app)  # CSRF, current-user loader, and the /login /signup /logout routes
app.register_blueprint(api_chat.bp)
app.register_blueprint(api_learning.bp)


@app.after_request
def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/")
@auth.login_required
def index():
    return render_template("chat.html", user=g.user)


@app.errorhandler(400)
def _bad_request(err):
    return render_template("error.html", message=getattr(err, "description", "Bad request.")), 400


@app.errorhandler(413)
def _too_large(err):
    return jsonify(error="That file or message is too large."), 413


if __name__ == "__main__":
    # debug stays off on purpose: Flask's debugger lets anyone who can reach
    # the page run code on your machine.
    app.run(host="127.0.0.1", port=5000, debug=False)
