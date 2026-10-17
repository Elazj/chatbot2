"""
End-to-end tests for the login system and the chat API.

Run from the project folder with:
    python -m unittest discover -s tests -v

Each run uses a throwaway database and log file in a temp folder, so your
real accounts in instance/nocturna.db are never touched.
"""

import os
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pyjokes is only used for the joke command; stub it if it isn't installed so
# the rest of the suite can still run.
try:
    import pyjokes  # noqa: F401
except ModuleNotFoundError:
    stub = types.ModuleType("pyjokes")
    stub.get_joke = lambda: "A test joke."
    sys.modules["pyjokes"] = stub

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="nocturna_test_")
config.DB_PATH = os.path.join(_TMP, "test.db")
config.LOG_PATH = os.path.join(_TMP, "log.csv")

import app as app_module  # noqa: E402
import db  # noqa: E402
import logger  # noqa: E402

logger.LOG_PATH = config.LOG_PATH
db.DB_PATH = config.DB_PATH
db.init_db()

CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
META_RE = re.compile(r'name="csrf-token" content="([^"]+)"')


class Client:
    """A browser-like wrapper: keeps cookies and handles CSRF tokens."""

    def __init__(self):
        self.c = app_module.app.test_client()

    def form_token(self, path):
        html = self.c.get(path).get_data(as_text=True)
        return CSRF_RE.search(html).group(1)

    def signup(self, name="Awa Jallow", email="aj2211001@utg.edu.gm", pw="correct horse", confirm=None):
        token = self.form_token("/signup")
        return self.c.post("/signup", data={
            "csrf_token": token, "full_name": name, "email": email,
            "password": pw, "confirm": pw if confirm is None else confirm,
        })

    def login(self, email="aj2211001@utg.edu.gm", pw="correct horse", next_url=None):
        token = self.form_token("/login")
        data = {"csrf_token": token, "email": email, "password": pw}
        if next_url:
            data["next"] = next_url
        return self.c.post("/login", data=data)

    def api_token(self):
        html = self.c.get("/").get_data(as_text=True)
        return META_RE.search(html).group(1)

    def chat(self, text):
        r = self.c.post("/api/chat", json={"text": text}, headers={"X-CSRF-Token": self.api_token()})
        return r.status_code, r.get_json()


