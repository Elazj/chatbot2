"""
Chat-centred API: conversations, messages, feedback, settings and profile.

Every route needs a logged-in student (login_required) and every database
lookup is filtered by that student's id. Asking for a conversation, message
or document that belongs to someone else gives the same 404 as one that
doesn't exist, so ids can't be used to probe other accounts.
"""

import json
import re
from datetime import timedelta

from flask import Blueprint, Response, g, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

import auth
import chatbot
import db
import reminders
from config import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from learning import progress

bp = Blueprint("api_chat", __name__)

# Strictness presets for searching the student's own documents. The number is
# the minimum TF-IDF cosine similarity a passage needs before it is shown.
RAG_STRICTNESS = {"relaxed": 0.08, "balanced": 0.12, "strict": 0.22}

SETTING_DEFAULTS = {
    # General
    "show_timestamps": True,
    # Documents / RAG
    "show_sources": True,
    "rag_passages": 3,              # how many passages are retrieved per question (1-5)
    "rag_strictness": "balanced",   # relaxed | balanced | strict (see RAG_STRICTNESS)
    "rag_fallback": True,           # search my documents when the UTG knowledge base has no answer
    # Kept from earlier versions (no longer shown in Settings)
    "voice_input": True,
    "voice_output": False,
    "voice_lang": "en-GB",
    "reminder_popups": True,
    "study_goals": "",
    "learning_style": "",
}


def err(message, code=400):
    return jsonify(error=message), code


def not_found():
    return err("Not found.", 404)


def get_settings(user_id: int) -> dict:
    row = db.fetchone("SELECT data FROM user_settings WHERE user_id = ?", (user_id,))
    data = {}
    if row:
        try:
            data = json.loads(row["data"])
        except ValueError:
            data = {}
    return {**SETTING_DEFAULTS, **{k: v for k, v in data.items() if k in SETTING_DEFAULTS}}


def save_settings(user_id: int, updates: dict) -> dict:
    current = get_settings(user_id)
    for key, val in updates.items():
        if key not in SETTING_DEFAULTS:
            continue
        default = SETTING_DEFAULTS[key]
        if isinstance(default, bool):
            current[key] = bool(val)
        elif key == "rag_passages":
            try:
                current[key] = max(1, min(5, int(val)))
            except (TypeError, ValueError):
                pass
        elif key == "rag_strictness":
            if val in RAG_STRICTNESS:
                current[key] = val
        elif isinstance(val, str):
            current[key] = val.strip()[:500 if key == "study_goals" else 100]
    db.execute(
        "INSERT INTO user_settings (user_id, data) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET data = excluded.data",
        (user_id, json.dumps(current)),
    )
    return current


# ----------------------------------------------------------- conversations

def _group_label(updated_at: str) -> str:
    d = progress.today()
    try:
        day = progress.date.fromisoformat((updated_at or "")[:10])
    except ValueError:
        return "Older"
    if day >= d:
        return "Today"
    if day == d - timedelta(days=1):
        return "Yesterday"
    if day >= d - timedelta(days=7):
        return "Previous 7 days"
    return "Older"


def _new_conversation(user) -> dict:
    cid = db.create_conversation(user["id"])
    db.add_message(user["id"], "bot", chatbot.greeting_for(user), conversation_id=cid)
    return db.get_conversation(user["id"], cid)


def _conv_payload(conv) -> dict:
    doc = None
    if conv.get("document_id"):
        d = db.fetchone("SELECT id, filename, status FROM documents WHERE id = ? AND user_id = ?", (conv["document_id"], g.user["id"]))
        if d:
            doc = d
    return {"id": conv["id"], "title": conv["title"], "document": doc}


@bp.route("/api/conversations")
@auth.login_required
def list_conversations():
    rows = db.list_conversations(g.user["id"], request.args.get("q", "").strip()[:100])
    order, groups = ["Today", "Yesterday", "Previous 7 days", "Older"], {}
    for r in rows:
        groups.setdefault(_group_label(r["updated_at"]), []).append(r)
    return jsonify(groups=[{"label": k, "items": groups[k]} for k in order if k in groups])


@bp.route("/api/conversations", methods=["POST"])
@auth.login_required
def create_conversation():
    session.pop("pending", None)
    conv = _new_conversation(g.user)
    return jsonify(conversation=_conv_payload(conv), messages=db.get_messages(g.user["id"], conversation_id=conv["id"]))


