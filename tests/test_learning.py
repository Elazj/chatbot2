"""
Tests for the chat-centred learning platform: conversations, documents,
notes, quizzes, flashcards, study plans, progress, past exams, search, code
help, settings, privacy controls -- and, most importantly, that one student
can never read or change another student's data.

Run with:  python -m unittest discover -s tests -v
"""

import datetime
import io
import json
import unittest

import test_app                      # sets up the temporary database
from test_app import Client, META_RE

from learning import ingest

ingest.SYNC = True                   # finish document processing before each request returns

DBS = b"""# Database Systems II

## Normalization

Normalization is the process of organizing data in a database to reduce redundancy and improve integrity. A functional dependency is a relationship between two attributes where one determines the other. First normal form requires that every column holds only atomic values. Second normal form removes partial dependencies on a composite primary key. Third normal form removes transitive dependencies between non-key attributes. A foreign key is a column that references the primary key of another table.

## Transactions

A transaction is a sequence of operations performed as a single logical unit of work. Atomicity means that either all operations of a transaction happen or none of them do. Isolation ensures that concurrent transactions do not interfere with each other. Durability guarantees that committed changes survive a system failure. A deadlock occurs when two transactions each wait for a lock held by the other. A schedule is serializable if it is equivalent to some serial execution of the transactions.
"""

PAPER1 = b"""DATABASE SYSTEMS II EXAMINATION
1. Define normalization and explain third normal form. (5 marks)
2. Describe the ACID properties of a transaction. (8 marks)
3. Write an SQL query to list all students. (4 marks)
4. Discuss concurrency control and deadlock in transactions. (10 marks)
"""
PAPER2 = b"""DATABASE SYSTEMS II RESIT EXAMINATION
1. Explain normalization and describe second normal form. (6 marks)
2. Define a transaction and state the ACID properties. (6 marks)
3. What is a foreign key? (3 marks)
4. Discuss deadlock handling in transactions. (10 marks)
"""

_counter = [0]


