"""
Structured lookup over the BSc Computer Science and BSc Telecommunication
course catalogs (data/programs.json) -- course codes, titles, credit hours,
prerequisites, and semester placement.

This is deliberately a SEPARATE system from retrieval_methods.py /
knowledge_base.py. The FAQ knowledge base answers free-text questions by
matching against a bank of Q&A pairs, which works well for "how much is
tuition" but is the wrong shape for "what is the prerequisite for CPS 402"
-- that's a precise structured lookup, not a similarity match, and this
module answers it exactly rather than approximately.

Course data is transcribed from BSc_Computer_Science.docx,
BSc_Telecom_2022.docx, and the Information Systems study plan PDF.

A Computer Science minor exists (see programs.json's minor_overview text)
but its detailed course-by-course list isn't represented here: the only
source for it was a photographed sheet using a different course-numbering
scheme than the main study plan, which the student confirmed is from a
different catalog year. Only the overview paragraph (that it exists and
requires the same 57 credit hours of CS core courses) was kept -- there is
no per-course minor lookup.
"""

import json
import os
import re

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "programs.json")

_PROGRAM_ALIASES = {
    "computer_science": ["computer science", "cs", "comp sci", "computing"],
    "telecommunication": ["telecommunication", "telecommunications", "telecom", "tel"],
    "information_systems": ["information systems", "is department", "information system"],
}

_CODE_PATTERN = re.compile(r"\b([a-z]{2,4})\s?-?\s?(\d{3})\b", re.IGNORECASE)
_SEMESTER_PATTERN = re.compile(
    r"year\s*([1-4]).{0,15}semester\s*([1-2])|semester\s*([1-2]).{0,15}year\s*([1-4])",
    re.IGNORECASE,
)


def _load_catalog():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _match_program(text: str):
    """Returns the program key ('computer_science', 'telecommunication',
    'information_systems') found in text, or None."""
    text = text.lower()
    for key, aliases in _PROGRAM_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if alias in text:
                return key
    return None


def find_course(query: str):
    """
    Finds a course by code (e.g. "CPS 402", "cps402") or by title, searching
    both programs. Returns a dict with course info + which programme(s) it
    belongs to, or None if nothing matched.

    Within a single program, course groups are searched in priority order
    (main semester plan, then electives, then minor list) and the FIRST
    match wins -- this matters because the minor list (transcribed from a
    photographed sheet with a different numbering scheme, see
    minor_numbering_caveat) sometimes lists the same course title under a
    different code than the main study plan. Without this priority order, a
    title search for something like "Artificial Intelligence" could
    non-deterministically return the minor list's code instead of the
    primary program's code.
    """
    catalog = _load_catalog()
    code_match = _CODE_PATTERN.search(query)
    target_code = f"{code_match.group(1).upper()} {code_match.group(2)}" if code_match else None
    query_lower = query.lower()

    matches = []  # (course_dict, program_full_name), one per program at most

    for prog_key, prog in catalog.items():
        if not prog:
            continue

        course_groups = list(prog.get("semesters", {}).values())
        course_groups.append(prog.get("electives", []))

        prog_match = None

        # Pass 1: exact code match, or exact title match, in priority order.
        for group in course_groups:
            for c in group:
                if target_code and c["code"] == target_code:
                    prog_match = c
                    break
                if not target_code and c["title"].lower() == query_lower.strip():
                    prog_match = c
                    break
            if prog_match:
                break

        # Pass 2 (title search only): fall back to substring match if no
        # exact title match was found anywhere in this program.
        if not prog_match and not target_code:
            for group in course_groups:
                for c in group:
                    if c["title"].lower() in query_lower:
                        prog_match = c
                        break
                if prog_match:
                    break

        if prog_match:
            matches.append((prog_match, prog["full_name"]))

    if not matches:
        return None

    first_course = matches[0][0]
    program_names = [m[1] for m in matches]
    return {**first_course, "programs": program_names}


def get_semester(query: str):
    """Parses 'year N semester N' + a program name from query. Returns
    (label, courses, prog_key) -- label and courses are None if parsing
    failed at either step; prog_key is None only if no program name was
    found in the query at all (useful for the caller to distinguish 'wrong
    program' from 'right program, bad year/semester')."""
    catalog = _load_catalog()
    prog_key = _match_program(query)
    if not prog_key or not catalog.get(prog_key):
        return None, None, prog_key

    m = _SEMESTER_PATTERN.search(query)
    if not m:
        return None, None, prog_key
    year = m.group(1) or m.group(4)
    semester = m.group(2) or m.group(3)
    label = f"Year {year} Semester {semester}"

    courses = catalog[prog_key]["semesters"].get(label)
    if not courses:
        return None, None, prog_key
    return label, courses, prog_key


