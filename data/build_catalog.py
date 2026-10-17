"""
Provenance script for data/programs.json -- NOT run automatically by the
assistant. This is how the course catalog data was originally transcribed
from the three source documents (BSc_Computer_Science.docx,
BSc_Telecom_2022.docx, and the Information Systems study plan PDF), kept
here so the transcription is auditable and so programs.json can be
regenerated if a source document is corrected.

Each semester has an assertion checking the transcribed credit total
against the "Total" row printed in that source document -- a self-check
against transcription errors, confirmed to all pass when this was built.
The Information Systems section additionally checks against the source
PDF's own printed summary ("Study plan total: 148 credits, 47 courses").

Deliberately excludes the photographed CS "Major/Minor Requirements" sheets'
detailed course-code tables -- the student confirmed those photos are from
a different catalog year than the docx/PDF study plans, so only their
overview paragraphs (total credit hours, GER/DER/core/elective structure)
are reflected in programs.json, as major_requirements_overview /
minor_overview text, not as course lists.

Run with: python build_catalog.py  (from inside the data/ folder, or
anywhere -- output path is relative to this file's own location)
"""
import json

def course(code, title, credits, prereq, category):
    return {"code": code, "title": title, "credits": credits, "prerequisite": prereq, "category": category}

def check(label, courses, expected_total):
    total = sum(c["credits"] for c in courses)
    assert total == expected_total, f"{label}: got {total}, expected {expected_total}"

# ---------------- COMPUTER SCIENCE (source: BSc_Computer_Science.docx) ----------------
cs_semesters = {}

cs_semesters["Year 1 Semester 1"] = [
    course("GEL 101", "Use of English I", 3, "None", "GER"),
    course("MTH 101", "Calculus I", 3, "None", "GER"),
    course("ICT 101", "Introduction to I.C.T.", 3, "None", "DER"),
    course("ICT 102", "Introduction to Computing & I.S", 3, "None", "DER"),
    course("ICT 103", "Programming Logic and Design", 3, "None", "DER"),
    course("ICT 104", "Ethics for Computing and Engineering", 3, "None", "DER"),
]
check("CS Y1S1", cs_semesters["Year 1 Semester 1"], 18)

cs_semesters["Year 1 Semester 2"] = [
    course("GEL 102", "Use of English 102", 3, "GEL 101", "GER"),
    course("SCI 101", "Introduction to General Science", 3, "None", "GER"),
    course("MTH 102", "Calculus II", 3, "MTH 101", "DER"),
    course("GER 107", "Cultural Studies", 3, "None", "GER"),
    course("GER-ELECTIVE", "Social and Behavioral Sciences (Choose 1 Course)", 3, "None", "GER"),
    course("ICT 110", "Computer Programming I", 4, "ICT 103", "DER"),
]
check("CS Y1S2", cs_semesters["Year 1 Semester 2"], 19)

cs_semesters["Year 2 Semester 1"] = [
    course("FRE 101", "Elementary French I or any Foreign Language", 3, "None", "GER"),
    course("PHY 101", "Fundamentals of Physics I", 3, "None", "DER"),
    course("ICT 201", "Computer Architecture & Organization", 3, "None", "DER"),
    course("ICT 202", "Computer Programming II", 4, "ICT 110", "DER"),
    course("ICT 203", "Computer Networking I", 3, "ICT 102", "DER"),
    course("ICT 204", "Database Systems I", 4, "ICT 102", "DER"),
]
check("CS Y2S1", cs_semesters["Year 2 Semester 1"], 20)

cs_semesters["Year 2 Semester 2"] = [
    course("FRE 102", "Elementary French II or any Foreign", 3, "FRE 101", "GER"),
    course("GER-ELECTIVE", "Social and Behavioral Sciences (Choose 1 Course)", 3, "None", "GER"),
    course("GER-ELECTIVE", "Humanistic Tradition (Choose 1 Outside Major)", 3, "None", "GER"),
    course("MTH 203", "Linear Algebra for Computer Science", 3, "None", "DER"),
    course("ICT 210", "Data Structure & Algorithms", 4, "ICT 202", "DER"),
    course("ICT 211", "Introduction to Operating Systems", 3, "ICT 202", "DER"),
]
check("CS Y2S2", cs_semesters["Year 2 Semester 2"], 19)

