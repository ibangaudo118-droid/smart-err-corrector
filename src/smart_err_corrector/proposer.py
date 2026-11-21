from dataclasses import dataclass
import json
import os
from pathlib import Path
import urllib.error
import urllib.request

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


@dataclass
class FixProposal:
    diagnosis: str
    file_path: Path
    start_line: int
    end_line: int
    replacement_lines: list[str]
    source: str = "rule"


def _format_context(lines: list[str], line_no: int, radius: int = 3) -> str:
    start = max(0, line_no - 1 - radius)
    end = min(len(lines), line_no + radius)
    rows: list[str] = []
    for idx in range(start, end):
        mark = ">>" if (idx + 1) == line_no else "  "
        clean = lines[idx].rstrip("\r\n")
        rows.append(f"{mark} {idx + 1:4d} | {clean}")
    return "\n".join(rows)


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _groq_fallback(
    exc_type: type[BaseException],
    exc_value: BaseException,
    file_path: Path,
    line_no: int,
    lines: list[str],
    indent: str,
    eol: str,
) -> FixProposal | None:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip() or DEFAULT_GROQ_MODEL
    start = max(0, line_no - 1 - 5)
    end = min(len(lines), line_no + 5)
    snippet = "".join(lines[start:end])

    system_prompt = (
        "You are a concise Python debugging assistant. "
        "Given an uncaught exception and surrounding code, propose a replacement "
        f"for line {line_no} using base indentation {indent!r}. "
        "Respond ONLY with valid JSON containing keys: "
        '"diagnosis" (1 short sentence) and '
        '"replacement_code" (the replacement line(s) for line '
        f"{line_no}, with no markdown fences)."
    )
    user_prompt = (
        f"Exception: {exc_type.__name__}: {exc_value}\n"
        f"File: {file_path.name}:{line_no}\n"
        f"Snippet (lines {start + 1}..{end}):\n{snippet}"
    )

    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    req = urllib.request.Request(
        GROQ_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "smart-err-corrector/0.2",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_body = resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    try:
        parsed = json.loads(raw_body)
        content = parsed["choices"][0]["message"]["content"]
        data = json.loads(_strip_fences(content))
        diagnosis = str(data.get("diagnosis") or f"{exc_type.__name__}: {exc_value}")
        raw_replacement = str(data.get("replacement_code") or "").rstrip("\r\n")
        if not raw_replacement:
            return None
        rep_lines = [
            f"{ln}{eol}" if not ln.startswith((" ", "\t")) else f"{ln}{eol}"
            for ln in raw_replacement.splitlines()
        ]
        return FixProposal(
            diagnosis=diagnosis,
            file_path=file_path,
            start_line=line_no,
            end_line=line_no,
            replacement_lines=rep_lines,
            source=f"groq:{model}",
        )
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        return None


def propose_fix(
    exc_type: type[BaseException],
    exc_value: BaseException,
    file_path: Path,
    line_no: int,
    lines: list[str],
) -> FixProposal:
    idx = max(0, min(len(lines) - 1, line_no - 1)) if lines else 0
    current = lines[idx] if lines else ""
    stripped = current.lstrip(" \t")
    indent = current[: len(current) - len(stripped)]
    eol = "\n"

    if exc_type is ZeroDivisionError:
        body_line = stripped.rstrip("\r\n")
        fallback_stmt = (
            f"{indent}    return 0  # TODO: verify fallback value{eol}"
            if body_line.startswith("return ")
            else f"{indent}    result = 0  # TODO: verify fallback value{eol}"
        )
        replacement = [
            f"{indent}try:{eol}",
            f"{indent}    {body_line}{eol}",
            f"{indent}except ZeroDivisionError:{eol}",
            fallback_stmt,
        ]
        return FixProposal(
            diagnosis=f"Division or floor-division by zero on line {line_no} ({exc_value}).",
            file_path=file_path,
            start_line=line_no,
            end_line=line_no,
            replacement_lines=replacement,
            source="rule:ZeroDivisionError",
        )

    if exc_type is KeyError:
        key_repr = str(exc_value)
        replacement = [
            f"{indent}# TODO: check key {key_repr} exists or use .get({key_repr}, default){eol}",
            current if current.endswith(eol) else current + eol,
        ]
        return FixProposal(
            diagnosis=f"Missing dictionary key {key_repr} on line {line_no}.",
            file_path=file_path,
            start_line=line_no,
            end_line=line_no,
            replacement_lines=replacement,
            source="rule:KeyError",
        )

    if exc_type is IndexError:
        replacement = [
            f"{indent}# TODO: verify sequence length before indexing on line {line_no}{eol}",
            current if current.endswith(eol) else current + eol,
        ]
        return FixProposal(
            diagnosis=f"Index out of range on line {line_no} ({exc_value}).",
            file_path=file_path,
            start_line=line_no,
            end_line=line_no,
            replacement_lines=replacement,
            source="rule:IndexError",
        )

    llm_proposal = _groq_fallback(
        exc_type=exc_type,
        exc_value=exc_value,
        file_path=file_path,
        line_no=line_no,
        lines=lines,
        indent=indent,
        eol=eol,
    )
    if llm_proposal is not None:
        return llm_proposal

    return FixProposal(
        diagnosis=f"Uncaught {exc_type.__name__}: {exc_value} on line {line_no}.",
        file_path=file_path,
        start_line=line_no,
        end_line=line_no,
        replacement_lines=[current if current.endswith(eol) else current + eol],
        source="fallback",
    )
