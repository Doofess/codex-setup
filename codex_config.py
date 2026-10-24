"""Merges the keys we own into Codex's config.toml and leaves every other byte alone.

Usage: python -I codex_config.py merge <template> <config.toml>
       python -I codex_config.py check <template> <config.toml>

The Codex desktop app writes the same file, so this is a line-based editor, not a TOML writer. It
replaces the lines of each owned key, or adds the key to its table (root keys go above the first
table header), and keeps comments, ordering, line endings, the BOM and the final-newline state.
It stops with exit 2 and leaves the file untouched when an owned key cannot be set safely: the file
is not valid TOML, or a parent table is defined as a dotted root key or an inline table.

check prints one JSON line with a row per owned key and exits 1 when any row is not ok.
"""
import json
import os
import re
import sys
import time
import tomllib

BOM = "﻿"
_SEGMENT = r"""(?:[A-Za-z0-9_-]+|"[^"]*"|'[^']*')"""
_KEY = rf"{_SEGMENT}(?:\s*\.\s*{_SEGMENT})*"
KEY_LINE = re.compile(rf"^\s*({_KEY})\s*=")
HEADER_LINE = re.compile(rf"^\s*(\[\[?)\s*({_KEY})\s*\]\]?\s*(?:#.*)?$")
SEGMENT = re.compile(_SEGMENT)
SWAP_TRIES = 50
SWAP_WAIT = 0.1


class MergeError(Exception):
    """The config cannot be merged safely; the message says why."""


def toml_value(v):
    """The TOML text of a str, bool, int or list of those."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    raise TypeError(f"cannot write {type(v).__name__} as TOML")


def _show(v):
    try:
        return toml_value(v)
    except TypeError:
        return repr(v)


def owned(template_text):
    """Maps table name ("" for the root) to {key: value} for every non-table value in the template."""
    found = {}

    def walk(name, table):
        keys = {k: v for k, v in table.items() if not isinstance(v, dict)}
        if keys:
            found[name] = keys
        for k, v in table.items():
            if isinstance(v, dict):
                walk(f"{name}.{k}" if name else k, v)

    walk("", tomllib.loads(template_text))
    return found


def _segments(key_text):
    return [s[1:-1] if s[0] in "\"'" else s for s in SEGMENT.findall(key_text)]


def _consume(line, ml, depth):
    """Reads one line of a value. ml is the open multi-line string delimiter or None; depth counts
    open brackets. Returns the new (ml, depth). Brackets in strings and comments do not count."""
    i, n = 0, len(line)
    while i < n:
        if ml:
            if ml == '"""' and line[i] == "\\":
                i += 2
            elif line.startswith(ml, i):
                ml, i = None, i + 3
            else:
                i += 1
            continue
        c = line[i]
        if c == "#":
            break
        if line.startswith('"""', i) or line.startswith("'''", i):
            ml, i = line[i : i + 3], i + 3
        elif c in "\"'":
            i += 1
            while i < n and line[i] != c:
                i += 2 if c == '"' and line[i] == "\\" else 1
            i += 1
        else:
            if c in "[{":
                depth += 1
            elif c in "]}":
                depth -= 1
            i += 1
    return ml, depth


def _scan(lines):
    """Splits lines into statements: header lines and key lines (a value may span lines).
    Returns dicts with kind ("header" or "kv"), start, end (inclusive), the table path the statement
    sits in (kv) or names (header), and the key path (kv)."""
    out = []
    table = []
    i = 0
    while i < len(lines):
        text = lines[i][0]
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
        elif stripped.startswith("["):
            m = HEADER_LINE.match(text)
            table = _segments(m.group(2)) if m else []
            out.append({"kind": "header", "start": i, "end": i, "table": table, "array": bool(m) and m.group(1) == "[["})
            i += 1
        else:
            m = KEY_LINE.match(text)
            ml, depth = None, 0
            j = i
            rest = text[m.end() :] if m else text
            while True:
                ml, depth = _consume(rest, ml, depth)
                if (not ml and depth <= 0) or j + 1 >= len(lines):
                    break
                j += 1
                rest = lines[j][0]
            out.append({"kind": "kv", "start": i, "end": j, "table": table, "key": _segments(m.group(1)) if m else []})
            i = j + 1
    return out


def _split(text):
    """Lines as [content, ending] pairs; ending is "\\r\\n", "\\n" or "" (last line without one)."""
    lines = []
    for raw in re.findall(r"[^\n]*\n|[^\n]+", text):
        if raw.endswith("\r\n"):
            lines.append([raw[:-2], "\r\n"])
        elif raw.endswith("\n"):
            lines.append([raw[:-1], "\n"])
        else:
            lines.append([raw, ""])
    return lines


def _insert_after(lines, index, content, nl):
    """Adds a line after lines[index] (-1 for the top), keeping the final-newline state."""
    ending = nl
    if index >= 0 and index == len(lines) - 1 and not lines[index][1]:
        lines[index][1] = nl
        ending = ""
    lines.insert(index + 1, [content, ending])


def _dotted(table, key):
    return f"{table}.{key}" if table else key