cs_semesters["Year 3 Semester 1"] = [
    course("GER-ELECTIVE", "Economics & Mgt. Tradition (Choose 1 Course)", 3, "None", "GER"),
    course("ICT 301", "IT Project Management", 3, "ICT 103", "DER"),
    course("CPS 301", "Microprocessor Principles", 3, "ICT 201", "MAJOR"),
    course("CPS 302", "Automata and Languages", 3, "None", "MAJOR"),
    course("CPS 303", "Internet and Web Programming I", 3, "ICT 102", "MAJOR"),
    course("CPS 304", "Operating Systems II", 3, "ICT 211", "MAJOR"),
]
check("CS Y3S1", cs_semesters["Year 3 Semester 1"], 18)

cs_semesters["Year 3 Semester 2"] = [
    course("CPS 310", "Internet and Web Programming II", 3, "CPS 302", "MAJOR"),
    course("CPS 311", "Computer Logic and Discrete Structures", 3, "MTH 102", "MAJOR"),
    course("CPS 312", "Object Oriented Analysis and Design", 3, "ICT 202", "MAJOR"),
    course("CPS 313", "Computational Mathematics", 3, "MTH 101", "MAJOR"),
    course("CPS 314", "Organization of Programming languages", 3, "ICT 210", "MAJOR"),
    course("ICT 315", "Research Methodology in IT", 3, "None", "MAJOR"),
]
check("CS Y3S2", cs_semesters["Year 3 Semester 2"], 18)

cs_semesters["Year 4 Semester 1"] = [
    course("CPS 401", "Parallel and Distributed Programming", 3, "ICT 211", "MAJOR"),
    course("CPS 402", "Artificial Intelligence", 3, "ICT 210", "MAJOR"),
    course("CPS 403", "Cloud Computing", 3, "CPS 312", "MAJOR"),
    course("CPS 404", "Data Communications and Networks", 3, "ICT 211", "MAJOR"),
    course("CPS 405", "Database Systems II", 3, "ICT 204", "MAJOR"),
    course("ICT 406", "Seminar", 3, "ICT 315", "MAJOR"),
]
check("CS Y4S1", cs_semesters["Year 4 Semester 1"], 18)

cs_semesters["Year 4 Semester 2"] = [
    course("CPS 410", "Compiler Design and Interpreters", 3, "CPS 301", "MAJOR"),
    course("CPS 419", "Final Year Project", 6, "ICT 315", "MAJOR"),
    course("400-LEVEL-ELECTIVE", "400 Level Elective", 3, "None", "ELECTIVE"),
    course("400-LEVEL-ELECTIVE", "400 Level Elective", 3, "None", "ELECTIVE"),
]
check("CS Y4S2", cs_semesters["Year 4 Semester 2"], 15)

cs_electives = [
    course("CPS 411", "LAN Administration", 3, None, "ELECTIVE"),
    course("CPS 412", "Advance Application Development", 3, None, "ELECTIVE"),
    course("CPS 413", "Object-Oriented Analysis and Design II", 3, None, "ELECTIVE"),
    course("CPS 414", "Analysis and design of Algorithms", 3, None, "ELECTIVE"),
    course("CPS 415", "Intelligent Systems", 3, None, "ELECTIVE"),
    course("CPS 416", "Information Security and Ethical Hacking", 3, None, "ELECTIVE"),
    course("CPS 417", "Big Data Analytics", 3, None, "ELECTIVE"),
    course("CPS 418", "Computer Networking II", 3, None, "ELECTIVE"),
]

# NOTE on the photographed sheets (IMG_3462, IMG_3463): per the student,
# those photos are from a different catalog year than the docx study plans
# and their detailed course-code tables (GER list, DER list, Majors list,
# Minor course list) are NOT used here -- only the short overview text at
# the top of each page is trustworthy across years and kept below.