class AuthTests(unittest.TestCase):
    def test_protected_pages_require_login(self):
        c = Client()
        r = c.c.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        self.assertEqual(c.c.get("/api/history").status_code, 401)
        r = c.c.post("/api/chat", json={"text": "hi"})
        self.assertIn(r.status_code, (400, 401))

    def test_signup_requires_csrf(self):
        c = Client()
        r = c.c.post("/signup", data={"full_name": "X Y", "email": "xy2211002@utg.edu.gm", "password": "password1", "confirm": "password1"})
        self.assertEqual(r.status_code, 400)

    # ------------------------------------------------------------ UTG email rule
    def test_utg_email_accepted_and_case_insensitive(self):
        c = Client()
        self.assertEqual(c.signup(name="Ebrima Jallow", email="EJ2212345@UTG.EDU.GM").status_code, 302)
        self.assertEqual(db.get_user_by_email("ej2212345@utg.edu.gm")["full_name"], "Ebrima Jallow")

    def test_non_utg_emails_are_rejected_at_signup(self):
        for bad in ("awa@example.com", "aj2211234@gmail.com", "aj2211234@utg.edu.gm.evil.com", "aj2211234@student.utg.edu.gm",
                    "a2211234@utg.edu.gm",          # only one initial
                    "aj123@utg.edu.gm",             # student number too short
                    "aj@utg.edu.gm",                # no student number
                    "2211234aj@utg.edu.gm",         # wrong order
                    "ajx2211234@utg.edu.gm",        # three letters
                    "aj22112x4@utg.edu.gm"):        # letter inside the number
            r = Client().signup(email=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("UTG student email", r.get_data(as_text=True), bad)

    def test_initials_must_match_the_name(self):
        r = Client().signup(name="Awa Jallow", email="fs2211234@utg.edu.gm")
        self.assertEqual(r.status_code, 400)
        self.assertIn("must be the first letters", r.get_data(as_text=True))
        self.assertEqual(Client().signup(name="Fatou Sanneh", email="fs2211235@utg.edu.gm").status_code, 302)

    def test_three_part_names_may_use_second_or_last_name(self):
        self.assertEqual(Client().signup(name="Awa Fatou Jallow", email="aj2211236@utg.edu.gm").status_code, 302)   # last name
        self.assertEqual(Client().signup(name="Awa Fatou Jallow", email="af2211237@utg.edu.gm").status_code, 302)   # second name
        self.assertEqual(Client().signup(name="Awa Fatou Jallow", email="ax2211238@utg.edu.gm").status_code, 400)

    def test_single_name_is_rejected(self):
        r = Client().signup(name="Awa", email="aa2211239@utg.edu.gm")
        self.assertEqual(r.status_code, 400)
        self.assertIn("first name and second name", r.get_data(as_text=True))

    def test_accents_are_ignored_when_checking_initials(self):
        self.assertEqual(Client().signup(name="Émilie Ndow", email="en2211240@utg.edu.gm").status_code, 302)

    def test_login_requires_a_utg_email_even_for_an_existing_account(self):
        # an account made before the rule existed, with a non-UTG address
        from werkzeug.security import generate_password_hash
        db.create_user("Old Student", "old.student@gmail.com", generate_password_hash("correct horse"))
        r = Client().login("old.student@gmail.com")
        self.assertEqual(r.status_code, 401)
        self.assertIn("UTG student email", r.get_data(as_text=True))

    def test_login_with_utg_email_works(self):
        Client().signup(name="Lamin Ceesay", email="lc2211241@utg.edu.gm")
        r = Client().login("lc2211241@utg.edu.gm")
        self.assertEqual(r.status_code, 302)

    def test_forms_show_the_utg_email_hint(self):
        c = Client()
        for path in ("/signup", "/login"):
            html = c.c.get(path).get_data(as_text=True)
            self.assertIn("UTG student email", html)
            self.assertIn("aj2211234@utg.edu.gm", html)

    def test_signup_validation(self):
        c = Client()
        r = c.signup(email="not-an-email")
        self.assertEqual(r.status_code, 400)
        self.assertIn("UTG student email", r.get_data(as_text=True))
        r = c.signup(email="aj2211003@utg.edu.gm", pw="short")
        self.assertIn("at least 8", r.get_data(as_text=True))
        r = c.signup(email="aj2211004@utg.edu.gm", pw="longenough1", confirm="different1")
        self.assertIn("don&#39;t match", r.get_data(as_text=True))
        r = c.signup(name="A", email="aj2211005@utg.edu.gm")
        self.assertIn("first name and second name", r.get_data(as_text=True))

    def test_signup_login_logout_cycle(self):
        c = Client()
        r = c.signup(name="Lamin Ceesay", email="lc2211006@utg.edu.gm")
        self.assertEqual(r.status_code, 302)
        page = c.c.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Hello Lamin", c.c.get("/api/history").get_json()["messages"][0]["content"])   # greeted by first name

        # password is stored hashed, never as typed
        stored = db.get_user_by_email("lc2211006@utg.edu.gm")["password_hash"]
        self.assertNotIn("correct horse", stored)

        token = c.api_token()
        r = c.c.post("/logout", data={"csrf_token": token})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.c.get("/").status_code, 302)

        r = c.login("lc2211006@utg.edu.gm", "wrong password")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Incorrect email or password", r.get_data(as_text=True))
        r = c.login("lc2211006@utg.edu.gm")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.c.get("/").status_code, 200)

    def test_duplicate_email_case_insensitive(self):
        Client().signup(email="aj2211007@utg.edu.gm")
        r = Client().signup(email="AJ2211007@UTG.edu.gm")
        self.assertEqual(r.status_code, 400)
        self.assertIn("already exists", r.get_data(as_text=True))

    def test_unknown_email_gives_same_message(self):
        r = Client().login("nb2211008@utg.edu.gm", "whatever123")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Incorrect email or password", r.get_data(as_text=True))

    def test_open_redirect_blocked(self):
        Client().signup(email="aj2211009@utg.edu.gm")
        c = Client()
        r = c.login("aj2211009@utg.edu.gm", next_url="//evil.example")
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("evil", r.headers["Location"])

    def test_login_throttle(self):
        Client().signup(email="aj2211010@utg.edu.gm")
        c = Client()
        for _ in range(5):
            c.login("aj2211010@utg.edu.gm", "badbadbad1")
        r = c.login("aj2211010@utg.edu.gm", "correct horse")  # right password, still locked
        self.assertEqual(r.status_code, 401)
        self.assertIn("Too many failed attempts", r.get_data(as_text=True))


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.c = Client()
        email = f"fs{2300000 + (id(self) % 1000000)}@utg.edu.gm"
        self.c.signup(name="Fatou Sanneh", email=email)
        self.email = email

    def test_history_starts_with_personal_greeting(self):
        r = self.c.c.get("/api/history").get_json()
        self.assertEqual(len(r["messages"]), 1)
        self.assertIn("Hello Fatou", r["messages"][0]["content"])

    def test_csrf_header_required_for_chat(self):
        r = self.c.c.post("/api/chat", json={"text": "help"})
        self.assertEqual(r.status_code, 400)

    def test_knowledge_base_and_catalog_answers(self):
        _, data = self.c.chat("what schools and faculties does utg have")
        self.assertIn("nine schools", data["replies"][0])
        _, data = self.c.chat("what is the prerequisite for CPS 402")
        self.assertIn("prerequisite", data["replies"][0].lower())

    def test_unmatched_and_empty(self):
        _, data = self.c.chat("zxqv blorf wibble")
        self.assertIn("still learning", data["replies"][0])
        status, _ = self.c.chat("   ")
        self.assertEqual(status, 400)
        status, _ = self.c.chat("x" * 600)
        self.assertEqual(status, 400)

    def test_greeting_help_and_time(self):
        _, data = self.c.chat("hello")
        self.assertIn("Fatou", data["replies"][0])
        _, data = self.c.chat("help")
        self.assertIn("admissions", data["replies"][0])
        _, data = self.c.chat("what time is it")
        self.assertIn("GMT", data["replies"][0])

    def test_weather_follow_up_and_cancel(self):
        _, data = self.c.chat("weather")
        self.assertIn("Which city", data["replies"][0])
        _, data = self.c.chat("cancel")
        self.assertEqual(data["replies"][0], "Okay, cancelled.")
        # after cancelling, a normal question is answered normally again
        _, data = self.c.chat("what schools and faculties does utg have")
        self.assertIn("nine schools", data["replies"][0])

    def test_search_returns_link(self):
        _, data = self.c.chat("search for utg admissions")
        self.assertIn("https://www.google.com/search?q=utg%20admissions", data["replies"][0])

    def test_notes(self):
        _, data = self.c.chat("note: Bring my ID to registration")
        self.assertIn("saved", data["replies"][0])
        _, data = self.c.chat("take a note")
        self.assertIn("What would you like", data["replies"][0])
        _, data = self.c.chat("Buy a calculator")
        self.assertIn("saved", data["replies"][0])
        _, data = self.c.chat("my notes")
        self.assertIn("Bring my ID to registration", data["replies"][0])  # case kept
        self.assertIn("Buy a calculator", data["replies"][0])

    def test_reminders_one_line_and_step_by_step(self):
        _, data = self.c.chat("remind me to pay fees in 3 days")
        self.assertIn("pay fees", data["replies"][0])
        _, data = self.c.chat("remind me to submit my assignment")
        self.assertIn("When should I remind you", data["replies"][0])
        _, data = self.c.chat("sometime soon")
        self.assertIn("couldn't understand that date", data["replies"][0])
        _, data = self.c.chat("tomorrow")
        self.assertIn("submit my assignment", data["replies"][0])
        _, data = self.c.chat("my reminders")
        self.assertIn("pay fees", data["replies"][0])
        self.assertIn("submit my assignment", data["replies"][0])

    def test_due_reminder_shown_once(self):
        self.c.chat("remind me to renew my ID today")
        first = self.c.c.get("/api/due_reminders").get_json()["due"]
        self.assertEqual(len(first), 1)
        self.assertIn("renew my ID", first[0])
        second = self.c.c.get("/api/due_reminders").get_json()["due"]
        self.assertEqual(second, [])

    def test_clear_chat_keeps_notes(self):
        self.c.chat("note: keep me")
        r = self.c.c.post("/api/clear", json={}, headers={"X-CSRF-Token": self.c.api_token()})
        self.assertEqual(r.status_code, 200)
        msgs = self.c.c.get("/api/history").get_json()["messages"]
        self.assertEqual(len(msgs), 1)  # fresh greeting only
        _, data = self.c.chat("my notes")
        self.assertIn("keep me", data["replies"][0])

    def test_users_cannot_see_each_others_data(self):
        self.c.chat("note: private to fatou")
        self.c.chat("remind me to do secret thing tomorrow")
        other = Client()
        other.signup(name="Omar Bah", email=f"ob{2400000 + (id(self) % 1000000)}@utg.edu.gm")
        _, data = other.chat("my notes")
        self.assertNotIn("private to fatou", data["replies"][0])
        _, data = other.chat("my reminders")
        self.assertNotIn("secret thing", data["replies"][0])
        history = " ".join(m["content"] for m in other.c.get("/api/history").get_json()["messages"])
        self.assertNotIn("private to fatou", history)


