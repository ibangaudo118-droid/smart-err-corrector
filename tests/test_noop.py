import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from smart_err_corrector.hook import ErrorHook, _apply_proposal
from smart_err_corrector.proposer import FixProposal, propose_fix


class TestNoopGuards(unittest.TestCase):
    @patch("smart_err_corrector.proposer.urllib.request.urlopen")
    def test_groq_noop_suggestion_falls_back_to_original_line(
        self, mock_urlopen: MagicMock
    ) -> None:
        lines = [
            "def parse_age(raw_value):\n",
            "    return int(raw_value)\n",
        ]
        groq_response_body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "diagnosis": "Echoes original line.",
                                    "replacement_code": "    return int(raw_value)",
                                }
                            )
                        }
                    }
                ]
            }
        ).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = groq_response_body
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False):
            proposal = propose_fix(
                ValueError,
                ValueError("invalid literal for int() with base 10: 'not_a_number'"),
                Path("app.py"),
                line_no=2,
                lines=lines,
            )

        self.assertEqual(proposal.source, "fallback")
        self.assertEqual(proposal.replacement_lines, ["    return int(raw_value)\n"])

    def test_apply_proposal_blocks_noop_without_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "sample.py"
            original = "def parse_age(raw_value):\n    return int(raw_value)\n"
            target.write_text(original, encoding="utf-8")

            proposal = FixProposal(
                diagnosis="No change",
                file_path=target,
                start_line=2,
                end_line=2,
                replacement_lines=["    return int(raw_value)\n"],
                source="fallback",
            )

            applied, msg = _apply_proposal(proposal)
            self.assertFalse(applied)
            self.assertIn("No code change", msg)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertFalse(Path(f"{target}.bak").exists())

    def test_handle_exception_skips_prompt_on_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "sample.py"
            original = (
                "def parse_age(raw_value):\n"
                "    return int(raw_value)\n\n"
                'parse_age("not_a_number")\n'
            )
            target.write_text(original, encoding="utf-8")

            hook = ErrorHook()
            stdout_buf = io.StringIO()
            try:
                exec(compile(original, str(target), "exec"), {})
            except ValueError as exc:
                _, _, tb = sys.exc_info()
                with (
                    patch.dict(os.environ, {}, clear=False),
                    patch("sys.stderr", new=io.StringIO()),
                    patch("sys.stdout", new=stdout_buf),
                    patch("builtins.input", side_effect=AssertionError("Should not prompt")),
                ):
                    os.environ.pop("GROQ_API_KEY", None)
                    hook._handle_exception(ValueError, exc, tb)

            self.assertIn("No actionable replacement proposed", stdout_buf.getvalue())
            self.assertFalse(Path(f"{target}.bak").exists())


if __name__ == "__main__":
    unittest.main()