class Api(Client):
    """Client with JSON helpers that handle the CSRF token."""

    def __init__(self, name="Awa Jallow"):
        super().__init__()
        _counter[0] += 1
        initials = "".join(w[0].lower() for w in name.split()[:2])
        self.email = f"{initials}{2500000 + _counter[0]}@utg.edu.gm"
        self.signup(name=name, email=self.email)
        self.token = META_RE.search(self.c.get("/").get_data(as_text=True)).group(1)

    def h(self):
        return {"X-CSRF-Token": self.token}

    def get(self, path):
        r = self.c.get(path)
        return r.status_code, (r.get_json(silent=True) or {})

    def post(self, path, data=None):
        r = self.c.post(path, json=data if data is not None else {}, headers=self.h())
        return r.status_code, (r.get_json(silent=True) or {})

    def delete(self, path):
        r = self.c.delete(path, headers=self.h())
        return r.status_code, (r.get_json(silent=True) or {})

    def upload(self, name, data, kind="material", course_id=None):
        form = {"file": (io.BytesIO(data), name), "kind": kind}
        if course_id:
            form["course_id"] = str(course_id)
        r = self.c.post("/api/documents", data=form, headers=self.h(), content_type="multipart/form-data")
        return r.status_code, (r.get_json(silent=True) or {})

    def doc(self, name="dbs.md", data=DBS, **kw):
        status, body = self.upload(name, data, **kw)
        assert status == 202, body
        return body["document"]["id"]


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.a = Api()

    def test_new_account_has_one_greeted_conversation(self):
        _, d = self.a.get("/api/history")
        self.assertEqual(len(d["messages"]), 1)
        self.assertIn("Hello Awa", d["messages"][0]["content"])

    def test_new_chat_list_rename_search_delete(self):
        _, d = self.a.post("/api/conversations")
        cid = d["conversation"]["id"]
        self.a.post("/api/chat", {"text": "What is ECOMANSA?", "conversation_id": cid})
        _, conv = self.a.get(f"/api/conversations/{cid}")
        self.assertTrue(conv["conversation"]["title"].startswith("What is ECOMANSA"))
        _, lst = self.a.get("/api/conversations")
        self.assertEqual(lst["groups"][0]["label"], "Today")
        _, found = self.a.get("/api/conversations?q=ECOMANSA")
        self.assertTrue(any(i["id"] == cid for g in found["groups"] for i in g["items"]))
        _, none = self.a.get("/api/conversations?q=zzzznotthere")
        self.assertEqual(none["groups"], [])
        self.assertEqual(self.a.post(f"/api/conversations/{cid}/rename", {"title": "Associations"})[0], 200)
        self.assertEqual(self.a.post(f"/api/conversations/{cid}/rename", {"title": "  "})[0], 400)
        self.assertEqual(self.a.delete(f"/api/conversations/{cid}")[0], 200)
        self.assertEqual(self.a.get(f"/api/conversations/{cid}")[0], 404)

    def test_other_students_conversation_is_404(self):
        _, d = self.a.post("/api/conversations")
        cid = d["conversation"]["id"]
        b = Api("Omar Bah")
        self.assertEqual(b.get(f"/api/conversations/{cid}")[0], 404)
        self.assertEqual(b.post(f"/api/conversations/{cid}/rename", {"title": "x"})[0], 404)
        self.assertEqual(b.delete(f"/api/conversations/{cid}")[0], 404)
        self.assertEqual(b.post("/api/chat", {"text": "hi", "conversation_id": cid})[0], 404)
        self.assertEqual(self.a.get(f"/api/conversations/{cid}")[0], 200)

    def test_feedback_and_regenerate(self):
        _, d = self.a.post("/api/chat", {"text": "What is EDUSA?"})
        mid = d["message_ids"][0]
        self.assertEqual(self.a.post(f"/api/messages/{mid}/feedback", {"value": 1})[0], 200)
        _, h = self.a.get("/api/history")
        self.assertEqual([m["feedback"] for m in h["messages"] if m["id"] == mid], [1])
        self.assertEqual(self.a.post(f"/api/messages/{mid}/feedback", {"value": 7})[0], 400)
        self.assertEqual(Api("Omar Bah").post(f"/api/messages/{mid}/feedback", {"value": 1})[0], 404)
        status, r = self.a.post("/api/chat/regenerate", {})
        self.assertEqual(status, 200)
        self.assertIn("EDUSA", r["replies"][0])
        _, h = self.a.get("/api/history")
        self.assertEqual(sum(1 for m in h["messages"] if m["role"] == "user"), 1)   # no duplicate user message

    def test_clear_history_keeps_everything_else(self):
        did = self.a.doc()
        self.a.post("/api/notes", {"content": "keep this note"})
        self.a.post("/api/flashcards", {"front": "Q", "back": "A"})
        self.a.post("/api/chat", {"text": "hello"})
        status, d = self.a.post("/api/history/clear")
        self.assertEqual(status, 200)
        self.assertEqual(len(d["messages"]), 1)
        _, convs = self.a.get("/api/conversations")
        self.assertEqual(sum(len(g["items"]) for g in convs["groups"]), 1)
        self.assertEqual(len(self.a.get("/api/documents")[1]["documents"]), 1)
        self.assertEqual(len(self.a.get("/api/notes")[1]["notes"]), 1)
        self.assertEqual(len(self.a.get("/api/flashcards")[1]["cards"]), 1)
        self.assertEqual(self.a.get(f"/api/documents/{did}")[0], 200)

    def test_pending_question_belongs_to_one_conversation(self):
        _, d1 = self.a.post("/api/chat", {"text": "weather"})
        self.assertIn("Which city", d1["replies"][0])
        _, d2 = self.a.post("/api/conversations")
        _, r = self.a.post("/api/chat", {"text": "What is EDUSA?", "conversation_id": d2["conversation"]["id"]})
        self.assertIn("EDUSA", r["replies"][0])     # not swallowed as the "city"

    def test_settings_and_profile(self):
        _, s = self.a.post("/api/settings", {"rag_strictness": "strict", "voice_output": True, "bogus": "x", "study_goals": "Pass DBS II"})
        self.assertEqual(s["settings"]["rag_strictness"], "strict")
        self.assertTrue(s["settings"]["voice_output"])
        self.assertNotIn("bogus", s["settings"])
        self.assertNotIn("explain_mode", s["settings"])          # AI explanation modes were removed
        self.a.post("/api/settings", {"rag_strictness": "not-a-level"})
        self.assertEqual(self.a.get("/api/settings")[1]["settings"]["rag_strictness"], "strict")
        _, p = self.a.post("/api/profile", {"full_name": "Awa B. Jallow", "learning_style": "visual"})
        self.assertEqual(p["profile"]["full_name"], "Awa B. Jallow")
        self.assertEqual(p["profile"]["study_goals"], "Pass DBS II")
        self.assertEqual(self.a.post("/api/profile", {"full_name": "A"})[0], 400)

    def test_change_password(self):
        self.assertEqual(self.a.post("/api/profile/password", {"current": "wrong", "new": "brandnewpass1"})[0], 403)
        self.assertEqual(self.a.post("/api/profile/password", {"current": "correct horse", "new": "short"})[0], 400)
        self.assertEqual(self.a.post("/api/profile/password", {"current": "correct horse", "new": "brandnewpass1"})[0], 200)
        self.a.c.post("/logout", data={"csrf_token": self.a.token})
        self.assertEqual(Client.login(self.a, self.a.email, "brandnewpass1").status_code, 302)

    def test_reminder_popups_setting(self):
        self.a.post("/api/chat", {"text": "remind me to renew my ID today"})
        self.a.post("/api/settings", {"reminder_popups": False})
        self.assertEqual(self.a.get("/api/due_reminders")[1]["due"], [])
        self.a.post("/api/settings", {"reminder_popups": True})
        self.assertEqual(len(self.a.get("/api/due_reminders")[1]["due"]), 1)


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.a = Api()
        self.did = self.a.doc()

    def test_upload_status_and_listing(self):
        _, d = self.a.get(f"/api/documents/{self.did}")
        self.assertEqual(d["document"]["status"], "ready")
        self.assertEqual(d["document"]["stage"], "Ready")
        self.assertEqual([s["section"] for s in d["sections"]], ["Normalization", "Transactions"])
        self.assertEqual(len(self.a.get("/api/documents")[1]["documents"]), 1)
        _, t = self.a.get(f"/api/documents/{self.did}/text")
        self.assertGreaterEqual(len(t["chunks"]), 2)

    def test_upload_refusals(self):
        self.assertEqual(self.a.upload("virus.exe", b"MZ")[0], 400)
        self.assertEqual(self.a.upload("empty.txt", b"")[0], 400)
        self.assertEqual(self.a.c.post("/api/documents", data={}, headers=self.a.h(), content_type="multipart/form-data").status_code, 400)
        status, body = self.a.upload("broken.pdf", b"not really a pdf")
        _, doc = self.a.get(f"/api/documents/{body['document']['id']}")
        self.assertEqual(doc["document"]["status"], "failed")
        self.assertIn("couldn't read", doc["document"]["error"])
        self.assertEqual(self.a.upload("x.txt", b"hello", course_id=99999)[0], 404)

    def test_chat_with_document_cites_sources(self):
        self.a.post(f"/api/conversations/{self.a.post('/api/conversations')[1]['conversation']['id']}/context", {"document_id": self.did})
        _, r = self.a.post("/api/chat", {"text": "What is third normal form?"})
        self.assertEqual(r["intent"], "document_answer")
        self.assertEqual(r["sources"][0]["filename"], "dbs.md")
        self.assertEqual(r["sources"][0]["section"], "Normalization")
        _, miss = self.a.post("/api/chat", {"text": "Who won the 2010 world cup?"})
        self.assertEqual(miss["intent"], "document_miss")
        self.assertIn("couldn't find that", miss["replies"][0])

    def test_general_chat_falls_back_to_my_documents(self):
        _, r = self.a.post("/api/chat", {"text": "what is a deadlock"})
        self.assertEqual(r["intent"], "document_answer")
        self.assertIn("dbs.md", r["sources"][0]["filename"])

    def test_summaries(self):
        for mode in ("quick", "detailed", "chapter", "exam"):
            status, s = self.a.post(f"/api/documents/{self.did}/summary", {"mode": mode})
            self.assertEqual(status, 200, mode)
            self.assertIn("summary", s["markdown"].lower())
        self.assertEqual(self.a.post(f"/api/documents/{self.did}/summary", {"mode": "weird"})[0], 400)
        _, ex = self.a.post(f"/api/documents/{self.did}/summary", {"mode": "exam"})
        self.assertIn("not a forecast", ex["markdown"])

    def test_document_to_notes_and_delete(self):
        _, n = self.a.post(f"/api/documents/{self.did}/notes")
        self.assertIn("dbs.md", n["note"]["title"])
        self.assertEqual(self.a.delete(f"/api/documents/{self.did}")[0], 200)
        self.assertEqual(self.a.get(f"/api/documents/{self.did}")[0], 404)
        self.assertEqual(self.a.post("/api/chat", {"text": "what is a deadlock"})[1]["intent"], "unmatched")

    def test_courses_and_assignment(self):
        _, c = self.a.post("/api/courses", {"name": "Database Systems II"})
        cid = c["course"]["id"]
        self.assertEqual(self.a.post("/api/courses", {"name": "database systems ii"})[0], 400)
        self.assertEqual(self.a.post(f"/api/documents/{self.did}/course", {"course_id": cid})[0], 200)
        self.assertEqual(len(self.a.get(f"/api/documents?course_id={cid}")[1]["documents"]), 1)
        self.assertEqual(self.a.get("/api/courses")[1]["courses"][0]["documents"], 1)
        self.assertEqual(self.a.post(f"/api/courses/{cid}/rename", {"name": "DBS II"})[0], 200)
        self.assertEqual(self.a.delete(f"/api/courses/{cid}")[0], 200)
        self.assertIsNone(self.a.get("/api/documents")[1]["documents"][0]["course_id"])