@bp.route("/api/conversations/<int:cid>")
@auth.login_required
def open_conversation(cid):
    conv = db.get_conversation(g.user["id"], cid)
    if not conv:
        return not_found()
    return jsonify(conversation=_conv_payload(conv), messages=db.get_messages(g.user["id"], conversation_id=cid))


@bp.route("/api/conversations/<int:cid>/rename", methods=["POST"])
@auth.login_required
def rename_conversation(cid):
    if not db.get_conversation(g.user["id"], cid):
        return not_found()
    title = " ".join(str((request.get_json(silent=True) or {}).get("title", "")).split())[:80]
    if not title:
        return err("Please enter a name.")
    db.execute("UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?", (title, cid, g.user["id"]))
    return jsonify(ok=True, title=title)


@bp.route("/api/conversations/<int:cid>", methods=["DELETE"])
@auth.login_required
def delete_conversation(cid):
    if not db.get_conversation(g.user["id"], cid):
        return not_found()
    db.execute("DELETE FROM conversations WHERE id = ? AND user_id = ?", (cid, g.user["id"]))
    session.pop("pending", None)
    return jsonify(ok=True)


@bp.route("/api/conversations/<int:cid>/context", methods=["POST"])
@auth.login_required
def set_context(cid):
    conv = db.get_conversation(g.user["id"], cid)
    if not conv:
        return not_found()
    body = request.get_json(silent=True) or {}
    if "document_id" in body:
        doc_id = body["document_id"]
        if doc_id is not None:
            doc = db.fetchone("SELECT id FROM documents WHERE id = ? AND user_id = ? AND status = 'ready'", (doc_id, g.user["id"]))
            if not doc:
                return not_found()
        db.execute("UPDATE conversations SET document_id = ? WHERE id = ? AND user_id = ?", (doc_id, cid, g.user["id"]))
    return jsonify(conversation=_conv_payload(db.get_conversation(g.user["id"], cid)))


@bp.route("/api/history")
@auth.login_required
def history():
    """The latest conversation (created, with a greeting, for a new account)."""
    conv = db.latest_conversation(g.user["id"]) or _new_conversation(g.user)
    return jsonify(conversation=_conv_payload(conv), messages=db.get_messages(g.user["id"], conversation_id=conv["id"]))


@bp.route("/api/history/clear", methods=["POST"])
@bp.route("/api/clear", methods=["POST"])
@auth.login_required
def clear_history():
    """Delete every chat. Documents, notes, quizzes, flashcards, plans and
    progress are NOT touched."""
    db.clear_all_conversations(g.user["id"])
    session.pop("pending", None)
    conv = _new_conversation(g.user)
    return jsonify(ok=True, conversation=_conv_payload(conv), messages=db.get_messages(g.user["id"], conversation_id=conv["id"]))


# --------------------------------------------------------------- chatting

def _context(conv) -> dict:
    st = get_settings(g.user["id"])
    ctx = {"rag_k": st["rag_passages"], "rag_min_score": RAG_STRICTNESS[st["rag_strictness"]], "rag_fallback": st["rag_fallback"]}
    if conv.get("document_id"):
        d = db.fetchone("SELECT id, course_id FROM documents WHERE id = ? AND user_id = ? AND status = 'ready'", (conv["document_id"], g.user["id"]))
        if d:
            ctx["document_id"], ctx["course_id"] = d["id"], d["course_id"]
    return ctx


def _store_reply(conv_id: int, res) -> list:
    ids = []
    n = len(res.replies)
    for i, line in enumerate(res.replies):
        meta = {"intent": res.intent}
        if i == n - 1:
            meta["sources"], meta["actions"] = res.sources, res.actions
        ids.append(db.add_message(g.user["id"], "bot", line, conversation_id=conv_id, meta=meta))
    return ids


def _reply_payload(conv_id, res, ids, title=None):
    return {"conversation_id": conv_id, "title": title, "replies": res.replies, "message_ids": ids,
            "sources": res.sources, "actions": res.actions, "intent": res.intent}


