"""
Lightweight reminder system for academic deadlines (registration windows,
exam dates, document submissions, etc.).

This is the one piece of this project that email and WhatsApp groups
structurally cannot do: track something specific to ONE student and
proactively resurface it, rather than broadcasting the same message to
everyone and relying on each person to remember it. A group chat can tell
300 students "registration closes Friday" -- it can't tell you, three weeks
later, "you still haven't registered and it's due tomorrow."

Reminders now live in the database (see db.py), one set per account. Each
has a description, a due date, and whether it's already been announced once
(so the chatbot doesn't repeat the same reminder every time the page loads,
forever).

Dates use UTC, which is the same as local time in The Gambia, so "today"
doesn't depend on which country the server happens to be hosted in.
"""

import re
from datetime import date, datetime, timedelta, timezone

import db


def _today() -> date:
    return datetime.now(timezone.utc).date()


def parse_due_date(text: str):
    """
    Deliberately simple date parsing -- NOT a full natural-language date
    parser, just enough to cover realistic phrasing for a typed deadline:
        "today"
        "tomorrow"
        "in 3 days" / "in 1 day"
        "2026-11-05"  (explicit ISO date, year-month-day)
    Returns a date, or None if it couldn't be parsed.
    """
    text = text.strip().lower()

    if text == "today":
        return _today()
    if text == "tomorrow":
        return _today() + timedelta(days=1)

    match = re.search(r"in (\d+) days?", text)
    if match:
        return _today() + timedelta(days=int(match.group(1)))

    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    return None


_REMINDER_PATTERN = re.compile(
    r"remind me (?:to )?(.+?)\s+"
    r"(today|tomorrow|in \d+ days?|on \d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE,
)


def parse_reminder_command(text: str):
    """
    Tries to parse a COMPLETE reminder request from one utterance, e.g.
        "remind me to submit my assignment in 3 days"
        "remind me to register for classes on 2026-11-05"
        "remind me to pay fees tomorrow"
    so a single typed line works without a follow-up question.

    Returns (description, due_text) if both were found, else (None, None)
    -- callers should fall back to asking for the missing piece in that case.
    """
    match = _REMINDER_PATTERN.search(text.strip())
    if not match:
        return None, None
    description = match.group(1).strip()
    due_text = match.group(2).strip().lower()
    if due_text.startswith("on "):
        due_text = due_text[3:]
    if not description:
        return None, None
    return description, due_text


def add_reminder(user_id: int, description: str, due_text: str):
    """Returns (success: bool, message: str) -- message is ready to show
    either way (confirmation, or an explanation of what went wrong)."""
    due = parse_due_date(due_text)
    if due is None:
        return False, (
            "I couldn't understand that date. Try a date like 2026-11-05 "
            "(year-month-day), or say 'tomorrow' or 'in 3 days'."
        )
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO reminders (user_id, description, due_date) VALUES (?, ?, ?)",
            (user_id, description, due.isoformat()),
        )
    return True, f"Okay, I'll remind you to {description} on {due.strftime('%B %d, %Y')}."


def get_due_reminders(user_id: int, mark_announced: bool = True):
    """Reminders due today or earlier that haven't been announced yet --
    this is what the chat page shows automatically when it loads."""
    today = _today().isoformat()
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT id, description, due_date FROM reminders "
            "WHERE user_id = ? AND announced = 0 AND due_date <= ? ORDER BY due_date",
            (user_id, today),
        ).fetchall()
        due = [dict(r) for r in rows]
        if mark_announced and due:
            conn.executemany(
                "UPDATE reminders SET announced = 1 WHERE id = ?", [(r["id"],) for r in due]
            )
    return due


def get_upcoming_reminders(user_id: int, within_days: int = 14):
    """Everything due within the next N days (including today) -- for when
    the student actively asks 'what are my reminders'. Doesn't mark them
    announced, since asking isn't the same as being proactively notified."""
    today = _today()
    cutoff = today + timedelta(days=within_days)
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT description, due_date FROM reminders "
            "WHERE user_id = ? AND due_date BETWEEN ? AND ? ORDER BY due_date",
            (user_id, today.isoformat(), cutoff.isoformat()),
        ).fetchall()
    return [dict(r) for r in rows]