computer_science = {
    "full_name": "BSc (Hons) Computer Science",
    "department": "Department of Computer Science",
    "school": "School of Information Technology and Communications (SITC)",
    "total_credit_hours": 120,
    "source": "BSc_Computer_Science.docx (semester-by-semester study plan), provided by student, accessed 2026",
    "semesters": cs_semesters,
    "electives": cs_electives,
    "electives_note": "At least 12 credit hours (4 courses) of electives required, per the programme requirements overview.",
    "major_requirements_overview": (
        "To graduate with a major in Computer Science, students must complete a minimum of "
        "120 credit hours total, including: all General Education Requirements (GER) of the "
        "University of The Gambia; all Divisional Educational Requirements (DER) of the School "
        "of Information Technology and Communications; all 57 credit hours of the eighteen (18) "
        "Computer Science core (MAJOR) courses; and at least 12 credit hours (4 courses) of "
        "Computer Science electives."
    ),
    "minor_offered": True,
    "minor_overview": (
        "A minor in Computer Science is available. As with the major, it requires a minimum of "
        "120 overall credit hours including all University GER, and specifically includes all 57 "
        "credit hours of the same eighteen (18) Computer Science core courses used in the major. "
        "A detailed minor-specific course list wasn't available in a form consistent with the "
        "main study plan -- check with the Department of Computer Science for the current list."
    ),
}

# ---------------- TELECOMMUNICATIONS (source: BSc_Telecom_2022.docx) ----------------
tel_semesters = {}

tel_semesters["Year 1 Semester 1"] = [
    course("GEL 101", "Use of English I", 3, "None", "GER"),
    course("MTH 101", "Calculus I", 3, "None", "GER"),
    course("ICT 101", "Introduction to I.C.T.", 3, "None", "GER"),
    course("ICT 102", "Introduction to Computing & I.S", 3, "None", "DER"),
    course("ICT 103", "Programming Logic and Design", 3, "None", "DER"),
    course("ICT 104", "Ethics for Computing and Engineering", 3, "None", "DER"),
]
check("TEL Y1S1", tel_semesters["Year 1 Semester 1"], 18)

tel_semesters["Year 1 Semester 2"] = [
    course("GEL 102", "Use of English 102", 3, "GEL 101", "GER"),
    course("SCI 101", "Introduction to General Science", 3, "None", "GER"),
    course("MTH 102", "Calculus II", 3, "MTH 101", "DER"),
    course("GER 107", "Cultural Studies", 3, "None", "DER"),
    course("ICT 110", "Computer Programming I", 4, "ICT 103", "DER"),
    course("GER-ELECTIVE", "Social and Behavioral Sciences (Choose any 1)", 3, "None", "DER"),
]
check("TEL Y1S2", tel_semesters["Year 1 Semester 2"], 19)

tel_semesters["Year 2 Semester 1"] = [
    course("FRE 101", "Elementary French I or any Foreign Language", 3, "None", "GER"),
    course("PHY 101", "Fundamentals of Physics I", 3, "None", "GER"),
    course("ICT 201", "Computer Architecture & Organization", 3, "None", "DER"),
    course("ICT 202", "Computer Programming II", 3, "ICT 110", "DER"),
    course("ICT 203", "Computer Networking I", 3, "ICT 102", "DER"),
    course("ICT 204", "Database Systems I", 3, "ICT 102", "DER"),
]
check("TEL Y2S1", tel_semesters["Year 2 Semester 1"], 18)

tel_semesters["Year 2 Semester 2"] = [
    course("FRE 102", "Elementary French II or any Foreign", 3, "FRE 101", "GER"),
    course("GER-ELECTIVE", "Social and Behavioral Sciences (Choose 1 Course)", 3, "None", "GER"),
    course("GER-ELECTIVE", "Humanistic Tradition (Choose 1 Outside Major)", 4, "None", "GER"),
    course("MTH 203", "Linear Algebra", 3, "MTH 102", "DER"),
    course("ICT 210", "Data Structure & Algorithms", 3, "ICT 202", "DER"),
    course("ICT 211", "Principles of Operating System", 3, "ICT 202", "DER"),
]
check("TEL Y2S2", tel_semesters["Year 2 Semester 2"], 19)

