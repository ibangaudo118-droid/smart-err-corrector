import ast
from pathlib import Path
import shutil
import sys
import traceback
from types import TracebackType
from typing import Callable

from .proposer import FixProposal, _format_context, propose_fix

HookFunc = Callable[
    [type[BaseException], BaseException, TracebackType | None],
    None,
]


def _is_noop_change(before_text: str, after_text: str) -> bool:
    return before_text.strip() == after_text.strip()


def _apply_proposal(proposal: FixProposal) -> tuple[bool, str]:
    path = proposal.file_path
    if not path.exists():
        return False, f"File not found: {path}"

    original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    original_text = "".join(original_lines)
    start_idx = max(0, proposal.start_line - 1)
    end_idx = min(len(original_lines), proposal.end_line)

    candidate_lines = (
        original_lines[:start_idx]
        + proposal.replacement_lines
        + original_lines[end_idx:]
    )
    candidate_text = "".join(candidate_lines)

    if candidate_text == original_text or _is_noop_change(
        "".join(original_lines[start_idx:end_idx]),
        "".join(proposal.replacement_lines),
    ):
        return False, "No code change proposed; file left unchanged."

    try:
        ast.parse(candidate_text, filename=str(path))
    except SyntaxError as exc:
        return False, f"Syntax check failed ({exc}); file left unchanged."

    backup = Path(f"{path}.bak")
    shutil.copy2(path, backup)
    path.write_text(candidate_text, encoding="utf-8")
    return True, f"Applied fix to {path} (backup saved at {backup})."


class ErrorHook:
    def __init__(self) -> None:
        self._previous_hook: HookFunc = sys.excepthook
        self._active = False

    def install(self) -> None:
        if self._active:
            return
        self._previous_hook = sys.excepthook
        sys.excepthook = self._handle_exception
        self._active = True

    def uninstall(self) -> None:
        if not self._active:
            return
        sys.excepthook = self._previous_hook
        self._active = False

    def _handle_exception(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            self._previous_hook(exc_type, exc_value, exc_tb)
            return

        self._previous_hook(exc_type, exc_value, exc_tb)

        frames = traceback.extract_tb(exc_tb) if exc_tb else []
        if not frames:
            return

        last_frame = frames[-1]
        target = Path(last_frame.filename)
        line_no = last_frame.lineno or 1
        if not target.exists():
            return

        lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
        proposal = propose_fix(exc_type, exc_value, target, line_no, lines)

        start_idx = max(0, proposal.start_line - 1)
        end_idx = min(len(lines), proposal.end_line)
        before_text = "".join(lines[start_idx:end_idx]).rstrip("\r\n")
        after_text = "".join(proposal.replacement_lines).rstrip("\r\n")

        print("\n=== SMART ERROR CORRECTOR ===")
        print(f"File:      {target}:{line_no}")
        print(f"Diagnosis: {proposal.diagnosis}\n")
        print(_format_context(lines, line_no))

        if _is_noop_change(before_text, after_text):
            print("\nNo actionable replacement proposed; file left unchanged.")
            print("=============================")
            return

        print("\nProposed replacement:")
        print("--- BEFORE ---")
        print(before_text)
        print("+++ AFTER  +++")
        print(after_text)
        print("=============================")

        if not sys.stdin.isatty():
            print("Non-interactive session; keeping original code.")
            return

        while True:
            answer = input("Apply fix? [a]pply / [k]eep original: ").strip().lower()
            if answer in ("a", "apply"):
                _, msg = _apply_proposal(proposal)
                print(msg)
                break
            if answer in ("k", "keep", ""):
                print("Kept original code.")
                break
            print("Type 'a' to apply or 'k' to keep original.")
