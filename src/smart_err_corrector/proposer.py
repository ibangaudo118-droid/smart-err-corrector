from dataclasses import dataclass
from pathlib import Path


@dataclass
class FixProposal:
    diagnosis: str
    file_path: Path
    start_line: int
    end_line: int
    replacement_lines: list[str]


def _format_context(lines: list[str], line_no: int, radius: int = 3) -> str:
    start = max(0, line_no - 1 - radius)
    end = min(len(lines), line_no + radius)
    rows: list[str] = []
    for idx in range(start, end):
        mark = ">>" if (idx + 1) == line_no else "  "
        clean = lines[idx].rstrip("\r\n")
        rows.append(f"{mark} {idx + 1:4d} | {clean}")
    return "\n".join(rows)


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
        replacement = [
            f"{indent}try:{eol}",
            f"{indent}    {body_line}{eol}",
            f"{indent}except ZeroDivisionError:{eol}",
            f"{indent}    result = 0  # TODO: verify fallback value{eol}",
        ]
        return FixProposal(
            diagnosis=f"Division or floor-division by zero on line {line_no} ({exc_value}).",
            file_path=file_path,
            start_line=line_no,
            end_line=line_no,
            replacement_lines=replacement,
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
        )

    return FixProposal(
        diagnosis=f"Uncaught {exc_type.__name__}: {exc_value} on line {line_no}.",
        file_path=file_path,
        start_line=line_no,
        end_line=line_no,
        replacement_lines=[current if current.endswith(eol) else current + eol],
    )
