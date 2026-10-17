"""
Nocturna's brain, as a plain text-in / text-out function.

This replaces main.py from the voice version. The decision logic is the same
(generic utility commands first, then the course catalog, then the UTG
knowledge base), but nothing here touches a microphone or speakers, so it
works for any number of students at once through the web app.

The one real difference is follow-up questions. The voice version could just
call listen() mid-command ("Which city?"). A web request can't wait for a
second answer, so instead respond() returns a `pending` dict describing what
it is waiting for, the web layer keeps that in the student's session, and the
next message is treated as the answer. Typing "cancel" abandons it.

    reply_lines, pending = respond(user, "weather", None)
    # -> ["Which city do you want the weather for?"], {"action": "weather"}
    reply_lines, pending = respond(user, "Banjul", pending)
    # -> ["The weather in Banjul is ..."], None
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import course_catalog as catalog
import reminders
import utilities as utils
from config import ASSISTANT_NAME
from knowledge_base import KnowledgeBase
from logger import log_interaction
from learning import retrieval, summaries
import db

kb = KnowledgeBase()

MAX_MESSAGE_CHARS = 500

_CANCEL_WORDS = {"cancel", "never mind", "nevermind", "stop", "forget it"}
_GREETINGS = {
    "hi", "hello", "hey", "hiya", "good morning", "good afternoon",
    "good evening", "salam", "assalamu alaikum", "as-salamu alaykum",
}
_THANKS = {"thanks", "thank you", "thank you so much", "thanks a lot", "many thanks"}
_GOODBYES = {"bye", "goodbye", "exit", "quit", "see you", "see you later"}

HELP_TEXT = (
    "**Ask me about UTG**: admissions, schools, fees, contacts, student associations, and course details for Computer Science, "
    "Telecommunication and Information Systems (try \"prerequisite for CPS 402\").\n\n"
    "**Study with your own material**: use the **＋** button to upload a PDF, Word, PowerPoint, text or Markdown file, then ask questions about it, "
    "get summaries, make notes, flashcards and quizzes, build a study plan, and analyse past exam papers.\n\n"
    "**Everyday tools**: the time, jokes, weather, a web search link, a map link, notes (\"note: bring my ID\"), and reminders "
    "(\"remind me to pay fees in 3 days\").\n\n"
    "Try: *show my progress*, *quiz me*, *make flashcards*, *study plan*, *my notes*, *my reminders*."
)

_SEARCH_RE = re.compile(
    r"^(?:please\s+)?(?:web\s+)?(?:search|google|look\s+up)(?:\s+for)?\s*(.*)$", re.I
)
_LOCATION_RE = re.compile(r"find\s+(?:the\s+)?location(?:\s+(?:of|for))?\s*(.*)$", re.I)
_WEATHER_RE = re.compile(r"weather(?:\s+(?:in|for|at|of))?\s*(.*)$", re.I)
_NOTE_RE = re.compile(
    r"^(?:please\s+)?(?:(?:take|save|write|make|add)\s+(?:down\s+)?(?:a\s+|this\s+)?)?"
    r"note\b\s*[:,\-]?\s*(?:that\s+|to\s+)?(.*)$",
    re.I,
)
_WRITE_DOWN_RE = re.compile(r"^(?:please\s+)?write\s+down\s*[:,\-]?\s*(.+)$", re.I)
_REMIND_DESC_RE = re.compile(r"^(?:please\s+)?remind\s+me\s+(?:to\s+)?(.+)$", re.I)

_LIST_NOTES_PHRASES = ("my notes", "list notes", "show notes", "show my notes", "what notes")
_LIST_REMINDER_PHRASES = ("my reminders", "list reminders", "what reminders", "show reminders")


def _clean_arg(value: str) -> str:
    return value.strip(" \t.!?\"'")


def _first_name(user) -> str:
    return user["full_name"].split()[0]


def greeting_for(user) -> str:
    return f"Hello {_first_name(user)}, I'm {ASSISTANT_NAME}, your UTG student assistant. How can I help you today?"


def format_due_reminder(r) -> str:
    return f"Reminder: {r['description']} (due {r['due_date']})"


# ---------------------------------------------------------------- routing

@dataclass
class Result:
    replies: list
    intent: str
    source: str = "utility"
    confidence: float = 1.0
    pending: dict = None
    sources: list = field(default_factory=list)   # citations shown under the reply
    actions: list = field(default_factory=list)   # buttons the page should offer / panels to open


def respond_rich(user, text: str, pending=None, ctx=None) -> Result:
    """The full reply: text, citations and UI actions.
    ctx = {"document_id": int|None, "course_id": int|None,
           "rag_k": int, "rag_min_score": float, "rag_fallback": bool}"""
    start = time.time()
    text = " ".join(text.split())[:MAX_MESSAGE_CHARS]
    if not text:
        return Result([], "empty", pending=pending)
    res = _route(user, text, pending, ctx or {})
    log_interaction(user["id"], text, res.intent, res.source, res.confidence, time.time() - start)
    return res


def respond(user, text: str, pending=None):
    """Plain version kept for simple callers and tests: (reply_lines, new_pending)."""
    res = respond_rich(user, text, pending)
    return res.replies, res.pending


def _route(user, text, pending, ctx) -> Result:
    lowered = text.lower()
    clean = lowered.strip(" .!?")

    if pending:
        if clean in _CANCEL_WORDS:
            return Result(["Okay, cancelled."], "cancel")
        return _continue_pending(user, text, pending)

    result = _handle_utility(user, text, lowered, clean)
    if result is not None:
        return result

    result = _handle_learning(user, text, lowered, ctx)
    if result is not None:
        return result

    # A document is open in this conversation: answer from it first.
    if ctx.get("document_id"):
        return _answer_from_documents(user, text, ctx, document_id=ctx["document_id"])

    # Not a command -- try the UTG knowledge base.
    answer, _matched_question, confidence, source = kb.search(lowered)
    if answer:
        srcs = [{"filename": source, "kb": True}] if source else []
        return Result([answer], "knowledge_base", source or "knowledge_base", confidence, sources=srcs)

    # Then the student's own documents (all of them, or the chosen course).
    if ctx.get("rag_fallback", True) and db.fetchone("SELECT 1 AS x FROM documents WHERE user_id = ? AND status = 'ready' AND kind = 'material' LIMIT 1", (user["id"],)):
        res = _answer_from_documents(user, text, ctx, document_id=None)
        if res.intent == "document_answer":
            return res

    return Result([
        "I'm still learning. Can you try asking that another way, or "
        "type \"help\" to see what I can do?"
    ], "unmatched", "none", confidence)


def _answer_from_documents(user, text, ctx, document_id=None) -> Result:
    """Retrieval-augmented answering without any language model: the best
    passages are found with TF-IDF and shown as quotations with their page and
    section. The retrieval settings (how many passages, how strict) come from
    the student's Settings > Documents / RAG tab through `ctx`."""
    k = int(ctx.get("rag_k") or 3)
    min_score = float(ctx.get("rag_min_score") or 0.12)
    chunks = retrieval.search_chunks(user["id"], text, document_id=document_id, course_id=ctx.get("course_id"), k=k, min_score=min_score)
    if not chunks:
        if document_id:
            doc = db.fetchone("SELECT filename FROM documents WHERE id = ? AND user_id = ?", (document_id, user["id"]))
            name = doc["filename"] if doc else "this document"
            return Result([f"I couldn't find that in **{name}**. Try different words from the document, or ask about a specific section. "
                           "You can also close the document to ask general questions."], "document_miss", "documents", 0.0)
        return Result(["I'm still learning."], "unmatched", "none", 0.0)
    cites = [retrieval.citation(c) for c in chunks]
    lines = [f"Here {'is the most relevant passage' if len(chunks) == 1 else 'are the most relevant passages'} from your material:", ""]
    for c in chunks:
        where = c["filename"] + (f", page {c['page']}" if c["page"] else "") + (f", {c['section']}" if c["section"] else "")
        body = " ".join(c["text"].split())
        body = body if len(body) <= 520 else body[:520].rsplit(" ", 1)[0] + "..."
        lines += [f"> {body}", f"> *({where})*", ""]
    lines.append("*These passages are quoted directly from your document. Nocturna does not use an AI model, so it shows the source text rather than rewriting it.*")
    return Result(["\n".join(lines)], "document_answer", "documents", chunks[0]["score"], sources=cites)