def get_electives(query: str):
    catalog = _load_catalog()
    prog_key = _match_program(query)
    if not prog_key or not catalog.get(prog_key):
        return None, prog_key
    return catalog[prog_key].get("electives"), prog_key


def get_overview(query: str):
    """Returns (program_dict, prog_key) for program-level facts: total
    credit hours, the major requirements summary, and minor info if any.
    Used for questions like 'how many credits do I need for computer
    science' rather than a specific course."""
    catalog = _load_catalog()
    prog_key = _match_program(query)
    if not prog_key or not catalog.get(prog_key):
        return None, prog_key
    return catalog[prog_key], prog_key


def format_overview(prog: dict) -> str:
    parts = [f"{prog['full_name']}: {prog['total_credit_hours']} total credit hours required."]
    if prog.get("major_requirements_overview"):
        parts.append(prog["major_requirements_overview"])
    elif prog.get("electives_note"):
        parts.append(prog["electives_note"])
    if prog.get("minor_offered") and prog.get("minor_overview"):
        parts.append(prog["minor_overview"])
    return " ".join(parts)


_PLACEHOLDER_CODES = {"GER-ELECTIVE", "400-LEVEL-ELECTIVE"}


def format_course(c: dict) -> str:
    prereq = c.get("prerequisite") or "None"
    credits = c.get("credits")
    credits_text = f"{credits} credit hours" if credits is not None else "credit hours not specified in the source document"
    programs = c.get("programs")
    program_text = f" (in {', '.join(programs)})" if programs else ""
    if c["code"] in _PLACEHOLDER_CODES:
        return f"{c['title']}{program_text}. {credits_text}."
    return (
        f"{c['code']}: {c['title']}{program_text}. {credits_text}. "
        f"Prerequisite: {prereq}."
    )


def format_course_list(label: str, courses: list) -> str:
    parts = [
        c["title"] if c["code"] in _PLACEHOLDER_CODES else f"{c['code']} {c['title']}"
        for c in courses
    ]
    return f"{label}: " + "; ".join(parts) + "."


def handle_catalog_query(text: str):
    """
    Single entry point for chatbot.py. Tries each catalog capability in
    priority order and returns a chat-ready answer string, or None if
    this doesn't look like a catalog question at all -- callers should fall
    through to the general FAQ knowledge base in that case.
    """
    text_lower = text.lower()

    if "prerequisite" in text_lower:
        c = find_course(text)
        if c:
            return f"The prerequisite for {c['code']} {c['title']} is {c.get('prerequisite') or 'None'}."
        return (
            "I couldn't find that course in the catalog. Try typing the "
            "course code, like CPS 402."
        )

    if "credit hour" in text_lower or "how many credit" in text_lower:
        c = find_course(text)
        if c:
            credits = c.get("credits")
            credits_text = (
                f"{credits} credit hours" if credits is not None
                else "an unspecified number of credit hours in the source document"
            )
            return f"{c['code']} {c['title']} is {credits_text}."
        prog, _ = get_overview(text)
        if prog:
            return format_overview(prog)
        return None

    if any(
        p in text_lower
        for p in (
            "graduation requirement", "major requirement", "minor requirement",
            "requirements to graduate", "requirements for a major", "requirements for a minor",
        )
    ):
        prog, _ = get_overview(text)
        if prog:
            return format_overview(prog)
        return None

    if "elective" in text_lower:
        electives, prog_key = get_electives(text)
        if electives:
            label = f"{prog_key.replace('_', ' ').title()} electives"
            return format_course_list(label, electives)
        if prog_key:
            return f"I don't have elective information for {prog_key.replace('_', ' ')} yet."
        return None

    if _SEMESTER_PATTERN.search(text_lower):
        label, courses, prog_key = get_semester(text)
        if label and courses:
            return format_course_list(label, courses)
        if prog_key:
            return (
                "I couldn't find that specific year and semester -- try "
                "typing it like 'year 2 semester 1'."
            )
        return None

    if _CODE_PATTERN.search(text) or "tell me about" in text_lower or text_lower.startswith("what is "):
        c = find_course(text)
        if c:
            return format_course(c)

    return None
