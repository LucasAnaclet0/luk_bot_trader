"""Offline regression tests for CoinGecko cooldown; never imports trading modules."""
import ast
import math
import time
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "scanner_multi_crypto.py"


def _client():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == "_CoinGeckoClient")


class CoinGeckoCooldownTests(unittest.TestCase):
    def test_retry_after_seconds(self):
        method = next(n for n in _client().body
                      if isinstance(n, ast.FunctionDef) and n.name == "_retry_after_seconds")
        # Evaluate only this pure method, not scanner imports or startup.
        cls = ast.ClassDef(name="Parser", bases=[], keywords=[],
                           body=[method], decorator_list=[])
        module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
        namespace = {"math": math, "time": time,
                     "parsedate_to_datetime": parsedate_to_datetime}
        exec(compile(module, str(SOURCE), "exec"), namespace)
        parser = namespace["Parser"]._retry_after_seconds
        self.assertEqual(parser("600"), 600.0)
        self.assertEqual(parser("1"), 1.0)
        self.assertEqual(parser("invalid"), 0.0)
        self.assertEqual(parser("-1"), 0.0)
        self.assertEqual(parser("inf"), 0.0)
        self.assertEqual(parser(None), 0.0)
        future = datetime.fromtimestamp(time.time() + 600, timezone.utc)
        self.assertGreater(parser(format_datetime(future, usegmt=True)), 590)

    def test_cooldown_rechecked_after_rate_limit(self):
        method = next(n for n in _client().body
                      if isinstance(n, ast.AsyncFunctionDef)
                      and n.name == "get_fundamental_data")
        body = method.body
        waits = [i for i, node in enumerate(body)
                 if isinstance(node, ast.Expr) and isinstance(node.value, ast.Await)
                 and isinstance(node.value.value, ast.Call)
                 and isinstance(node.value.value.func, ast.Attribute)
                 and node.value.value.func.attr == "_rate_limit"]
        self.assertEqual(len(waits), 1)
        after = body[waits[0] + 1]
        self.assertIsInstance(after, ast.If)
        self.assertIn("_cooldown_until", ast.unparse(after.test))
        self.assertTrue(any(isinstance(n, ast.Return) for n in after.body))

    def test_rate_limit_response_extends_deadline(self):
        method = next(n for n in _client().body
                      if isinstance(n, ast.AsyncFunctionDef)
                      and n.name == "get_fundamental_data")
        source = ast.unparse(method)
        self.assertIn('resp.headers.get(\'Retry-After\')', source)
        self.assertIn('max(self._cooldown_until,', source)


if __name__ == "__main__":
    unittest.main()
