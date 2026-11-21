import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from smart_err_corrector.proposer import FixProposal, propose_fix


class TestProposeFixRules(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_path = Path("sample_script.py")

    def test_zero_division_return_statement_uses_return_fallback(self) -> None:
        lines = [
            "def avg(total, count):\n",
            "    return total // count\n",
        ]
        proposal = propose_fix(
            ZeroDivisionError,
            ZeroDivisionError("division by zero"),
            self.sample_path,
            line_no=2,
            lines=lines,
        )

        self.assertIsInstance(proposal, FixProposal)
        self.assertEqual(proposal.source, "rule:ZeroDivisionError")
        joined = "".join(proposal.replacement_lines)
        self.assertIn("try:", joined)
        self.assertIn("except ZeroDivisionError:", joined)
        self.assertIn("return 0", joined)
        self.assertNotIn("result = 0", joined)

    def test_zero_division_non_return_uses_assignment_fallback(self) -> None:
        lines = [
            "share = total / count\n",
        ]
        proposal = propose_fix(
            ZeroDivisionError,
            ZeroDivisionError("division by zero"),
            self.sample_path,
            line_no=1,
            lines=lines,
        )

        self.assertEqual(proposal.source, "rule:ZeroDivisionError")
        joined = "".join(proposal.replacement_lines)
        self.assertIn("result = 0", joined)
        self.assertNotIn("return 0", joined)

    def test_key_error_rule(self) -> None:
        lines = [
            'val = data["missing"]\n',
        ]
        proposal = propose_fix(
            KeyError,
            KeyError("missing"),
            self.sample_path,
            line_no=1,
            lines=lines,
        )

        self.assertEqual(proposal.source, "rule:KeyError")
        joined = "".join(proposal.replacement_lines)
        self.assertIn(".get(", joined)
        self.assertIn('val = data["missing"]\n', joined)

    def test_index_error_rule(self) -> None:
        lines = [
            "item = items[10]\n",
        ]
        proposal = propose_fix(
            IndexError,
            IndexError("list index out of range"),
            self.sample_path,
            line_no=1,
            lines=lines,
        )

        self.assertEqual(proposal.source, "rule:IndexError")
        joined = "".join(proposal.replacement_lines)
        self.assertIn("sequence length", joined)
        self.assertIn("item = items[10]\n", joined)


class TestProposeFixFallbacks(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_path = Path("sample_script.py")
        self.lines = ['num = int("bad")\n']

    def test_fallback_when_groq_api_key_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GROQ_API_KEY", None)
            proposal = propose_fix(
                ValueError,
                ValueError("invalid literal for int() with base 10: 'bad'"),
                self.sample_path,
                line_no=1,
                lines=self.lines,
            )

        self.assertEqual(proposal.source, "fallback")
        self.assertEqual(proposal.replacement_lines, ['num = int("bad")\n'])

    @patch("smart_err_corrector.proposer.urllib.request.urlopen")
    def test_groq_fallback_when_key_set(self, mock_urlopen: MagicMock) -> None:
        groq_response_body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "diagnosis": "Invalid integer literal passed to int().",
                                    "replacement_code": "num = 0  # fallback on invalid int",
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
                ValueError("invalid literal for int() with base 10: 'bad'"),
                self.sample_path,
                line_no=1,
                lines=self.lines,
            )

        self.assertTrue(proposal.source.startswith("groq:"))
        self.assertIn("Invalid integer literal", proposal.diagnosis)
        self.assertIn("num = 0", "".join(proposal.replacement_lines))
        mock_urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