class SettingsTests(unittest.TestCase):
    """Settings > General, Documents / RAG and User Profile / Account."""

    def setUp(self):
        self.a = Api()
        self.did = self.a.doc()

    def test_defaults(self):
        st = self.a.get("/api/settings")[1]["settings"]
        self.assertTrue(st["show_timestamps"])
        self.assertEqual((st["rag_passages"], st["rag_strictness"], st["rag_fallback"], st["show_sources"]), (3, "balanced", True, True))

    def test_general_timestamps_toggle_and_validation(self):
        self.assertFalse(self.a.post("/api/settings", {"show_timestamps": False})[1]["settings"]["show_timestamps"])
        self.assertTrue(self.a.post("/api/settings", {"show_timestamps": True})[1]["settings"]["show_timestamps"])
        # passages is clamped to 1..5; garbage is ignored
        self.assertEqual(self.a.post("/api/settings", {"rag_passages": 99})[1]["settings"]["rag_passages"], 5)
        self.assertEqual(self.a.post("/api/settings", {"rag_passages": 0})[1]["settings"]["rag_passages"], 1)
        self.assertEqual(self.a.post("/api/settings", {"rag_passages": "abc"})[1]["settings"]["rag_passages"], 1)

    def test_rag_passage_count_changes_the_answer(self):
        self.a.post("/api/settings", {"rag_passages": 1, "rag_strictness": "relaxed"})
        _, one = self.a.post("/api/chat", {"text": "what is a deadlock"})
        self.a.post("/api/settings", {"rag_passages": 5, "rag_strictness": "relaxed"})
        _, many = self.a.post("/api/chat", {"text": "what is a deadlock"})
        self.assertEqual(one["intent"], "document_answer")
        self.assertLessEqual(len(one["sources"]), 1)
        self.assertGreaterEqual(len(many["sources"]), len(one["sources"]))

    def test_rag_fallback_off_keeps_documents_out_of_general_chat(self):
        self.a.post("/api/settings", {"rag_fallback": False})
        _, r = self.a.post("/api/chat", {"text": "what is a deadlock"})
        self.assertNotEqual(r["intent"], "document_answer")

    def test_document_answers_are_quoted_not_generated(self):
        _, r = self.a.post("/api/chat", {"text": "what is a deadlock"})
        self.assertIn("quoted directly", r["replies"][0])
        self.assertNotIn("AI model", r["replies"][0].replace("does not use an AI model", ""))

    def test_clear_history_and_delete_all_documents(self):
        self.a.post("/api/chat", {"text": "hello"})
        self.assertEqual(self.a.post("/api/history/clear")[0], 200)
        self.assertEqual(self.a.post("/api/data/delete", {"what": "documents"})[0], 400)         # needs the DELETE confirmation
        self.assertEqual(self.a.post("/api/data/delete", {"what": "documents", "confirm": "DELETE"})[0], 200)
        self.assertEqual(self.a.get("/api/documents")[1]["documents"], [])

    def test_delete_account_needs_password(self):
        self.assertEqual(self.a.post("/api/data/delete", {"what": "account", "confirm": "DELETE", "password": "wrong"})[0], 403)
        self.assertEqual(self.a.post("/api/data/delete", {"what": "account", "confirm": "DELETE", "password": "correct horse"})[0], 200)
        self.assertEqual(self.a.get("/api/profile")[0], 401)


