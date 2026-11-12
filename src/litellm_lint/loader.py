"""YAML loading with line/column positions, and parse errors that never echo file content."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError
from ruamel.yaml.parser import ParserError
from ruamel.yaml.scanner import ScannerError

from .diagnostics import Diagnostic, LintUsageError, Severity
from .i18n import msg

Pos = tuple[int | None, int | None]


class YamlProblem(Exception):
    """The file is not usable YAML. ``diagnostic`` carries only line:col and a safe description."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


MAX_EXPANDED_NODES = 500_000  # nodes after expanding every alias; real configs use a few thousand
MAX_DEPTH = 100  # nesting levels; real configs use fewer than 10
_DONE = object()


def _problem(message: str, path: Path | str) -> YamlProblem:
    return YamlProblem(Diagnostic("LL900", Severity.ERROR, message, str(path), 1, 1))


def check_complexity(root: Any, path: Path | str) -> None:
    """Refuse documents the rules could not walk in reasonable time.

    ruamel keeps an alias as a reference to the same object, but every rule walk expands it
    again, so a few hundred bytes of nested aliases (a "billion laughs" file) mean billions of
    steps. Count the expanded size once (memoised per shared node) and stop at the limits.
    Raises ``YamlProblem`` (LL900). Self-referencing aliases count as one node.
    """
    too_deep = msg("yaml_too_deep", limit=MAX_DEPTH)
    too_big = msg("yaml_too_big", limit=MAX_EXPANDED_NODES)
    memo: dict[int, tuple[int, int]] = {}  # id(node) -> (expanded size, height)
    on_path: set[int] = set()
    # frame: [node, children iterator, size so far, height so far]
    stack: list[list[Any]] = []

    def open_frame(node: Any) -> None:
        on_path.add(id(node))
        kids = iter(node.values() if isinstance(node, dict) else node)
        stack.append([node, kids, 0, 0])

    if isinstance(root, (dict, list)):
        open_frame(root)
    while stack:
        frame = stack[-1]
        if len(stack) > MAX_DEPTH:
            raise _problem(too_deep, path)
        child = next(frame[1], _DONE)
        if child is _DONE:
            stack.pop()
            on_path.discard(id(frame[0]))
            size, height = frame[2] + 1, frame[3] + 1
            memo[id(frame[0])] = (size, height)
            if stack:
                stack[-1][2] += size
                stack[-1][3] = max(stack[-1][3], height)
                if stack[-1][2] > MAX_EXPANDED_NODES:
                    raise _problem(too_big, path)
            elif size > MAX_EXPANDED_NODES:
                raise _problem(too_big, path)
            continue
        if not isinstance(child, (dict, list)):
            frame[2] += 1
        elif id(child) in on_path:
            frame[2] += 1  # self-reference: do not follow
        elif id(child) in memo:
            size, height = memo[id(child)]
            frame[2] += size
            if len(stack) + height > MAX_DEPTH:
                raise _problem(too_deep, path)
            if frame[2] > MAX_EXPANDED_NODES:
                raise _problem(too_big, path)
        else:
            open_frame(child)


def parse_yaml_file(path: Path, *, label: str | None = None) -> Any:
    """Read and parse one YAML file; any failure is a ``YamlProblem`` or ``LintUsageError``.

    The returned value is not yet checked to be a mapping.
    """
    shown = label or str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise LintUsageError(msg("config_not_found", path=path)) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise LintUsageError(msg("config_unreadable", path=path, name=type(exc).__name__)) from None
    yaml = YAML(typ="rt")
    try:
        data = yaml.load(text)
    except RecursionError:
        raise _problem(msg("yaml_parser_gave_up", limit=MAX_DEPTH), shown) from None
    except MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        line = mark.line + 1 if mark is not None else None
        col = mark.column + 1 if mark is not None else None
        # Only scanner/parser problems have fixed wording. Other errors (duplicate keys,
        # constructor errors) can quote values, so they get a generic message.
        if isinstance(exc, (ScannerError, ParserError)) and exc.problem:
            what = _fixed_problem(exc.problem)
        elif "duplicate" in type(exc).__name__.lower():
            what = msg("yaml_duplicate_key")
        else:
            what = msg("yaml_invalid_construct")
        raise YamlProblem(
            Diagnostic("LL900", Severity.ERROR, msg("yaml_cannot_parse", what=what), shown, line, col)
        ) from None
    check_complexity(data, shown)
    return data


def load_config(path: Path, *, label: str | None = None) -> Any:
    """Read ``path`` into ruamel round-trip containers (they remember line/column)."""
    data = parse_yaml_file(path, label=label)
    if not isinstance(data, dict):
        raise _problem(msg("root_not_mapping"), label or str(path))
    return data


def _fixed_problem(problem: str) -> str:
    """Keep ruamel's wording but drop anything quoted from the file."""
    out = []
    quote = ""
    for ch in problem:
        if quote:
            if ch == quote:
                quote = ""
                out.append("..." + ch)
            continue
        if ch in "'\"" and len(problem) > 0:
            quote = ch
            out.append(ch)
            continue
        out.append(ch)
    return "".join(out).strip()


def key_pos(mapping: Any, key: Any) -> Pos:
    """Position (1-based line, col) of ``key`` in a mapping."""
    try:
        line, col = mapping.lc.key(key)
        return line + 1, col + 1
    except (AttributeError, KeyError, TypeError):
        return None, None


def value_pos(mapping: Any, key: Any) -> Pos:
    try:
        line, col = mapping.lc.value(key)
        return line + 1, col + 1
    except (AttributeError, KeyError, TypeError):
        return None, None


def item_pos(seq: Any, index: int) -> Pos:
    try:
        line, col = seq.lc.item(index)
        return line + 1, col + 1
    except (AttributeError, KeyError, IndexError, TypeError):
        return None, None


def to_plain(node: Any) -> Any:
    """Convert ruamel containers to plain dict/list/scalars (for hashing and JSON Schema)."""
    if isinstance(node, dict):
        return {str(k): to_plain(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [to_plain(v) for v in node]
    if isinstance(node, bool) or node is None:
        return node
    if isinstance(node, int):
        return int(node)
    if isinstance(node, float):
        return float(node)
    if isinstance(node, str):
        return str(node)
    return str(node)  # dates and other YAML scalars -> text


def iter_scalars(node: Any, path: str = "") -> Iterator[tuple[str, str, Any, Pos]]:
    """Yield ``(key_path, last_key, scalar_value, (line, col))`` for every scalar in the tree.

    ``last_key`` is the nearest mapping key ("" for list items directly under the root).
    """
    if isinstance(node, dict):
        for key, value in node.items():
            sub = f"{path}.{key}" if path else str(key)
            if isinstance(value, (dict, list)):
                yield from iter_scalars(value, sub)
            else:
                yield sub, str(key), value, value_pos(node, key)
    elif isinstance(node, list):
        last = path.rsplit(".", 1)[-1].split("[", 1)[0]
        for i, value in enumerate(node):
            sub = f"{path}[{i}]"
            if isinstance(value, (dict, list)):
                yield from iter_scalars(value, sub)
            else:
                yield sub, last, value, item_pos(node, i)
