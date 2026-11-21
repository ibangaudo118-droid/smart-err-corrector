# smart-err-corrector

A lightweight Python runtime exception hook that diagnoses uncaught errors with surrounding source context, proposes targeted fixes via deterministic rules or a Groq LLM fallback, blocks no-op edits, and validates syntax before touching any file.

## Features

- **Context-rich runtime hook (`ErrorHook`):** Wraps `sys.excepthook` while preserving your existing exception hook, printing file/line location, a diagnosis, and numbered surrounding lines.
- **Deterministic rules first:** Handles common runtime exceptions immediately with zero network latency (`ZeroDivisionError`, `KeyError`, `IndexError`).
- **Groq fallback (`openai/gpt-oss-120b` by default):** Queries Groq's chat completions API when `GROQ_API_KEY` is set and no deterministic rule matches, supporting custom models via `GROQ_MODEL`.
- **No-op & safety guards:** Rejects suggestions that echo the original line or leave whitespace-only changes, skips interactive prompts in non-TTY sessions, handles `EOFError` / `KeyboardInterrupt` cleanly, validates syntax with `ast.parse`, and writes a `.bak` backup before applying edits.

## Installation

Clone the repository and install in editable mode (or run with `PYTHONPATH=src`):

\`\`\`bash
git clone https://github.com/ibangaudo118-droid/smart-err-corrector.git
cd smart-err-corrector
pip install -e .
\`\`\`

Optional environment variables for LLM fallback:

\`\`\`bash
export GROQ_API_KEY="your_groq_api_key"
export GROQ_MODEL="openai/gpt-oss-120b"  # optional; defaults to openai/gpt-oss-120b
\`\`\`

## Usage Example

Install the hook at your script entry point:

\`\`\`python
from smart_err_corrector.hook import ErrorHook

hook = ErrorHook()
hook.install()


def divide_values(a: int, b: int) -> float:
    return a / b


if __name__ == "__main__":
    divide_values(10, 0)
\`\`\`

When an uncaught exception occurs in an interactive TTY:

1. The original traceback is emitted as usual.
2. `smart-err-corrector` prints the diagnosis, surrounding code context, and a before/after diff preview.
3. If the proposal changes code and passes `ast.parse`, you can choose `[a]pply` (writes `<file>.bak` and updates the file) or `[k]eep` (leaves the file untouched).

## How Deterministic Rules vs. Groq Fallback Work

`propose_fix()` evaluates exceptions in two stages:

| Stage | When It Runs | Behavior & Trade-offs |
| :--- | :--- | :--- |
| **Deterministic Rules** | `ZeroDivisionError`, `KeyError`, `IndexError` | Instant, offline, and predictable. Generates a `try/except` guard for `ZeroDivisionError` or `# TODO` safety reminders paired with the original line for `KeyError` and `IndexError`. |
| **Groq Fallback** | Other exception types when `GROQ_API_KEY` is set | Sends a bounded snippet around the failing line to `GROQ_CHAT_URL` using `GROQ_MODEL` (`openai/gpt-oss-120b` by default), strips optional code fences, validates response types, rejects empty or unchanged replacements, and returns `source="groq:<model>"`. |
| **Safe Fallback** | No API key, non-rule exception, or API/network/parse failure | Degrades gracefully without crashing the hook—returning an out-of-range guard if `line_no` is invalid, or leaving the line unchanged (`source="fallback"`). |

## Running Tests

Run the unit test suites from the repository root:

\`\`\`bash
PYTHONPATH=src python tests/test_proposer.py -v
PYTHONPATH=src python tests/test_noop.py -v
PYTHONPATH=src python tests/test_edge_cases.py -v
\`\`\`

Current test suite status (**14/14 passing** across all three test modules):

\`\`\`text
Ran 6 tests ... OK   # tests/test_proposer.py
Ran 3 tests ... OK   # tests/test_noop.py
Ran 5 tests ... OK   # tests/test_edge_cases.py
\`\`\`

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

Copyright (c) 2026 David Udoh