class FrontEndRequirementTests(unittest.TestCase):
    """Static checks on the browser code for the final-year requirements."""

    def setUp(self):
        import pathlib
        self.root = pathlib.Path(__file__).resolve().parent.parent
        self.read = lambda p: (self.root / p).read_text(encoding="utf-8")

    def test_no_llm_anywhere(self):
        self.assertFalse((self.root / "learning" / "llm.py").exists())
        for p in self.root.rglob("*.py"):
            if "tests" in p.parts or "venv" in p.parts:
                continue
            text = p.read_text(encoding="utf-8").lower()
            for banned in ("import anthropic", "api.anthropic", "openai", "llm.generate", "llm.available"):
                self.assertNotIn(banned, text, f"{banned} found in {p.name}")

    def test_interface_never_says_ai(self):
        """Buttons and labels must not suggest an AI is involved (only statements that no AI is used)."""
        import re
        for p in ("static/app.js", "static/ui.js", "static/panels_a.js", "static/panels_b.js", "templates/chat.html"):
            for m in re.finditer(r'text: "([^"]*\bAI\b[^"]*)"', self.read(p)):
                self.assertRegex(m.group(1), r"(?i)\b(no|not|isn't|never|without)\b[^.]*\bAI\b|\bAI\b[^.]*\b(not|never)\b", m.group(1))

    def test_five_second_thinking_delay(self):
        js = self.read("static/app.js")
        self.assertIn("const THINKING_MS = 5000;", js)
        self.assertIn('text: "Thinking"', js)
        self.assertIn("withThinking(", js)

    def test_settings_has_exactly_the_three_tabs(self):
        js = self.read("static/panels_b.js")
        for label in ('"General"', '"Documents / RAG"', '"User Profile / Account"'):
            self.assertIn(label, js)
        for needed in ("Light", "Dark", "System", "Show timestamps", "Clear chat history", "Delete my account", "Download my data"):
            self.assertIn(needed, js)

    def test_theme_supports_system_mode(self):
        js = self.read("static/theme.js")
        self.assertIn("prefers-color-scheme: dark", js)
        self.assertIn('"system"', js)

    def test_no_emoji_in_interface_code(self):
        import re
        emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF\uFE0F]")
        for p in ("static/app.js", "static/ui.js", "static/panels_a.js", "static/panels_b.js", "templates/chat.html"):
            hits = sorted(set(emoji.findall(self.read(p))) - {"\u2713", "\u2717"})
            self.assertEqual(hits, [], f"emoji in {p}: {hits}")