tel_semesters["Year 3 Semester 1"] = [
    course("GER-ELECTIVE", "Economics & Mgt. Tradition (Choose 1 Course)", 3, "None", "GER"),
    course("MTH 301", "Probability and Statistic I", 3, "MTH 102", "GER"),
    course("ICT 301", "Project Management", 3, "ICT 101", "DER"),
    course("TEL 301", "Analog and Digital Communications", 3, "ICT 101", "MAJOR"),
    course("TEL 302", "Designing and Implementing Wi-Fi and VoIP Network", 3, "ICT 203", "MAJOR"),
    course("TEL 303", "Designing and Administering Internetworks Infrastructure", 3, "ICT 203", "MAJOR"),
]
check("TEL Y3S1", tel_semesters["Year 3 Semester 1"], 18)

tel_semesters["Year 3 Semester 2"] = [
    course("TEL 310", "Digital Systems", 3, "TEL 301", "MAJOR"),
    course("TEL 311", "Switching and Automata Theory", 3, "TEL 301", "MAJOR"),
    course("TEL 312", "Telecommunication Network Management", 3, "TEL 301", "MAJOR"),
    course("TEL 313", "Satellite Technology", 3, "TEL 303", "MAJOR"),
    course("TEL 315", "Fiber-Optic Communications", 3, "TEL 303", "MAJOR"),
    course("ICT 315", "Research Methodology in IT", 3, "None", "MAJOR"),
]
check("TEL Y3S2", tel_semesters["Year 3 Semester 2"], 18)

tel_semesters["Year 4 Semester 1"] = [
    course("TEL 401", "Mathematics for Engineers", 3, "TEL 301", "MAJOR"),
    course("TEL 402", "Radio Frequency & Microwave Engineering", 3, "TEL 304", "MAJOR"),
    course("TEL 403", "Mobile Computing & Wireless Networks", 3, "TEL 303", "MAJOR"),
    course("TEL 404", "Digital Signal Processing", 3, "TEL 307", "MAJOR"),
    course("TEL 405", "Telecommunication Quality of Service Audit", 3, "TEL 307", "MAJOR"),
    course("ICT 406", "Seminar", 3, "ICT 315", "MAJOR"),
]
check("TEL Y4S1", tel_semesters["Year 4 Semester 1"], 18)
# Note: TEL 402's prerequisite "TEL 304" and TEL 404/405's prerequisite
# "TEL 307" are printed in the source document but neither TEL 304 nor
# TEL 307 appears anywhere else in the study plan. Transcribed as-is --
# this looks like a gap/typo in the original document, not mine to fix.

tel_semesters["Year 4 Semester 2"] = [
    course("TEL 407", "Legal and Regulatory Issues in Telecommunications", 3, "None", "MAJOR"),
    course("ICT 408", "Final Project", 6, "ICT 406", "MAJOR"),
    course("400-LEVEL-ELECTIVE", "400 Level Elective", 3, "None", "ELECTIVE"),
    course("400-LEVEL-ELECTIVE", "400 Level Elective", 3, "None", "ELECTIVE"),
]
check("TEL Y4S2", tel_semesters["Year 4 Semester 2"], 15)

tel_electives = [
    course("TEL 409", "Telecommunications Technology", None, None, "ELECTIVE"),
    course("TEL 410", "Telecommunications Switching and Transmission", None, None, "ELECTIVE"),
    course("TEL 411", "Broadband and Advance Communication", None, None, "ELECTIVE"),
    course("TEL 412", "Sensor Networks and Intelligent Systems", None, None, "ELECTIVE"),
    course("TEL 413", "Internet of Things", None, None, "ELECTIVE"),
    course("TEL 414", "Radio Access Technologies", None, None, "ELECTIVE"),
    course("TEL 415", "Mobile Computing", None, None, "ELECTIVE"),
    course("TEL 416", "Computer Systems and Networks", None, None, "ELECTIVE"),
]
# Credit hours intentionally None: the source document's elective table for
# Telecom has no "Hrs" column (unlike the CS electives table), so this isn't
# known rather than assumed to be the usual 3.