def _refuse_foreign_parents(stmts, owned_keys):
    """A table we own keys in must be a [header] table, not a dotted key or an inline table."""
    for table, keys in owned_keys.items():
        if not table:
            continue
        path = table.split(".")
        for s in stmts:
            if s["kind"] != "kv":
                continue
            full = s["table"] + s["key"]
            if len(s["table"]) < len(path) and full[: len(path)] == path:
                names = ", ".join(_dotted(table, k) for k in keys)
                raise MergeError(
                    f"cannot set {names}: {table} is defined by {'.'.join(full)} in the file, not as a [{table}] table"
                )


def _set_key(lines, nl, table, key, value):
    stmts = _scan(lines)
    path = table.split(".") if table else []
    header = None
    if path:
        header = next((s for s in stmts if s["kind"] == "header" and not s["array"] and s["table"] == path), None)
    if path and header is None:
        # New table: append it at the end, after a blank line.
        if lines and lines[-1][0].strip():
            _insert_after(lines, len(lines) - 1, "", nl)
        _insert_after(lines, len(lines) - 1, f"[{table}]", nl)
        _insert_after(lines, len(lines) - 1, f"{key} = {value}", nl)
        return
    first = header["end"] + 1 if header else 0
    boundary = next((s["start"] for s in stmts if s["kind"] == "header" and s["start"] >= first), len(lines))
    region = [s for s in stmts if s["kind"] == "kv" and first <= s["start"] < boundary]
    same = next((s for s in region if s["key"] == [key]), None)
    new = f"{key} = {value}"
    if same:
        ending = lines[same["end"]][1]
        lines[same["start"] : same["end"] + 1] = [[new, ending]]
    elif region:
        _insert_after(lines, region[-1]["end"], new, nl)
    elif header:
        _insert_after(lines, header["end"], new, nl)
    else:
        # Root without keys: go above the first header (and the comment lines that belong to it).
        at = boundary
        while at < len(lines) and at > 0 and lines[at - 1][0].strip().startswith("#"):
            at -= 1
        _insert_after(lines, at - 1, new, nl)
        if at < len(lines) - 1 and lines[at + 1][0].strip():
            _insert_after(lines, at, "", nl)


def _lookup(doc, table, key):
    for part in filter(None, table.split(".")):
        doc = doc.get(part) if isinstance(doc, dict) else None
        if doc is None:
            return False, None
    if isinstance(doc, dict) and key in doc:
        return True, doc[key]
    return False, None


def _same(a, b):
    return type(a) is type(b) and a == b


def merge(text, owned_keys):
    """Returns text with every owned key set. Raises MergeError and changes nothing when it cannot."""
    bom = text.startswith(BOM)
    body = text[1:] if bom else text
    try:
        tomllib.loads(body)
    except tomllib.TOMLDecodeError as e:
        raise MergeError(f"not valid TOML: {e}") from e
    lines = _split(body)
    _refuse_foreign_parents(_scan(lines), owned_keys)
    nl = next((end for _, end in lines if end), "\n")
    for table, keys in owned_keys.items():
        for key, value in keys.items():
            _set_key(lines, nl, table, key, toml_value(value))
    out = "".join(content + ending for content, ending in lines)
    if not body and out and not out.endswith("\n"):
        out += nl
    try:
        doc = tomllib.loads(out)
    except tomllib.TOMLDecodeError as e:
        raise MergeError(f"the merge would produce invalid TOML: {e}") from e
    for table, keys in owned_keys.items():
        for key, value in keys.items():
            found, actual = _lookup(doc, table, key)
            if not found or not _same(actual, value):
                raise MergeError(f"the merge would not set {_dotted(table, key)}")
    return (BOM if bom else "") + out


def check(text, owned_keys):
    """One row per owned key: its expected TOML, the file's TOML (or "missing"), and ok or FAIL."""
    try:
        doc = tomllib.loads(text[1:] if text.startswith(BOM) else text)
    except tomllib.TOMLDecodeError:
        doc = None
    rows = []
    for table, keys in owned_keys.items():
        for key, value in keys.items():
            found, actual = _lookup(doc, table, key) if doc is not None else (False, None)
            rows.append(
                {
                    "name": f"config {_dotted(table, key)}",
                    "expected": toml_value(value),
                    "actual": _show(actual) if found else "missing",
                    "status": "ok" if found and _same(actual, value) else "FAIL",
                }
            )
    return rows


def _read(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8")
    except FileNotFoundError:
        return None


def _write(path, text):
    # Write beside the target, then swap, so the desktop app never reads half a file. The swap is
    # retried while another process briefly holds the target open.
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    for attempt in range(SWAP_TRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == SWAP_TRIES - 1:
                os.remove(tmp)
                raise
            time.sleep(SWAP_WAIT)


def main(argv):
    if len(argv) != 3 or argv[0] not in ("merge", "check"):
        print("codex_config: usage: codex_config.py merge|check <template> <config.toml>", file=sys.stderr)
        return 2
    command, template, target = argv
    try:
        template_text = _read(template)
        if template_text is None:
            raise MergeError(f"template not found: {template}")
        keys = owned(template_text)
        current = _read(target)
        if command == "check":
            rows = check(current or "", keys)
            print(json.dumps({"rows": rows}))
            return 0 if all(r["status"] == "ok" for r in rows) else 1
        merged = merge(current or "", keys)
        if merged != current:
            _write(target, merged)
    except (MergeError, tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as e:
        print(f"codex_config: {e}".splitlines()[0], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