@bp.route("/api/chat", methods=["POST"])
@auth.login_required
def chat():
    payload = request.get_json(silent=True) or {}
    text = " ".join(str(payload.get("text") or "").split())
    if not text:
        return err("Please type a message.")
    if len(text) > chatbot.MAX_MESSAGE_CHARS:
        return err(f"Please keep messages under {chatbot.MAX_MESSAGE_CHARS} characters.")

    uid = g.user["id"]
    cid = payload.get("conversation_id")
    conv = db.get_conversation(uid, cid) if cid else db.latest_conversation(uid)
    if cid and not conv:
        return not_found()
    if not conv:
        conv = _new_conversation(g.user)

    user_msg_id = db.add_message(uid, "user", text, conversation_id=conv["id"])
    pending = session.get("pending") if session.get("pending_conv") == conv["id"] else None
    ctx = _context(conv)
    res = chatbot.respond_rich(g.user, text, pending, ctx)

    if res.pending:
        session["pending"], session["pending_conv"] = res.pending, conv["id"]
    else:
        session.pop("pending", None)
        session.pop("pending_conv", None)

    title = None
    if conv["title"] == "New chat":
        title = text[:40] + ("..." if len(text) > 40 else "")
        db.execute("UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?", (title, conv["id"], uid))
    ids = _store_reply(conv["id"], res)
    progress.record_event(uid, "doc_chat" if ctx.get("document_id") else "chat", ctx.get("document_id"))
    out = _reply_payload(conv["id"], res, ids, title)
    out["user_message_id"] = user_msg_id
    return jsonify(out)


@bp.route("/api/chat/regenerate", methods=["POST"])
@auth.login_required
def regenerate():
    uid = g.user["id"]
    cid = (request.get_json(silent=True) or {}).get("conversation_id")
    conv = db.get_conversation(uid, cid) if cid else db.latest_conversation(uid)
    if not conv:
        return not_found()
    last_user = db.fetchone("SELECT id, content FROM messages WHERE user_id = ? AND conversation_id = ? AND role = 'user' ORDER BY id DESC LIMIT 1",
                            (uid, conv["id"]))
    if not last_user:
        return err("There is nothing to regenerate yet.")
    db.execute("DELETE FROM messages WHERE user_id = ? AND conversation_id = ? AND id > ?", (uid, conv["id"], last_user["id"]))
    res = chatbot.respond_rich(g.user, last_user["content"], None, _context(conv))
    ids = _store_reply(conv["id"], res)
    return jsonify(_reply_payload(conv["id"], res, ids))


@bp.route("/api/messages/<int:mid>/feedback", methods=["POST"])
@auth.login_required
def feedback(mid):
    msg = db.fetchone("SELECT id FROM messages WHERE id = ? AND user_id = ? AND role = 'bot'", (mid, g.user["id"]))
    if not msg:
        return not_found()
    value = (request.get_json(silent=True) or {}).get("value")
    if value == 0:
        db.execute("DELETE FROM message_feedback WHERE message_id = ? AND user_id = ?", (mid, g.user["id"]))
    elif value in (1, -1):
        db.execute("INSERT INTO message_feedback (message_id, user_id, value) VALUES (?, ?, ?) "
                   "ON CONFLICT(message_id) DO UPDATE SET value = excluded.value", (mid, g.user["id"], value))
    else:
        return err("Feedback must be 1, -1 or 0.")
    return jsonify(ok=True)


@bp.route("/api/due_reminders")
@auth.login_required
def due_reminders():
    """Reminders due today or overdue, shown once each when the page opens
    (unless the student turned reminder pop-ups off in Settings)."""
    if not get_settings(g.user["id"])["reminder_popups"]:
        return jsonify(due=[])
    lines = []
    conv = db.latest_conversation(g.user["id"])
    for r in reminders.get_due_reminders(g.user["id"]):
        text = chatbot.format_due_reminder(r)
        db.add_message(g.user["id"], "bot", text, conversation_id=conv["id"] if conv else None)
        lines.append(text)
    return jsonify(due=lines)


@bp.route("/api/capabilities")
@auth.login_required
def capabilities():
    return jsonify(llm=False, notes="Answers come only from the UTG knowledge base, the UTG course catalogue and your own documents. No AI or language model is used.")


# ------------------------------------------------------ settings / profile

