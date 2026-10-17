"""
Central configuration for the Nocturna UTG chatbot.

Secrets are read from environment variables rather than hard-coded, so the
project can be committed to version control (e.g. for your dissertation
appendix / GitHub repo) without leaking a live API key.

Before running, set:
    export OPENWEATHER_API_KEY="your_key_here"      # macOS/Linux
    setx OPENWEATHER_API_KEY "your_key_here"         # Windows

For anything beyond local testing also set SECRET_KEY (signs the login
session cookie) and, when serving over HTTPS, COOKIE_SECURE=1.

Or create a .env file and load it with python-dotenv if you prefer.
"""

import os

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

ASSISTANT_NAME = "Nocturna"
WAKE_GREETING = (
    "Hello, I'm Nocturna, your UTG student assistant. How can I help you today?"
)

# Which retrieval method the LIVE chatbot (chatbot.py / app.py)
# uses: "keyword", "tfidf", or "embeddings". See retrieval_methods.py for
# what each one does. Run `python evaluate.py` first and set this to
# whichever one actually scored best on eval/test_set.json -- don't just
# assume the fanciest method wins; that's the whole point of evaluating.
RETRIEVAL_METHOD = "tfidf"

# Minimum similarity score (0-1) required before each method will answer a
# question rather than saying it doesn't know. Each method's scores aren't
# on a comparable scale (keyword overlap vs TF-IDF cosine vs embedding
# cosine behave differently), so each gets its own threshold rather than
# sharing one number.
#
# These starting values came from a small manual test (a handful of
# in-scope vs clearly-out-of-scope queries) -- NOT a proper validation set.
# `python evaluate.py` reports accuracy at these thresholds on your real
# test set; re-tune here based on those results and report the false
# accept/false reject trade-off in your results chapter.
RETRIEVAL_THRESHOLDS = {
    "keyword": 0.34,
    "tfidf": 0.45,
    "embeddings": 0.5,
}

# Words the TF-IDF method ignores on top of ordinary English stop words.
# "utg" appears in most questions students ask, so it tells the matcher
# nothing about WHICH entry is meant, yet it made unrelated questions
# ("is there a football team at utg") look similar to short entries that
# also contain it. Ignoring it kept accuracy steady as the knowledge base
# grew from 20 to 46 entries. Set to () to get the original behaviour back
# (the numbers for both are in the README).
TFIDF_EXTRA_STOPWORDS = ("utg",)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(_BASE_DIR, "instance")  # holds the database + generated secret
DB_PATH = os.path.join(INSTANCE_DIR, "nocturna.db")
LOG_PATH = os.path.join(_BASE_DIR, "logs", "chat_interactions.csv")
KB_PATH = os.path.join(_BASE_DIR, "utg_knowledge.json")

# ---------------------------------------------------------------- accounts
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
SESSION_DAYS = 7
# Set COOKIE_SECURE=1 once the site is served over HTTPS so the session
# cookie is never sent over plain HTTP.
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"


def _load_secret_key() -> str:
    """Use SECRET_KEY from the environment if set; otherwise generate one
    once and keep it in instance/secret_key so logins survive a restart
    during development. Never commit the instance/ folder."""
    from_env = os.environ.get("SECRET_KEY")
    if from_env:
        return from_env
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    path = os.path.join(INSTANCE_DIR, "secret_key")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    import secrets

    key = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        f.write(key)
    return key


SECRET_KEY = _load_secret_key()

# ------------------------------------------------------------------------ UTG email
# Only University of The Gambia student emails may sign up or log in. The
# address is built from the student's name and student number:
#     first letter of first name + first letter of second name + student number
#     + @utg.edu.gm            e.g.  Awa Jallow, 2211234  ->  aj2211234@utg.edu.gm
UTG_EMAIL_DOMAIN = "utg.edu.gm"
STUDENT_NUMBER_MIN_DIGITS = 4
STUDENT_NUMBER_MAX_DIGITS = 10
