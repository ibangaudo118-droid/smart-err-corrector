# Smart Error Corrector

Catch uncaught Python runtime errors in your terminal via `sys.excepthook`, inspect a diagnosis and `BEFORE` / `AFTER` replacement preview, and choose whether to apply (`[a]`) or keep (`[k]`) the original code.

## What's New in v0.2

- **Smarter `return` fallbacks on `ZeroDivisionError`:** When a failing line starts with `return `, the proposed `except ZeroDivisionError:` block returns `0` (`# TODO: verify fallback value`) instead of assigning an unused variable.
- **Rule-first, LLM-optional proposals:** Deterministic rules handle common errors first (`ZeroDivisionError`, `KeyError`, `IndexError`) with zero network calls. If no rule matches and `GROQ_API_KEY` is set, it queries the Groq chat completions API using Python's standard library (`urllib.request`) with no extra dependencies.
- **Graceful offline / unconfigured fallback:** If `GROQ_API_KEY` is unset, the API request times out, or the response is not valid JSON, it safely falls back to a diagnostic message without crashing your error handler.

## Quickstart

Install in editable mode:

pip install --no-build-isolation --no-deps -e .

Run the demo script:

python examples/demo.py

When the prompt appears in an interactive terminal:
- Type **`a`** to apply the proposed replacement.
- Type **`k`** (or press Enter) to keep your original code unchanged.

## Optional `GROQ_API_KEY` Setup

To enable LLM-assisted proposals for unmatched exceptions:

export GROQ_API_KEY="your_groq_api_key_here"

Optionally override the model (defaults to `llama-3.3-70b-versatile`):

export GROQ_MODEL="llama-3.3-70b-versatile"

## Safety Guarantees & Limitations

- **Human-in-the-loop review:** Changes are never applied silently; you must explicitly choose `[a]` in an interactive terminal (`sys.stdin.isatty()`). Non-interactive runs default to keeping the original code.
- **Automatic `.bak` backup:** Before writing any approved patch, a backup copy is saved alongside the target file as `<filename>.bak` (ignored in `.gitignore`).
- **Syntax validation gate:** Candidate replacements are parsed with `ast.parse()` before touching the target file. If syntax validation fails, the file is left untouched.
- **Scope limits:** Only uncaught exceptions reaching `sys.excepthook` are intercepted, and rule/LLM suggestions are starting points—always review logic and edge cases before committing code.