class NotesFlashcardsQuizTests(unittest.TestCase):
    def setUp(self):
        self.a = Api()
        self.did = self.a.doc()

    def test_notes_crud_search_convert(self):
        _, n = self.a.post("/api/notes", {"title": "Keys", "content": "Primary key: a column that uniquely identifies each row.\nForeign key: a column that references a primary key."})
        nid = n["note"]["id"]
        self.assertEqual(self.a.post("/api/notes", {"content": "  "})[0], 400)
        self.assertEqual(len(self.a.get("/api/notes?q=uniquely")[1]["notes"]), 1)
        self.assertEqual(len(self.a.get("/api/notes?q=zzz")[1]["notes"]), 0)
        self.assertEqual(self.a.post(f"/api/notes/{nid}", {"content": "Updated body text"})[1]["note"]["content"], "Updated body text")
        self.a.post(f"/api/notes/{nid}", {"content": "Primary key: a column that uniquely identifies each row.\nForeign key: a column that references a primary key."})
        _, fc = self.a.post(f"/api/notes/{nid}/flashcards")
        self.assertEqual(fc["created"], 2)
        self.assertEqual(self.a.post(f"/api/notes/{nid}/improve")[0], 404)       # AI "improve" feature no longer exists
        self.assertEqual(self.a.delete(f"/api/notes/{nid}")[0], 200)
        self.assertEqual(self.a.get(f"/api/notes/{nid}")[0], 404)

    def test_note_to_quiz(self):
        text = "Normalization is the process of organizing data to reduce redundancy. A foreign key is a column that references the primary key of another table. A transaction is a sequence of operations performed as a single unit. Atomicity means that all operations happen or none do."
        nid = self.a.post("/api/notes", {"content": text})[1]["note"]["id"]
        status, q = self.a.post(f"/api/notes/{nid}/quiz", {"count": 4})
        self.assertEqual(status, 201)
        self.assertGreaterEqual(len(q["questions"]), 1)

    def test_quiz_generate_submit_and_progress(self):
        status, q = self.a.post("/api/quizzes/generate", {"source": {"type": "document", "id": self.did}, "count": 8, "difficulty": "medium", "types": ["mcq", "tf", "short"]})
        self.assertEqual(status, 201)
        self.assertGreaterEqual(len(q["questions"]), 4)
        self.assertNotIn("answer", q["questions"][0])                      # answers are not sent to the browser
        qid = q["quiz"]["id"]
        # answer everything wrongly on purpose
        wrong = {str(x["id"]): ("zzz" if x["qtype"] != "tf" else "Maybe") for x in q["questions"]}
        status, res = self.a.post(f"/api/quizzes/{qid}/submit", {"answers": wrong})
        self.assertEqual(status, 200)
        self.assertEqual(res["score"], 0)
        self.assertTrue(all("correct_answer" in r and "explanation" in r for r in res["results"]))
        self.assertTrue(res["weak"])
        self.assertTrue(res["recommendations"])
        _, prog = self.a.get("/api/progress")
        self.assertEqual(prog["progress"]["quizzes_taken"], 1)
        self.assertEqual(prog["progress"]["average_score"], 0)
        # a second wrong attempt makes the topics count as weak (needs >= 2 answers)
        self.a.post(f"/api/quizzes/{qid}/submit", {"answers": wrong})
        weak = self.a.get("/api/progress")[1]["progress"]["weak"]
        self.assertTrue(weak)
        # a quiz built from weak topics and one from past mistakes
        self.assertEqual(self.a.post("/api/quizzes/generate", {"source": {"type": "weak"}, "count": 4})[0], 201)
        self.assertEqual(self.a.post("/api/quizzes/generate", {"source": {"type": "mistakes"}, "count": 5})[0], 201)
        status, sim = self.a.post(f"/api/quizzes/{qid}/similar")
        self.assertEqual(status, 201)
        self.assertNotEqual(sim["quiz"]["id"], qid)
        self.assertGreaterEqual(len(self.a.get("/api/quizzes")[1]["quizzes"]), 3)

    def test_correct_answers_score_full_marks(self):
        _, q = self.a.post("/api/quizzes/generate", {"source": {"type": "document", "id": self.did}, "count": 6, "types": ["mcq", "tf"]})
        rows = {r["id"]: r["answer"] for r in test_app.db.fetchall("SELECT id, answer FROM quiz_questions WHERE quiz_id = ?", (q["quiz"]["id"],))}
        _, res = self.a.post(f"/api/quizzes/{q['quiz']['id']}/submit", {"answers": {str(i): a for i, a in rows.items()}})
        self.assertEqual(res["percent"], 100)

    def test_quiz_errors(self):
        self.assertEqual(self.a.post("/api/quizzes/generate", {"source": {"type": "topic", "topic": "quantum chromodynamics"}})[0], 400)
        self.assertEqual(self.a.post("/api/quizzes/generate", {"source": {"type": "weak"}})[0], 400)
        self.assertEqual(self.a.post("/api/quizzes/generate", {"source": {"type": "document", "id": 99999}})[0], 404)
        self.assertEqual(self.a.post("/api/quizzes/generate", {"source": {"type": "nonsense"}})[0], 400)

    def test_flashcards_generate_review_schedule(self):
        status, g = self.a.post("/api/flashcards/generate", {"source": {"type": "document", "id": self.did}, "count": 10})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(g["created"], 5)
        self.a.post("/api/flashcards/generate", {"source": {"type": "document", "id": self.did}, "count": 10})
        fronts = [c["front"].lower() for c in self.a.get("/api/flashcards")[1]["cards"]]
        self.assertEqual(len(fronts), len(set(fronts)))                    # never two cards with the same front
        _, due = self.a.get("/api/flashcards/due")
        card = due["cards"][0]
        _, r = self.a.post(f"/api/flashcards/{card['id']}/review", {"rating": 3})
        self.assertEqual(r["card"]["interval_days"], 1)
        self.assertGreater(r["card"]["due_date"], datetime.date.today().isoformat() if False else "2000-01-01")
        _, again = self.a.post(f"/api/flashcards/{card['id']}/review", {"rating": 1})
        self.assertEqual(again["card"]["interval_days"], 0)
        self.assertEqual(self.a.post(f"/api/flashcards/{card['id']}/review", {"rating": 9})[0], 400)
        self.assertEqual(self.a.get("/api/progress")[1]["progress"]["flashcards_reviewed"], 2)

    def test_study_plan_lifecycle(self):
        exam = (datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=9)).isoformat()
        status, p = self.a.post("/api/study-plans", {"exam_date": exam, "hours_per_day": 2, "level": "beginner", "struggling": ["Transactions"], "title": "DBS II"})
        self.assertEqual(status, 201)
        plan = p["plan"]
        labels = [t["label"] for d in plan["days"] for t in d["tasks"]]
        self.assertTrue(any("Normalization" in l for l in labels))
        self.assertEqual(plan["days"][-1]["tasks"][0]["label"], "Full mock exam")
        tid = plan["days"][0]["tasks"][0]["id"]
        _, t = self.a.post(f"/api/study-tasks/{tid}/toggle")
        self.assertTrue(t["done"])
        self.assertGreater(t["plan"]["completion"], 0)
        self.assertEqual(self.a.post(f"/api/study-plans/{plan['id']}/adapt")[0], 200)
        self.assertEqual(self.a.get("/api/study-plans")[1]["plans"][0]["title"], "DBS II")
        self.assertEqual(self.a.delete(f"/api/study-plans/{plan['id']}")[0], 200)

    def test_study_plan_validation(self):
        self.assertEqual(self.a.post("/api/study-plans", {"exam_date": "2001-01-01"})[0], 400)
        self.assertEqual(self.a.post("/api/study-plans", {"exam_date": "nonsense"})[0], 400)
        empty = Api("No Docs")
        exam = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
        status, e = empty.post("/api/study-plans", {"exam_date": exam})
        self.assertEqual(status, 400)
        self.assertIn("topics", e["error"])
        self.assertEqual(empty.post("/api/study-plans", {"exam_date": exam, "topics": ["Trees", "Graphs"]})[0], 201)