tel_ger_breakdown = [
    {"competency": "Writing Competence", "requirement": "GEL 101: Use of English 1 and GEL 102: Use of English 2", "hours": "6 semester hours"},
    {"competency": "Mathematics competence", "requirement": "MTH 103: Basic Mathematics or MTH 101: Calculus 1 (for all science students)", "hours": "3 semester hours"},
    {"competency": "Information Technology Competence", "requirement": "CPS 111: Introduction to Information Communication Technology (ICT)", "hours": "3 semester hours"},
    {"competency": "Foreign Language Competence", "requirement": "Any language offered except English: French 1&2, Arabic 1&2, or Spanish 1&2 (majors/minors in French or Islamic Studies take FRE/ARB 103 & 104 instead)", "hours": "6 semester hours"},
    {"competency": "Humanistic Tradition", "requirement": "GER 107: Cultural Studies plus one other course outside the student's major area (History, Literature, Philosophy, Law, or Religious Studies)", "hours": "6 semester hours"},
    {"competency": "Social and Behavioural Sciences", "requirement": "Two courses from: Psychology, Anthropology, Geography, Political Science, Sociology, Development and Gender Issues", "hours": "6 semester hours"},
    {"competency": "General Science Competence", "requirement": "SCI 101: Introduction to General Science", "hours": "3 semester hours"},
    {"competency": "Economics and Management Tradition", "requirement": "MGT 100: Introduction to Management or ECO 200: Economics of Development", "hours": "3 semester hours"},
]

telecommunication = {
    "full_name": "BSc Telecommunication",
    "department": "Department of Telecommunications",
    "school": "School of Information Technology and Communication (SITC)",
    "total_credit_hours": None,
    "source": "BSc_Telecom_2022.docx (semester-by-semester study plan), provided by student, accessed 2026",
    "semesters": tel_semesters,
    "electives": tel_electives,
    "ger_breakdown": tel_ger_breakdown,
    "minor_offered": False,
}

# ---------------- INFORMATION SYSTEMS (source: BSc (Hons) Information Systems Study Plan.pdf) ----------------
is_semesters = {}

is_semesters["Year 1 Semester 1"] = [
    course("GEL 101", "Use of English I", 3, "None", "GER"),
    course("MTH 101", "Calculus I", 3, "None", "GER"),
    course("ICT 101", "Introduction to I.C.T.", 3, "None", "DER"),
    course("ICT 102", "Introduction to Computing & I.S", 3, "None", "DER"),
    course("ICT 103", "Programming Logic and Design", 3, "None", "DER"),
    course("ICT 104", "Ethics for Computing and Engineering", 3, "None", "DER"),
]
check("IS Y1S1", is_semesters["Year 1 Semester 1"], 18)

is_semesters["Year 1 Semester 2"] = [
    course("GEL 102", "Use of English 102", 3, "GEL 101", "GER"),
    course("SCI 101", "Introduction to General Science", 3, "None", "GER"),
    course("GER 107", "Cultural Studies", 3, "None", "GER"),
    course("MTH 102", "Calculus II", 3, "MTH 101", "DER"),
    course("ICT 110", "Computer Programming I", 4, "ICT 103", "DER"),
    course("GER-ELECTIVE", "Social and Behavioral Sciences (Choose 1 Course)", 3, "None", "GER"),
]
check("IS Y1S2", is_semesters["Year 1 Semester 2"], 19)