@bp.route("/api/settings", methods=["GET", "POST"])
@auth.login_required
def settings():
    if request.method == "POST":
        return jsonify(settings=save_settings(g.user["id"], request.get_json(silent=True) or {}))
    return jsonify(settings=get_settings(g.user["id"]))


@bp.route("/api/profile", methods=["GET", "POST"])
@auth.login_required
def profile():
    uid = g.user["id"]
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        if "full_name" in body:
            name = " ".join(str(body["full_name"]).split())
            if not 2 <= len(name) <= 80:
                return err("Enter your full name (2 to 80 characters).")
            db.execute("UPDATE users SET full_name = ? WHERE id = ?", (name, uid))
        save_settings(uid, {k: body[k] for k in ("study_goals", "learning_style") if k in body})
    u = db.get_user_by_id(uid)
    s = get_settings(uid)
    return jsonify(profile={"full_name": u["full_name"], "email": u["email"], "created_at": u["created_at"],
                            "study_goals": s["study_goals"], "learning_style": s["learning_style"]})


@bp.route("/api/profile/password", methods=["POST"])
@auth.login_required
def change_password():
    body = request.get_json(silent=True) or {}
    current, new = str(body.get("current", "")), str(body.get("new", ""))
    user = db.get_user_by_id(g.user["id"])
    if not check_password_hash(user["password_hash"], current[:MAX_PASSWORD_LENGTH]):
        return err("Your current password is incorrect.", 403)
    if not MIN_PASSWORD_LENGTH <= len(new) <= MAX_PASSWORD_LENGTH:
        return err(f"Use {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters for the new password.")
    if new.lower() in (user["email"].lower(), user["full_name"].lower()):
        return err("Your password can't be the same as your name or email.")
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), user["id"]))
    return jsonify(ok=True)


@bp.route("/api/export")
@auth.login_required
def export_data():
    uid = g.user["id"]
    q = lambda sql: db.fetchall(sql, (uid,))
    data = {
        "profile": {"full_name": g.user["full_name"], "email": g.user["email"], "settings": get_settings(uid)},
        "conversations": [{**c, "messages": [{k: m[k] for k in ("role", "content", "created_at")} for m in db.get_messages(uid, 1000, c["id"])]}
                          for c in q("SELECT id, title, created_at FROM conversations WHERE user_id = ?")],
        "courses": q("SELECT name FROM courses WHERE user_id = ?"),
        "notes": q("SELECT title, content, created_at FROM notes WHERE user_id = ?"),
        "documents": q("SELECT id, filename, kind, created_at FROM documents WHERE user_id = ?"),
        "quizzes": q("SELECT id, title, kind, created_at FROM quizzes WHERE user_id = ?"),
        "quiz_attempts": q("SELECT quiz_id, score, total, created_at FROM quiz_attempts WHERE user_id = ?"),
        "flashcards": q("SELECT front, back, topic, due_date FROM flashcards WHERE user_id = ?"),
        "reminders": q("SELECT description, due_date FROM reminders WHERE user_id = ?"),
        "study_plans": q("SELECT title, exam_date FROM study_plans WHERE user_id = ?"),
    }
    return Response(json.dumps(data, indent=2, default=str), mimetype="application/json",
                    headers={"Content-Disposition": "attachment; filename=nocturna-my-data.json"})


@bp.route("/api/data/delete", methods=["POST"])
@auth.login_required
def delete_data():
    uid = g.user["id"]
    body = request.get_json(silent=True) or {}
    what = body.get("what")
    if body.get("confirm") != "DELETE":
        return err("Type DELETE to confirm.")
    if what == "documents":
        db.execute("DELETE FROM documents WHERE user_id = ?", (uid,))
    elif what == "notes":
        db.execute("DELETE FROM notes WHERE user_id = ?", (uid,))
    elif what == "learning":
        for table in ("quizzes", "flashcards", "study_plans", "study_events", "past_exam_analyses"):
            db.execute(f"DELETE FROM {table} WHERE user_id = ?", (uid,))   # table names are fixed above, not user input
    elif what == "account":
        user = db.get_user_by_id(uid)
        if not check_password_hash(user["password_hash"], str(body.get("password", ""))[:MAX_PASSWORD_LENGTH]):
            return err("Enter your password to delete your account.", 403)
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
        session.clear()
    else:
        return err("Unknown option.")
    return jsonify(ok=True)