# ----------------------------------------------------- learning commands

_ACT = lambda panel, **kw: {"type": "open_panel", "panel": panel, **kw}

_PROGRESS_RE = re.compile(r"\b(?:show|see|view|check)\s+(?:me\s+)?(?:my\s+)?(?:learning\s+)?progress\b|\bmy\s+(?:learning\s+)?progress\b|\bhow am i doing\b", re.I)
_QUIZ_RE = re.compile(r"\b(?:quiz me|test me|(?:make|create|generate|give me|start)\s+(?:me\s+)?(?:a\s+)?(?:practice\s+)?quiz(?:zes)?)\b(?:\s+(?:on|about)\s+(?P<topic>.+))?", re.I)
_CARDS_RE = re.compile(r"\b(?:make|create|generate|study|review|show)\b.*\bflash\s?cards?\b|\bflash\s?cards?\b", re.I)
_PLAN_RE = re.compile(r"\bstudy\s*plan\b|\bplan my (?:study|revision)\b|\bexam\s*plan\b|\brevision\s*plan\b", re.I)
_SUMMARY_RE = re.compile(r"\bsummari[sz]e\b|\bsummary\b", re.I)
_PAST_RE = re.compile(r"\bpast\s*(?:exam|paper)s?\b|\banaly[sz]e.*\bexam\b", re.I)
_MOCK_RE = re.compile(r"\bmock\s*exam\b|\bexam\s*simulator\b", re.I)
_CODE_RE = re.compile(r"\b(?:debug|fix my code|explain (?:this|my) code|coding help|code help|help with (?:my )?code)\b", re.I)
_DOCS_RE = re.compile(r"\b(?:my\s+documents|upload\s+(?:a\s+|my\s+)?(?:document|file|pdf|notes)|attach\s+(?:a\s+)?file)\b", re.I)
_INAPP_SEARCH_RE = re.compile(r"\bsearch\s+(?:my\s+)?(notes|documents|flash\s?cards|conversations|chats)\b(?:\s+for)?\s*(.*)$", re.I)
_NOTES_PANEL_RE = re.compile(r"\b(?:open|manage|edit)\s+(?:my\s+)?notes\b", re.I)
_COURSES_RE = re.compile(r"\bmy\s+courses\b", re.I)
_ASSIGNMENT_RE = re.compile(r"\b(?:do|solve|write|finish|complete)\s+(?:my|this|the)\s+(?:assignment|homework|coursework|essay|lab)\b", re.I)