is_semesters["Year 2 Semester 1"] = [
    course("FRE 101", "Elementary French I or any Foreign", 3, "None", "GER"),
    course("PHY 101", "Fundamentals of Physics I", 3, "None", "DER"),
    course("ICT 201", "Computer Architecture & Organization", 3, "None", "DER"),
    course("ICT 202", "Computer Programming II", 4, "ICT 110", "DER"),
    course("ICT 203", "Computer Networking I", 3, "ICT 102", "DER"),
    course("ICT 204", "Database Systems I", 4, "ICT 102", "DER"),
]
check("IS Y2S1", is_semesters["Year 2 Semester 1"], 20)

is_semesters["Year 2 Semester 2"] = [
    course("FRE 102", "Elementary French II or any Foreign", 3, "FRE 101", "GER"),
    course("GER-ELECTIVE", "Social and Behavioral Sciences (Choose 1 Course)", 3, "None", "GER"),
    course("GER-ELECTIVE", "Humanistic Tradition (Choose 1 Outside Major)", 3, "None", "GER"),
    course("ICT 210", "Data Structure & Algorithms", 4, "ICT 202", "DER"),
    course("ICT 211", "Principles of Operating System", 3, "ICT 202", "DER"),
    course("MTH 203", "Linear Algebra", 3, "None", "DER"),
]
check("IS Y2S2", is_semesters["Year 2 Semester 2"], 19)

is_semesters["Year 3 Semester 1"] = [
    course("GER-ELECTIVE", "Economics & Mgt. Tradition (Choose 1 Course)", 3, "None", "GER"),
    course("ICT 301", "Project Management", 3, "ICT 101", "DER"),
    course("MTH 301", "Probability and Statistics", 3, "MTH 102", "DER"),
    course("INS 301", "Systems Analysis & Design", 3, "ICT 102", "MAJOR"),
    course("INS 302", "Information Resource Management", 3, "ICT 102", "MAJOR"),
    course("INS 303", "Data Engineering", 3, "ICT 102", "MAJOR"),
    course("INS 304", "Systems Administration and Security", 3, "ICT 102", "MAJOR"),
]
check("IS Y3S1", is_semesters["Year 3 Semester 1"], 21)

is_semesters["Year 3 Semester 2"] = [
    course("INS 305", "Access Control Sys. & Methodology", 3, "INS 304", "MAJOR"),
    course("INS 306", "Service Centric and Cloud Computing", 3, "ICT 201", "MAJOR"),
    course("INS 307", "E-Business for Development", 3, "INS 303", "MAJOR"),
    course("INS 308", "Internetworking & TCP/IP", 3, "ICT 203", "MAJOR"),
    course("INS 309", "Advanced Application Development", 3, "ICT 202", "MAJOR"),
    course("ICT 315", "Research Methodology in IT", 3, "None", "MAJOR"),
]
check("IS Y3S2", is_semesters["Year 3 Semester 2"], 18)

is_semesters["Year 4 Semester 1"] = [
    course("INS 401", "Business Continuity & Recovery Planning", 3, "INS 306", "MAJOR"),
    course("INS 402", "Cross Platform & Enterprise Integration", 3, "INS 304", "MAJOR"),
    course("INS 403", "Computer Forensics", 3, "INS 304", "MAJOR"),
    course("INS 404", "Security Script Programming", 3, "INS 304", "MAJOR"),
    course("INS 405", "Process Modelling & Solution Blueprint", 3, "ICT 301", "MAJOR"),
    course("ICT 406", "Seminar", 3, "ICT 315", "MAJOR"),
]
check("IS Y4S1", is_semesters["Year 4 Semester 1"], 18)

is_semesters["Year 4 Semester 2"] = [
    course("INS 407", "Information Security & Auditing", 3, "INS 304", "MAJOR"),
    course("ICT 408", "Project", 6, "ICT 406", "MAJOR"),
    course("400-LEVEL-ELECTIVE", "400 Level Elective", 3, "None", "ELECTIVE"),
    course("400-LEVEL-ELECTIVE", "400 Level Elective", 3, "None", "ELECTIVE"),
]
check("IS Y4S2", is_semesters["Year 4 Semester 2"], 15)

