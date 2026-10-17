"""
Coding Tutor without an AI model.

What it can do, by reading the code and never running it:
  * Python: report syntax errors with the offending line, outline the
    structure, explain each statement in plain words, flag common mistakes,
    and draft a test skeleton and docstrings.
  * Any language: explain common error messages (a built-in glossary).

What it cannot do: judge whether an algorithm is correct, fix logic errors,
or explain code in other languages. Nocturna uses no AI model, so these are out of scope.

Nothing the student pastes is executed. It is parsed with Python's `ast`
module, which reads code as text and never runs it.
"""

import ast
import builtins
import re

MAX_CODE_CHARS = 12000

_PY_ERRORS = {
    "SyntaxError": ("Python couldn't understand the code's structure.",
                    ["A missing colon after if/for/while/def/class", "An unclosed bracket, quote or parenthesis on this line or the one above",
                     "A misspelt keyword, or = used where == was meant"]),
    "IndentationError": ("The spaces at the start of a line don't match the block they belong to.",
                         ["Mixing tabs and spaces", "A block (after a colon) with nothing indented under it", "A line indented by a different amount than its neighbours"]),
    "NameError": ("A name was used before it was created, or it is misspelt.",
                  ["A typo in a variable or function name", "Using a variable before assigning it", "Forgetting to import a module"]),
    "UnboundLocalError": ("A variable inside a function is used before it receives a value, often because it is also assigned later in that function.",
                          ["Assigning to a global variable inside a function without declaring it global", "A value assigned only inside an if branch"]),
    "TypeError": ("An operation was used on a value of the wrong type.",
                  ["Adding text and a number (convert one of them with int() or str())", "Calling something that isn't a function",
                   "Passing the wrong number of arguments to a function", "Indexing something that isn't a list, string or dict"]),
    "ValueError": ("The value has the right type but an unacceptable content.",
                   ["int('abc') on text that isn't a number", "Unpacking a different number of items than expected", "An empty sequence passed to max() or min()"]),
    "IndexError": ("A list or string position doesn't exist.",
                   ["Looping one step too far (remember indexes start at 0)", "Using an index on an empty list", "len(x) used as an index instead of len(x) - 1"]),
    "KeyError": ("A dictionary doesn't contain that key.",
                 ["A typo in the key, or different capitalisation", "Reading a key before it has been added", "Use .get(key) if the key may be missing"]),
    "AttributeError": ("The object doesn't have that attribute or method.",
                       ["A typo in the method name", "A variable that is None where you expected an object", "Calling a list method on a string, or the other way round"]),
    "ZeroDivisionError": ("The code divided by zero.", ["A divisor that is 0 for some input", "An empty list's length used as the divisor"]),
    "ModuleNotFoundError": ("Python can't find the module you imported.",
                            ["The package isn't installed in this environment (pip install it)", "A typo in the module name", "A file in your own project named the same as a library"]),
    "ImportError": ("An import failed.", ["The name doesn't exist in that module", "A circular import between two of your files"]),
    "FileNotFoundError": ("The file or folder doesn't exist at that path.",
                          ["A wrong path, or running from a different folder than you expect", "A typo in the file name or extension"]),
    "RecursionError": ("A function kept calling itself without stopping.",
                       ["A missing or unreachable base case", "A recursive call that doesn't move closer to the base case"]),
    "StopIteration": ("An iterator ran out of items.", ["Calling next() on an exhausted iterator"]),
    "OverflowError": ("A number became too large for that operation.", ["A calculation growing without limit"]),
}

_OTHER_ERRORS = [
    (r"Cannot read propert(?:y|ies) of (?:undefined|null)", "JavaScript: you used a property of something that is undefined or null.",
     ["A variable that hasn't been given a value yet", "An object or array element that doesn't exist", "Data from a request that hasn't arrived yet"]),
    (r"(\w+) is not defined", "The name was used but never declared in this scope.", ["A typo in the name", "A variable declared inside a block or function and used outside it", "A missing import or script"]),
    (r"is not a function", "Something that isn't a function was called like one.", ["A typo in the method name", "A variable overwritten with a non-function value"]),
    (r"NullPointerException", "Java: a method or field was used on a reference that is null.", ["An object never created with new", "A method that returned null", "An uninitialised field"]),
    (r"ArrayIndexOutOfBounds|IndexOutOfBounds", "Java: an array or list position doesn't exist.", ["A loop that goes one step too far (arrays start at 0)", "An empty array or list"]),
    (r"cannot find symbol", "Java: the compiler doesn't know that variable, method or class.", ["A typo or wrong capitalisation", "A missing import", "A variable declared in a different scope"]),
    (r"incompatible types", "Java: a value of one type was assigned to a variable of another type.", ["Assigning a double to an int", "Assigning a String to a number"]),
    (r"';' expected|expected ';'", "A statement is missing its semicolon, or the line above is unfinished.", ["A missing semicolon", "An unclosed bracket on the previous line"]),
    (r"[Ss]egmentation fault", "C/C++: the program touched memory it doesn't own.", ["A pointer that is null or uninitialised", "An array index out of range", "Using memory after freeing it"]),
    (r"undefined reference to", "C/C++ linker: a function was declared but its code wasn't found.", ["A source file missing from the build", "A library not linked", "A function declared but never defined"]),
    (r"Unexpected token", "JavaScript/JSON: the parser met a symbol it didn't expect.", ["A missing comma, bracket or quote", "A trailing comma in JSON"]),
]