def _handle_learning(user, text, lowered, ctx):
    doc_id = ctx.get("document_id")
    m = _INAPP_SEARCH_RE.search(text)
    if m:
        return Result(["Opening search."], "search_app", actions=[_ACT("search", query=m.group(2).strip())])
    if _MOCK_RE.search(text):
        return Result(["Mock exams are built from your uploaded past papers. Opening the past-exam tools."], "mock_exam", actions=[_ACT("past_exams")])
    if _PAST_RE.search(text):
        return Result(["Upload your past papers there, then I can show which topics come up most often in them."], "past_exam", actions=[_ACT("past_exams")])
    if _PLAN_RE.search(text):
        return Result(["Tell me your exam date and how much time you have, and I'll build a plan."], "study_plan", actions=[_ACT("study_plan")])
    if _PROGRESS_RE.search(text):
        return Result(["Here is your progress."], "progress", actions=[_ACT("progress")])
    if _SUMMARY_RE.search(text) and doc_id:
        mode = "exam" if "exam" in lowered else "detailed" if "detail" in lowered else "chapter" if "chapter" in lowered or "section" in lowered else "quick"
        out = summaries.summarize(user["id"], doc_id, mode)
        if out:
            return Result([out["markdown"]], "document_summary", "documents", sources=out["sources"],
                          actions=[{"type": "save_note", "label": "Save to notes"}])
    if _SUMMARY_RE.search(text) and not doc_id:
        return Result(["Open a document first (the **＋** button, then *Ask about document*), then ask me to summarise it."], "document_summary",
                      actions=[_ACT("documents")])
    m = _QUIZ_RE.search(text)
    if m:
        return Result(["Let's set up a quiz."], "quiz", actions=[_ACT("quiz", topic=(m.group("topic") or "").strip(" .?!"), document_id=doc_id)])
    if _CARDS_RE.search(text):
        return Result(["Opening flashcards."], "flashcards", actions=[_ACT("flashcards", document_id=doc_id)])
    if _CODE_RE.search(text):
        return Result(["Paste your code or error message in the coding helper."], "coding", actions=[_ACT("coding")])
    if _NOTES_PANEL_RE.search(text):
        return Result(["Opening your notes."], "notes_panel", actions=[_ACT("notes")])
    if _DOCS_RE.search(text):
        return Result(["Here are your documents."], "documents", actions=[_ACT("documents")])
    if _COURSES_RE.search(text):
        rows = db.fetchall("SELECT name FROM courses WHERE user_id = ? ORDER BY name", (user["id"],))
        if not rows:
            return Result(["You haven't added any courses yet. You can add them in **User Profile**."], "courses", actions=[_ACT("profile")])
        return Result(["Your courses:\n" + "\n".join(f"- {r['name']}" for r in rows)], "courses")
    if _ASSIGNMENT_RE.search(text):
        return Result([
            "I'd rather help you do it than hand over an answer. Tell me which part you're stuck on and what you've tried so far, "
            "and I can point to the relevant material in your documents, help you break it into steps, or quiz you on the concepts it needs."
        ], "integrity")
    return None