class PastExamTests(unittest.TestCase):
    def setUp(self):
        self.a = Api()
        self.a.doc()
        self.p1 = self.a.doc("paper1.txt", PAPER1, kind="past_exam")
        self.p2 = self.a.doc("paper2.txt", PAPER2, kind="past_exam")

    def test_analysis_wording_and_mock_exam(self):
        status, r = self.a.post("/api/past-exams/analyze", {"document_ids": [self.p1, self.p2]})
        self.assertEqual(status, 200)
        an = r["analysis"]
        self.assertEqual(an["question_count"], 8)
        self.assertTrue(any("normalization" in t["term"] for t in an["topics"]))
        self.assertIn("Frequently tested in the provided past papers", an["note"])
        self.assertNotIn("will appear", json.dumps(an).lower())
        status, m = self.a.post("/api/past-exams/mock", {"analysis_id": r["analysis_id"], "count": 6, "duration_min": 45})
        self.assertEqual(status, 201)
        self.assertEqual(m["quiz"]["kind"], "mock_exam")
        self.assertEqual(m["quiz"]["duration_min"], 45)
        open_ids = [q["id"] for q in m["questions"] if q["qtype"] == "open"]
        self.assertTrue(open_ids)
        status, res = self.a.post(f"/api/quizzes/{m['quiz']['id']}/submit", {"answers": {str(open_ids[0]): "my answer"}})
        self.assertEqual(res["waiting_for_self_mark"], len(open_ids))
        status, marked = self.a.post(f"/api/quiz-attempts/{res['attempt_id']}/selfmark", {"question_id": open_ids[0], "score": 1})
        self.assertEqual(status, 200)
        self.assertEqual(marked["waiting_for_self_mark"], len(open_ids) - 1)
        self.assertEqual(self.a.post(f"/api/quiz-attempts/{res['attempt_id']}/selfmark", {"question_id": open_ids[0], "score": 7})[0], 400)

    def test_analyze_errors(self):
        self.assertEqual(self.a.post("/api/past-exams/analyze", {"document_ids": []})[0], 400)
        self.assertEqual(self.a.post("/api/past-exams/analyze", {"document_ids": [987654]})[0], 404)


class SearchCodingImageTests(unittest.TestCase):
    def setUp(self):
        self.a = Api()
        self.a.doc()
        self.a.post("/api/notes", {"title": "Deadlock note", "content": "Remember the four deadlock conditions."})
        self.a.post("/api/courses", {"name": "Deadlock Theory"})

    def test_search_groups(self):
        _, r = self.a.get("/api/search?q=deadlock")
        res = r["results"]
        self.assertTrue(res["documents"] and res["notes"] and res["courses"])
        self.assertEqual(self.a.get("/api/search?q=a")[1]["results"], {})
        self.assertEqual(Api("Omar Bah").get("/api/search?q=deadlock")[1]["results"], {})

    def test_coding_helper(self):
        _, r = self.a.post("/api/coding/analyze", {"code": "def f(x):\n    return x / 0\nresult = f(1)", "error": "ZeroDivisionError: division by zero"})
        self.assertEqual(r["error"]["kind"], "ZeroDivisionError")
        self.assertTrue(any("0" in i["message"] for i in r["python"]["issues"]))
        _, bad = self.a.post("/api/coding/analyze", {"code": "if x == 1\n    pass"})
        self.assertEqual(bad["python"]["syntax_error"]["line"], 1)
        _, other = self.a.post("/api/coding/analyze", {"code": "int main(){}", "language": "c"})
        self.assertIn("Nothing was run", " ".join(other["notes"]))

    def test_no_ai_endpoints_exist(self):
        """The project must not use any LLM: the AI-only endpoints are gone."""
        r = self.a.c.post("/api/images/explain", data={}, headers=self.a.h())
        self.assertEqual(r.status_code, 404)
        self.assertFalse(self.a.get("/api/capabilities")[1]["llm"])

    def test_learning_commands_open_panels_from_chat(self):
        for text, panel in (("show my progress", "progress"), ("quiz me on deadlock", "quiz"), ("make flashcards", "flashcards"),
                            ("study plan", "study_plan"), ("analyze my past exams", "past_exams"), ("open my notes", "notes")):
            _, r = self.a.post("/api/chat", {"text": text})
            self.assertEqual(r["actions"][0]["panel"], panel, text)

    def test_assignment_requests_get_guidance_not_answers(self):
        _, r = self.a.post("/api/chat", {"text": "solve my assignment"})
        self.assertEqual(r["intent"], "integrity")
        self.assertIn("what you've tried", r["replies"][0])