# Cross-check against the PDF's own printed summary: "Study plan total: 148 credits, 47 courses"
_is_all_courses = [c for sem in is_semesters.values() for c in sem]
assert sum(c["credits"] for c in _is_all_courses) == 148, "IS total credits mismatch vs source PDF"
assert len(_is_all_courses) == 47, "IS course count mismatch vs source PDF"

is_electives = [
    course("INS 409", "Entrepreneurship (Strongly recommended)", 3, None, "ELECTIVE"),
    course("INS 410", "Foundations of Cryptography", 3, None, "ELECTIVE"),
    course("INS 411", "Management Process and Organization Behavior", 3, None, "ELECTIVE"),
    course("INS 412", "Introduction to Cyber Security", 3, None, "ELECTIVE"),
    course("INS 413", "Internet and Web Technologies", 3, None, "ELECTIVE"),
    course("INS 414", "Applications in Information Security and Assurance", 3, None, "ELECTIVE"),
    course("INS 415", "Policy and Administration in Information Security and Assurance", 3, None, "ELECTIVE"),
    course("INS 416", "UNIX System Administration & Security", 3, None, "ELECTIVE"),
    course("INS 417", "Human Computer Interaction", 3, None, "ELECTIVE"),
    course("INS 418", "Geographic Information Systems", 3, None, "ELECTIVE"),
]

is_ger_breakdown = [
    {"competency": "Writing Competence", "requirement": "GEL 101: Use of English 1 and GEL 102: Use of English 2", "hours": "6 semester hours"},
    {"competency": "Mathematics competence", "requirement": "MTH 103: Basic Mathematics or MTH 101: Calculus 1 (for all science students)", "hours": "3 semester hours"},
    {"competency": "Information Technology Competence", "requirement": "CPS 111: Introduction to Information Communication Technology (ICT)", "hours": "3 semester hours"},
    {"competency": "Foreign Language Competence", "requirement": "Any language offered except English: French 1&2, Arabic 1&2, or Spanish 1&2 (majors/minors in French or Islamic Studies take FRE/ARB 103 & 104 instead)", "hours": "6 semester hours"},
    {"competency": "Humanistic Tradition", "requirement": "GER 107: Cultural Studies plus one other course outside the student's major area (History, Literature, Philosophy, Law, or Religious Studies)", "hours": "6 semester hours"},
    {"competency": "Social and Behavioural Sciences", "requirement": "Two courses from: Psychology, Anthropology, Geography, Political Science, Sociology, Development and Gender Issues", "hours": "6 semester hours"},
    {"competency": "General Science Competence", "requirement": "SCI 101: Introduction to General Science", "hours": "3 semester hours"},
    {"competency": "Economics and Management Tradition", "requirement": "MGT 100: Introduction to Management or ECO 200: Economics of Development", "hours": "3 semester hours"},
]

information_systems = {
    "full_name": "BSc (Hons) Information Systems",
    "department": "Department of Information Systems",
    "school": "School of Information Technology and Communication (SITC)",
    "total_credit_hours": 148,
    "source": "BSc (Hons) Information Systems Study Plan.pdf, provided by student, accessed 2026",
    "semesters": is_semesters,
    "electives": is_electives,
    "electives_note": "Choose two 400-level electives in Year 4 Semester II. INS 409 Entrepreneurship is marked as strongly recommended.",
    "ger_breakdown": is_ger_breakdown,
    "minor_offered": False,
}

catalog = {
    "computer_science": computer_science,
    "telecommunication": telecommunication,
    "information_systems": information_systems,
}

import os
_output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "programs.json")
with open(_output_path, "w", encoding="utf-8") as f:
    json.dump(catalog, f, indent=2)

print("All credit-hour and course-count checks passed. Wrote data/programs.json")
print(f"CS semesters: {len(cs_semesters)}, CS electives: {len(cs_electives)}")
print(f"TEL semesters: {len(tel_semesters)}, TEL electives: {len(tel_electives)}")
print(f"IS semesters: {len(is_semesters)}, IS electives: {len(is_electives)}, "
      f"IS total courses: {len(_is_all_courses)}, IS total credits: {sum(c['credits'] for c in _is_all_courses)}")