class WeatherTests(unittest.TestCase):
    """The weather call is mocked: no internet or real API key is needed."""

    def _reply(self, key, payload, city="Banjul"):
        import utilities
        fake = mock.Mock()
        fake.json.return_value = payload
        with mock.patch.object(utilities, "OPENWEATHER_API_KEY", key), \
                mock.patch.object(utilities.requests, "get", return_value=fake):
            return utilities.get_weather(city)

    def test_no_key_explains_how_to_fix(self):
        self.assertIn("OPENWEATHER_API_KEY", self._reply("", {}))

    def test_success(self):
        out = self._reply("k", {"cod": 200, "weather": [{"description": "clear sky"}], "main": {"temp": 31.2}})
        self.assertIn("clear sky", out)
        self.assertIn("31.2", out)

    def test_bad_or_inactive_key(self):
        self.assertIn("didn't accept the API key", self._reply("k", {"cod": 401}))

    def test_unknown_city(self):
        self.assertIn("couldn't find the weather for Atlantis", self._reply("k", {"cod": "404"}, "Atlantis"))


class ThemeTests(unittest.TestCase):
    def test_every_page_loads_theme_script_and_has_a_toggle(self):
        c = Client()
        for path in ("/login", "/signup"):
            html = c.c.get(path).get_data(as_text=True)
            self.assertIn("theme.js", html)
            self.assertIn('id="theme-toggle"', html)
        c.signup(email="aj2211011@utg.edu.gm")
        html = c.c.get("/").get_data(as_text=True)
        self.assertIn("theme.js", html)
        self.assertNotIn('id="theme-toggle"', html)  # the chat screen picks its theme in Settings > General

    def test_theme_assets_are_served(self):
        c = Client()
        self.assertEqual(c.c.get("/static/theme.js").status_code, 200)
        css = c.c.get("/static/style.css").get_data(as_text=True)
        self.assertIn('[data-theme="light"]', css)


if __name__ == "__main__":
    unittest.main()