def _continue_pending(user, text, pending) -> Result:
    return _wrap5(_continue_pending_tuple(user, text, pending))


def _wrap5(t):
    replies, intent, source, conf, pend = t
    return Result(replies, intent, source, conf, pend)


def _continue_pending_tuple(user, text, pending):
    action = pending.get("action")

    if action == "weather":
        return [utils.get_weather(_clean_arg(text))], "weather", "utility", 1.0, None
    if action == "search":
        return [utils.web_search(_clean_arg(text))], "web_search", "utility", 1.0, None
    if action == "location":
        return [utils.find_location(_clean_arg(text))], "location", "utility", 1.0, None
    if action == "note":
        return [utils.save_note(user["id"], text)], "note", "utility", 1.0, None

    if action == "remind_desc":
        new_pending = {"action": "remind_due", "description": text}
        return [_ASK_WHEN], "set_reminder", "utility", 1.0, new_pending

    if action == "remind_due":
        success, message = reminders.add_reminder(user["id"], pending["description"], text)
        # On a bad date keep waiting so the student can just retype the date.
        return [message], "set_reminder", "utility", 1.0, (None if success else pending)

    return ["Sorry, I lost track of what we were doing. Please ask again."], "error", "utility", 1.0, None


_ASK_WHEN = (
    "When should I remind you? Use a date like 2026-11-05 (year-month-day), "
    "or say 'tomorrow' or 'in 3 days'."
)