def explain_error(error_text: str):
    if not error_text.strip():
        return None
    line_no = None
    m = re.findall(r'line (\d+)', error_text)
    if m:
        line_no = int(m[-1])
    kind = None
    for m in re.finditer(r"(\w+(?:Error|Exception))\s*(?::\s*(.*))?", error_text):
        kind, msg = m.group(1), (m.group(2) or "").strip()
    if kind in _PY_ERRORS:
        what, causes = _PY_ERRORS[kind]
        return {"kind": kind, "message": msg, "line": line_no, "what": what, "causes": causes}
    for pattern, what, causes in _OTHER_ERRORS:
        if re.search(pattern, error_text):
            return {"kind": re.search(pattern, error_text).group(0), "message": "", "line": line_no, "what": what, "causes": causes}
    if kind:
        return {"kind": kind, "message": msg, "line": line_no,
                "what": "I don't have a built-in explanation for this error type.", "causes": ["Search the exact error message together with the language name", "Read the line number it points to, and the line above it"]}
    return None


# ----------------------------------------------------------- Python only

def _describe(node):
    t = type(node).__name__
    src = lambda n: ast.unparse(n)[:60]
    try:
        if isinstance(node, ast.Assign):
            return f"Stores {src(node.value)} in {', '.join(src(x) for x in node.targets)}."
        if isinstance(node, ast.AugAssign):
            return f"Updates {src(node.target)} by applying {type(node.op).__name__.lower()} with {src(node.value)}."
        if isinstance(node, ast.AnnAssign):
            return f"Declares {src(node.target)} with a type annotation."
        if isinstance(node, ast.For):
            return f"Repeats the block below once for each item {src(node.target)} taken from {src(node.iter)}."
        if isinstance(node, ast.While):
            return f"Repeats the block below as long as {src(node.test)} is true."
        if isinstance(node, ast.If):
            return f"Runs the block below only if {src(node.test)} is true."
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return f"Defines a function named {node.name} that takes ({', '.join(a.arg for a in node.args.args)})."
        if isinstance(node, ast.ClassDef):
            return f"Defines a class named {node.name}."
        if isinstance(node, ast.Return):
            return f"Sends {src(node.value) if node.value else 'nothing'} back to whoever called the function."
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return f"Calls {src(node.value.func)}."
        if isinstance(node, ast.Import):
            return f"Loads the module(s): {', '.join(a.name for a in node.names)}."
        if isinstance(node, ast.ImportFrom):
            return f"Loads {', '.join(a.name for a in node.names)} from {node.module}."
        if isinstance(node, ast.Try):
            return "Tries the block below; if an error occurs, the except block handles it instead of crashing."
        if isinstance(node, ast.With):
            return f"Opens {', '.join(src(i.context_expr) for i in node.items)} and closes it automatically afterwards."
        if isinstance(node, ast.Break):
            return "Leaves the loop immediately."
        if isinstance(node, ast.Continue):
            return "Skips to the next round of the loop."
        if isinstance(node, ast.Raise):
            return "Raises an error on purpose."
        if isinstance(node, ast.Pass):
            return "Does nothing (a placeholder)."
    except Exception:
        pass
    return None