class PrivacyAndIsolationTests(unittest.TestCase):
    """One student must never see, change or learn about another student's data."""

    def setUp(self):
        self.a, self.b = Api("Awa Jallow"), Api("Omar Bah")
        self.did = self.a.doc()
        self.nid = self.a.post("/api/notes", {"content": "Awa's secret note about deadlock"})[1]["note"]["id"]
        self.qid = self.a.post("/api/quizzes/generate", {"source": {"type": "document", "id": self.did}, "count": 4})[1]["quiz"]["id"]
        self.cardid = self.a.post("/api/flashcards", {"front": "secret front", "back": "secret back"})[1]["card"]["id"]
        exam = (datetime.date.today() + datetime.timedelta(days=6)).isoformat()
        self.pid = self.a.post("/api/study-plans", {"exam_date": exam})[1]["plan"]["id"]
        self.course = self.a.post("/api/courses", {"name": "Awa course"})[1]["course"]["id"]

    def test_every_object_id_is_404_for_the_other_student(self):
        b = self.b
        for path in (f"/api/documents/{self.did}", f"/api/documents/{self.did}/text", f"/api/notes/{self.nid}", f"/api/quizzes/{self.qid}",
                     f"/api/study-plans/{self.pid}"):
            self.assertEqual(b.get(path)[0], 404, path)
        for path in (f"/api/documents/{self.did}/summary", f"/api/documents/{self.did}/notes", f"/api/documents/{self.did}/course",
                     f"/api/notes/{self.nid}", f"/api/notes/{self.nid}/flashcards", f"/api/notes/{self.nid}/quiz", f"/api/notes/{self.nid}/summarize",
                     f"/api/quizzes/{self.qid}/submit", f"/api/quizzes/{self.qid}/similar", f"/api/flashcards/{self.cardid}/review",
                     f"/api/study-plans/{self.pid}/adapt", f"/api/courses/{self.course}/rename"):
            self.assertEqual(b.post(path, {"rating": 3, "mode": "quick", "name": "x", "content": "x"})[0], 404, path)
        for path in (f"/api/documents/{self.did}", f"/api/notes/{self.nid}", f"/api/quizzes/{self.qid}", f"/api/flashcards/{self.cardid}",
                     f"/api/study-plans/{self.pid}", f"/api/courses/{self.course}"):
            self.assertEqual(b.delete(path)[0], 404, path)
        # ...and nothing was changed by those attempts
        self.assertEqual(self.a.get(f"/api/documents/{self.did}")[0], 200)
        self.assertEqual(self.a.get(f"/api/notes/{self.nid}")[0], 200)

    def test_sources_for_generation_must_belong_to_you(self):
        for src in ({"type": "document", "id": self.did}, {"type": "note", "id": self.nid}, {"type": "course", "id": self.course}):
            self.assertEqual(self.b.post("/api/quizzes/generate", {"source": src})[0], 404, src)
            self.assertEqual(self.b.post("/api/flashcards/generate", {"source": src})[0], 404, src)
        self.assertEqual(self.b.post("/api/study-plans", {"exam_date": (datetime.date.today() + datetime.timedelta(days=5)).isoformat(), "course_id": self.course})[0], 404)
        self.assertEqual(self.b.post("/api/notes", {"content": "x", "document_id": self.did})[0], 404)
        self.assertEqual(self.b.post("/api/past-exams/analyze", {"document_ids": [self.did]})[0], 404)

    def test_retrieval_and_chat_never_leak(self):
        _, r = self.b.post("/api/chat", {"text": "what is a deadlock transactions lock"})
        self.assertNotEqual(r["intent"], "document_answer")
        self.assertEqual(r["sources"], [])
        conv = self.b.post("/api/conversations")[1]["conversation"]["id"]
        self.assertEqual(self.b.post(f"/api/conversations/{conv}/context", {"document_id": self.did})[0], 404)
        self.assertEqual(self.b.get("/api/documents")[1]["documents"], [])
        self.assertEqual(self.b.get("/api/notes")[1]["notes"], [])
        self.assertEqual(self.b.get("/api/flashcards")[1]["cards"], [])
        self.assertEqual(self.b.get("/api/flashcards/due")[1]["cards"], [])
        self.assertEqual(self.b.get("/api/quizzes")[1]["quizzes"], [])
        self.assertEqual(self.b.get("/api/study-plans")[1]["plans"], [])
        self.assertEqual(self.b.get("/api/courses")[1]["courses"], [])
        self.assertEqual(self.b.get("/api/search?q=secret")[1]["results"], {})      # A's note says "secret"
        self.assertEqual(self.b.get(f"/api/progress?course_id={self.course}")[0], 404)

    def test_progress_is_per_student(self):
        self.a.post(f"/api/quizzes/{self.qid}/submit", {"answers": {}})
        self.assertEqual(self.a.get("/api/progress")[1]["progress"]["quizzes_taken"], 1)
        self.assertEqual(self.b.get("/api/progress")[1]["progress"]["quizzes_taken"], 0)

    def test_login_and_csrf_required_everywhere(self):
        anon = test_app.Client()
        paths = ["/api/conversations", "/api/history", "/api/documents", "/api/notes", "/api/quizzes", "/api/flashcards", "/api/flashcards/due",
                 "/api/study-plans", "/api/progress", "/api/courses", "/api/settings", "/api/profile", "/api/search?q=abc", "/api/export",
                 "/api/capabilities", "/api/due_reminders", f"/api/documents/{self.did}", f"/api/notes/{self.nid}"]
        for p in paths:
            self.assertEqual(anon.c.get(p).status_code, 401, p)
        # logged in, but no CSRF header on a state-changing request
        for p in ("/api/conversations", "/api/notes", "/api/flashcards", "/api/settings", "/api/history/clear", "/api/courses"):
            self.assertEqual(self.a.c.post(p, json={"content": "x", "front": "a", "back": "b", "name": "n"}).status_code, 400, p)
        self.assertEqual(self.a.c.delete(f"/api/notes/{self.nid}").status_code, 400)

    def test_export_and_delete_my_data(self):
        r = self.a.c.get("/api/export")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["profile"]["email"], self.a.email)
        self.assertTrue(data["notes"] and data["documents"])
        self.assertNotIn("Omar", json.dumps(data))
        self.assertEqual(self.a.post("/api/data/delete", {"what": "documents", "confirm": "nope"})[0], 400)
        self.assertEqual(self.a.post("/api/data/delete", {"what": "documents", "confirm": "DELETE"})[0], 200)
        self.assertEqual(self.a.get("/api/documents")[1]["documents"], [])
        self.assertEqual(len(self.a.get("/api/notes")[1]["notes"]), 1)          # notes untouched
        self.assertEqual(self.a.post("/api/data/delete", {"what": "learning", "confirm": "DELETE"})[0], 200)
        self.assertEqual(self.a.get("/api/quizzes")[1]["quizzes"], [])
        self.assertEqual(self.a.post("/api/data/delete", {"what": "account", "confirm": "DELETE", "password": "wrong"})[0], 403)
        self.assertEqual(self.a.post("/api/data/delete", {"what": "account", "confirm": "DELETE", "password": "correct horse"})[0], 200)
        self.assertEqual(self.a.c.get("/api/history").status_code, 401)
        self.assertEqual(self.b.get("/api/history")[0], 200)                    # the other account is untouched