def _handle_utility(user, text, lowered, clean):
    """Generic commands. Returns a Result, or None to fall through."""
    # In-app search and the notes panel are handled by _handle_learning.
    if _INAPP_SEARCH_RE.search(text) or _NOTES_PANEL_RE.search(text):
        return None
    t = _handle_utility_tuple(user, text, lowered, clean)
    if t is None:
        return None
    replies, intent, pending = t
    return Result(replies, intent, pending=pending)


def _handle_utility_tuple(user, text, lowered, clean):
    """Returns (replies, intent, new_pending) if a utility command matched,
    otherwise None so the caller falls through."""

    if clean in _GREETINGS:
        return [greeting_for(user)], "greeting", None

    if clean in _THANKS:
        return ["You're welcome! Anything else I can help with?"], "thanks", None

    if clean in _GOODBYES:
        return ["Goodbye! Come back any time."], "exit", None

    if "what is your name" in lowered or clean in ("who are you", "your name"):
        return [f"My name is {ASSISTANT_NAME}, the UTG student assistant."], "identity", None

    if "what time is it" in lowered or "what's the time" in lowered or "what is the time" in lowered:
        now = datetime.now(timezone.utc)
        # The Gambia is on GMT all year, so UTC is the correct local time there.
        return [now.strftime("It's %H:%M GMT on %A, %d %B %Y.")], "time", None

    if "joke" in lowered:
        return [utils.tell_joke()], "joke", None

    if "weather" in lowered:
        m = _WEATHER_RE.search(text)
        city = _clean_arg(m.group(1)) if m else ""
        if city:
            return [utils.get_weather(city)], "weather", None
        return ["Which city do you want the weather for?"], "weather", {"action": "weather"}

    m = _SEARCH_RE.match(text)
    if m:
        query = _clean_arg(m.group(1))
        if query:
            return [utils.web_search(query)], "web_search", None
        return ["What do you want to search for?"], "web_search", {"action": "search"}

    m = _LOCATION_RE.search(text)
    if m:
        place = _clean_arg(m.group(1))
        if place:
            return [utils.find_location(place)], "location", None
        return ["What location do you want to search for?"], "location", {"action": "location"}

    if any(p in lowered for p in _LIST_NOTES_PHRASES):
        return [utils.list_notes(user["id"])], "list_notes", None

    m = _NOTE_RE.match(text) or _WRITE_DOWN_RE.match(text)
    if m:
        content = m.group(1).strip()
        if content:
            return [utils.save_note(user["id"], content)], "note", None
        return ["What would you like me to write?"], "note", {"action": "note"}

    if any(p in lowered for p in _LIST_REMINDER_PHRASES):
        upcoming = reminders.get_upcoming_reminders(user["id"])
        if not upcoming:
            return ["You don't have any upcoming reminders."], "list_reminders", None
        lines = [f"- {r['description']} on {r['due_date']}" for r in upcoming]
        return ["Here are your upcoming reminders:\n" + "\n".join(lines)], "list_reminders", None

    if "remind me" in lowered or "set a reminder" in lowered:
        # One line with everything ("remind me to X in 3 days") works at once.
        description, due_text = reminders.parse_reminder_command(text)
        if description and due_text:
            _success, message = reminders.add_reminder(user["id"], description, due_text)
            return [message], "set_reminder", None
        # Description given but no date: only ask for the date.
        m = _REMIND_DESC_RE.match(text)
        if m and m.group(1).strip():
            return [_ASK_WHEN], "set_reminder", {"action": "remind_due", "description": m.group(1).strip()}
        return ["What should I remind you about?"], "set_reminder", {"action": "remind_desc"}

    catalog_response = catalog.handle_catalog_query(text)
    if catalog_response:
        return [catalog_response], "course_catalog", None

    if clean == "help" or "what can you do" in lowered:
        return [HELP_TEXT], "help", None

    return None
