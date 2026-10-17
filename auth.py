"""
Accounts for Nocturna: sign up, log in, log out.

What this covers:
  * Passwords are never stored -- only a salted hash (werkzeug's
    generate_password_hash, which uses scrypt by default).
  * Only UTG student emails are accepted (sign up AND log in): first letter of
    the first name + first letter of the second name + student number +
    @utg.edu.gm, e.g. aj2211234@utg.edu.gm. At sign-up the two initials must
    also match the name the student typed.
  * Login errors are deliberately vague ("incorrect email or password") so
    the form can't be used to discover which emails are registered.
  * After 5 failed logins for the same email + IP within 10 minutes, further
    attempts are refused until the window passes. This counter lives in
    memory, so it resets if the server restarts and is per-process -- fine
    for a single-server project, use a shared store (e.g. Redis) if you ever
    run several workers.
  * Every POST needs a CSRF token (form field `csrf_token` or header
    `X-CSRF-Token`), so another website can't make a logged-in student's
    browser submit requests on their behalf.
  * The `next` redirect after login only accepts paths on this site.
"""

import re
import secrets
import sqlite3
import unicodedata
import time
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import db
from config import (MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, STUDENT_NUMBER_MAX_DIGITS,
                    STUDENT_NUMBER_MIN_DIGITS, UTG_EMAIL_DOMAIN)

bp = Blueprint("auth", __name__)

# UTG student email: two letters (initials) + student number + @utg.edu.gm
_UTG_EMAIL_RE = re.compile(
    r"^([a-z])([a-z])(\d{%d,%d})@%s$" % (STUDENT_NUMBER_MIN_DIGITS, STUDENT_NUMBER_MAX_DIGITS, re.escape(UTG_EMAIL_DOMAIN))
)
UTG_EMAIL_HELP = (
    "Use your UTG student email: the first letter of your first name, the first letter of your second name, "
    f"your student number, then @{UTG_EMAIL_DOMAIN} (for example aj2211234@{UTG_EMAIL_DOMAIN})."
)


def _first_letter(word: str) -> str:
    """First letter of a name as plain a-z (so 'Émilie' gives 'e')."""
    plain = unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode()
    return plain[:1].lower()


def utg_email_problem(email: str, full_name: str | None = None) -> str | None:
    """Return a message explaining what is wrong with `email`, or None if it is a valid UTG student email.

    With `full_name` given (sign-up) the two initials must also match the
    student's first and second name. A name with more than two words is
    accepted if the second letter matches the second word OR the last word,
    e.g. 'Awa Fatou Jallow' may use aj... or af....
    """
    m = _UTG_EMAIL_RE.match(email or "")
    if not m:
        return UTG_EMAIL_HELP
    if full_name is not None:
        words = full_name.split()
        if len(words) < 2:
            return "Enter your first name and your second name."
        first, second = m.group(1), m.group(2)
        if first != _first_letter(words[0]) or second not in {_first_letter(words[1]), _first_letter(words[-1])}:
            return (f"The first two letters of your email ({first}{second}) must be the first letters of your first and "
                    "second name. Check your name and your email.")
    return None

# Used when the email isn't registered, so a wrong-email attempt takes about
# as long as a wrong-password attempt (avoids a timing leak).
_DUMMY_HASH = generate_password_hash("not-a-real-password")

_MAX_FAILED_LOGINS = 5
_LOCKOUT_WINDOW_S = 600
_failed_logins = {}


# ------------------------------------------------------------------ CSRF

def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def init_app(app) -> None:
    """Wire up CSRF protection, the current-user loader and template helpers."""
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _check_csrf():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            expected = session.get("csrf", "")
            if not expected or not secrets.compare_digest(sent, expected):
                if request.path.startswith("/api/"):
                    return jsonify(error="Your session expired. Please refresh the page."), 400
                abort(400, description="Your session expired. Go back, refresh the page and try again.")

    @app.before_request
    def _load_user():
        g.user = None
        user_id = session.get("user_id")
        if user_id is not None:
            user = db.get_user_by_id(user_id)
            if user is None:  # account no longer exists
                session.clear()
            else:
                g.user = user

    app.register_blueprint(bp)


# ------------------------------------------------------- access control

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return jsonify(error="Please log in."), 401
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _safe_next(target):
    """Only allow redirects to a path on this site (blocks //evil.com etc.)."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def _start_session(user_id: int) -> None:
    session.clear()  # drops any pre-login state, including the old CSRF token
    session["user_id"] = user_id
    session.permanent = True


# ------------------------------------------------------------ throttling

def _throttle_key(email: str) -> str:
    return f"{request.remote_addr}|{email}"


def _is_throttled(key: str) -> bool:
    now = time.time()
    recent = [t for t in _failed_logins.get(key, []) if now - t < _LOCKOUT_WINDOW_S]
    if recent:
        _failed_logins[key] = recent
    else:
        _failed_logins.pop(key, None)
    return len(recent) >= _MAX_FAILED_LOGINS


def _record_failure(key: str) -> None:
    _failed_logins.setdefault(key, []).append(time.time())


# ----------------------------------------------------------------- routes

@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if g.user:
        return redirect(url_for("index"))

    errors = {}
    form = {"full_name": "", "email": ""}

    if request.method == "POST":
        full_name = " ".join(request.form.get("full_name", "").split())
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        form = {"full_name": full_name, "email": email}

        if not 2 <= len(full_name) <= 80 or len(full_name.split()) < 2:
            errors["full_name"] = "Enter your first name and second name (2 to 80 characters)."
        email_problem = utg_email_problem(email, full_name if "full_name" not in errors else None)
        if email_problem:
            errors["email"] = email_problem
        if len(password) < MIN_PASSWORD_LENGTH:
            errors["password"] = f"Use at least {MIN_PASSWORD_LENGTH} characters."
        elif len(password) > MAX_PASSWORD_LENGTH:
            errors["password"] = f"Use at most {MAX_PASSWORD_LENGTH} characters."
        elif password.lower() == email or password.lower() == full_name.lower():
            errors["password"] = "Your password can't be the same as your name or email."
        if "password" not in errors and password != confirm:
            errors["confirm"] = "The two passwords don't match."

        if not errors:
            try:
                user_id = db.create_user(full_name, email, generate_password_hash(password))
            except sqlite3.IntegrityError:
                errors["email"] = "An account with this email already exists. Try logging in."
            else:
                _start_session(user_id)
                return redirect(url_for("index"))

    return render_template("signup.html", errors=errors, form=form), (400 if errors else 200)


@bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = _safe_next(request.values.get("next"))

    if g.user:
        return redirect(next_url or url_for("index"))

    error = None
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        key = _throttle_key(email)

        if not _UTG_EMAIL_RE.match(email):
            # Only UTG student emails can log in (even if an older account exists with another address).
            error = UTG_EMAIL_HELP
        elif _is_throttled(key):
            error = "Too many failed attempts. Please wait a few minutes and try again."
        else:
            user = db.get_user_by_email(email) if email else None
            stored_hash = user["password_hash"] if user else _DUMMY_HASH
            password_ok = check_password_hash(stored_hash, password[:MAX_PASSWORD_LENGTH])
            if user and password_ok:
                _failed_logins.pop(key, None)
                _start_session(user["id"])
                return redirect(next_url or url_for("index"))
            _record_failure(key)
            error = "Incorrect email or password."

    return render_template("login.html", error=error, email=email, next_url=next_url), (
        401 if error else 200
    )


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