def _lint(tree):
    notes = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            notes.append((line, "A bare `except:` hides every kind of error, including typos. Catch the specific error you expect."))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.args.defaults + [x for x in node.args.kw_defaults if x]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    notes.append((line, f"`{node.name}` has a mutable default argument. The same list/dict is shared between calls; use None and create it inside."))
            assigned, loaded = {}, set()
            for n in ast.walk(node):
                if isinstance(n, ast.Name):
                    if isinstance(n.ctx, ast.Store):
                        assigned.setdefault(n.id, n.lineno)
                    else:
                        loaded.add(n.id)
            for name, ln in assigned.items():
                if name not in loaded and not name.startswith("_"):
                    notes.append((ln, f"`{name}` is assigned in `{node.name}` but never used."))
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comp, ast.Constant) and comp.value is None:
                    notes.append((line, "Compare with None using `is None` / `is not None`, not `==`."))
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comp, ast.Constant) and isinstance(comp.value, (int, str)) and comp.value is not None:
                    notes.append((line, "`is` compares identity, not value. Use `==` for numbers and strings."))
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) and node.test.value is True:
            if not any(isinstance(n, (ast.Break, ast.Return)) for n in ast.walk(node)):
                notes.append((line, "`while True` with no `break` or `return` inside never ends."))
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in dir(builtins) and not t.id.startswith("_"):
                    notes.append((line, f"`{t.id}` is the name of a built-in. Assigning to it hides the built-in later in your code."))
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Name):
            for n in ast.walk(node):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("remove", "append", "pop", "insert") \
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == node.iter.id:
                    notes.append((line, f"`{node.iter.id}` is changed while the loop is going through it, which can skip items."))
                    break
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) \
                and isinstance(node.right, ast.Constant) and node.right.value == 0:
            notes.append((line, "This divides by the constant 0."))
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[(a.asname or a.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported[a.asname or a.name] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    for name, ln in imported.items():
        if name not in used and name != "*":
            notes.append((ln, f"`{name}` is imported but never used."))
    seen, out = set(), []
    for ln, msg in sorted(notes, key=lambda x: (x[0] or 0, x[1])):
        if (ln, msg) not in seen:
            seen.add((ln, msg))
            out.append({"line": ln, "message": msg})
    return out[:15]


def _python(code: str):
    lines = code.splitlines()
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        bad = lines[e.lineno - 1] if e.lineno and e.lineno <= len(lines) else ""
        hint = None
        if bad.rstrip().endswith(("if", "else", "elif", "for", "while", "def", "class")) or re.match(r"\s*(if|elif|else|for|while|def|class|try|except|finally|with)\b[^:]*$", bad):
            hint = "This line starts a block but doesn't end with a colon (:)."
        return {"syntax_error": {"line": e.lineno, "column": e.offset, "message": e.msg, "source": bad.rstrip(), "hint": hint}}

    out = {"outline": [], "line_by_line": [], "issues": _lint(tree), "tests": [], "docstrings": []}
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls_self = any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == n.name for c in ast.walk(n))
            out["outline"].append(f"Function `{n.name}({', '.join(a.arg for a in n.args.args)})`" + (" (calls itself: recursion)" if calls_self else ""))
        elif isinstance(n, ast.ClassDef):
            out["outline"].append(f"Class `{n.name}`")
    loops = sum(isinstance(n, (ast.For, ast.While)) for n in ast.walk(tree))
    if loops:
        out["outline"].append(f"{loops} loop(s)")
    for n in sorted((x for x in ast.walk(tree) if isinstance(x, ast.stmt) and hasattr(x, "lineno")), key=lambda x: x.lineno):
        d = _describe(n)
        if d and len(out["line_by_line"]) < 60:
            out["line_by_line"].append({"line": n.lineno, "code": lines[n.lineno - 1].strip()[:90], "explanation": d})
    for f in funcs[:8]:
        args = ", ".join("..." for _ in f.args.args if _.arg not in ("self", "cls"))
        out["tests"].append(f"    def test_{f.name}(self):\n        # TODO: choose inputs and the result you expect\n        self.assertEqual({f.name}({args}), ...)")
        if ast.get_docstring(f) is None:
            params = [a.arg for a in f.args.args if a.arg not in ("self", "cls")]
            doc = '"""One-line summary of what the function does.\n' + "".join(f"\n    {p}: what it means" for p in params) + ("\n\n    Returns: what comes back" if any(isinstance(x, ast.Return) and x.value for x in ast.walk(f)) else "") + '\n    """'
            out["docstrings"].append(f"{f.name}:\n{doc}")
    return out


def analyze(code: str, language: str = "python", error_text: str = ""):
    code, error_text = (code or "")[:MAX_CODE_CHARS], (error_text or "")[:4000]
    result = {"language": language, "error": explain_error(error_text), "python": None, "notes": []}
    if code.strip() and (language or "").lower() in ("python", "py", "auto", ""):
        result["python"] = _python(code)
    elif code.strip():
        result["notes"].append(f"I can only read Python code. For {language}, paste the error message and I can explain it.")
    if not code.strip() and not error_text.strip():
        result["notes"].append("Paste some code, an error message, or both.")
    result["notes"].append("Nothing was run: your code was only read. It cannot judge whether the logic is correct.")
    return result