class NavigationAndMigrationTests(unittest.TestCase):
    def test_sidebar_has_exactly_the_three_allowed_items(self):
        import re
        a = Api()
        html = a.c.get("/").get_data(as_text=True)
        nav = html[html.index('<nav class="sb-nav"'):html.index("</nav>")]
        labels = [re.sub(r"<[^>]+>|&[a-z]+;", "", m).strip() for m in re.findall(r'<button[^>]*class="nav-item[^"]*"[^>]*>(.*?)</button>', nav, re.S)]
        labels = [re.sub(r"^[^\w]+", "", l).strip() for l in labels]
        self.assertEqual(labels, ["New Chat", "Chat History", "Settings"])
        self.assertNotIn("🌙", html)                                   # no crescent moon beside the brand
        self.assertNotIn("moon", html[html.index('class="sb-brand"'):html.index("</aside>")])
        for banned in ("Dashboard", "AI Tutor", "Documents", "Notes", "Quizzes", "Flashcards", "Study Plan", "Progress", "Past Exams", "Courses"):
            self.assertNotIn(banned, nav)

    def test_old_database_is_migrated_without_losing_data(self):
        import os, sqlite3, tempfile
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                                password_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                                   role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, description TEXT NOT NULL, due_date TEXT NOT NULL, announced INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO users (full_name, email, password_hash) VALUES ('Old User', 'old@example.com', 'x');
            INSERT INTO messages (user_id, role, content) VALUES (1, 'user', 'an old question');
            INSERT INTO notes (user_id, content) VALUES (1, 'an old note');
        """)
        conn.commit(); conn.close()
        real = test_app.db.DB_PATH
        try:
            test_app.db.DB_PATH = path
            test_app.db.init_db(); test_app.db.init_db()                  # safe to run twice
            msgs = test_app.db.get_messages(1)
            self.assertEqual([m["content"] for m in msgs], ["an old question"])
            self.assertEqual(test_app.db.fetchall("SELECT title FROM conversations")[0]["title"], "Earlier chat")
            self.assertEqual(test_app.db.fetchall("SELECT content FROM notes")[0]["content"], "an old note")
        finally:
            test_app.db.DB_PATH = real


if __name__ == "__main__":
    unittest.main()
