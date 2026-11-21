import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from smart_err_corrector.hook import ErrorHook, _apply_proposal
from smart_err_corrector.proposer import FixProposal, propose_fix


class TestEdgeCaseGuards(unittest.TestCase):
    def test_propose_fix_rejects_out_of_range_line_no(self) -> None:
        proposal = propose_fix(
            ZeroDivisionError,
            ZeroDivisionError("division by zero"),
            Path("math_ops.py"),
            line_no=50,
            lines=["x = 1\n", "y = 2\n"],
        )
        self.assertEqual(proposal.replacement_lines, [])
        self.assertEqual(proposal.source, "fallback:out_of_range")

    @patch("smart_err_corrector.proposer.urllib.request.urlopen")
    def test_groq_fenced_json_and_whitespace_noop_handled(self, mock_urlopen: MagicMock) -> None:
        lines = ["def parse(v):\n", "    return int(v)\n"]

        def make_resp(content: str) -> MagicMock:
            resp = MagicMock()
            resp.read.return_value = json.dumps(
                {"choices": [{"message": {"content": content}}]}
            ).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        # Whitespace-only replacement_code is rejected
        mock_urlopen.return_value = make_resp('```json\n{"diagnosis": "bad", "replacement_code": "   \\n  "}\n```')
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False):
            p_blank = propose_fix(ValueError, ValueError("bad int"), Path("app.py"), 2, lines)
        self.assertEqual(p_blank.source, "fallback")

        # Valid fenced JSON fix succeeds
        fenced = (
            "```json\n"
            '{"diagnosis": "Invalid int literal.", "replacement_code": "    try:\\n        return int(v)\\n    except ValueError:\\n        return None"}'
            "\n```"
        )
        mock_urlopen.return_value = make_resp(fenced)
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False):
            p_ok = propose_fix(ValueError, ValueError("bad int"), Path("app.py"), 2, lines)
        self.assertEqual(p_ok.source, "groq:openai/gpt-oss-120b")
        self.assertIn("except ValueError:", "".join(p_ok.replacement_lines))

    @patch("smart_err_corrector.proposer.urllib.request.urlopen")
    def test_groq_http_429_falls_back_cleanly(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=None,
        )
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False):
            proposal = propose_fix(
                ValueError,
                ValueError("bad int"),
                Path("app.py"),
                2,
                ["def parse(v):\n", "    return int(v)\n"],
            )
        self.assertEqual(proposal.source, "fallback")
        self.assertEqual(proposal.replacement_lines, ["    return int(v)\n"])

    def test_apply_proposal_blocks_empty_replacement_and_bad_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "demo.py"
            target.write_text("x = 1\ny = 2\n", encoding="utf-8")

            ok_empty, _ = _apply_proposal(
                FixProposal("d", target, 1, 1, [], source="fallback")
            )
            self.assertFalse(ok_empty)

            ok_range, _ = _apply_proposal(
                FixProposal("d", target, 1, 99, ["x = 10\n"], source="rule")
            )
            self.assertFalse(ok_range)
            self.assertEqual(target.read_text(encoding="utf-8"), "x = 1\ny = 2\n")

    def test_handle_exception_handles_eof_on_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "sample.py"
            code = "def run():\n    return 1 / 0\n\nrun()\n"
            target.write_text(code, encoding="utf-8")

            hook = ErrorHook()
            out_buf = io.StringIO()
            try:
                exec(compile(code, str(target), "exec"), {})
            except ZeroDivisionError as exc:
                _, _, tb = sys.exc_info()
                with (
                    patch("sys.stderr", new=io.StringIO()),
                    patch("sys.stdout", new=out_buf),
                    patch("builtins.input", side_effect=EOFError()),
                ):
                    hook._handle_exception(ZeroDivisionError, exc, tb)

            self.assertIn("keeping original code", out_buf.getvalue().lower())
            self.assertEqual(target.read_text(encoding="utf-8"), code)
            self.assertFalse(Path(f"{target}.bak").exists())


if __name__ == "__main__":
    unittest.main()
