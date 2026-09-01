"""בדיקות עבור מודול מעקב הקריסות ושחזור הצעדים (sbpy/trace.py)."""

from __future__ import annotations

import os
import unittest

from sbpy.trace import CrashTracer
from tests.support import IsolatedConfigTest


class TraceTest(IsolatedConfigTest):
    def test_trace_captures_timeline_and_locals(self) -> None:
        tracer = CrashTracer(history_size=10)
        
        def buggy_flow():
            a = 10
            b = 0
            return a / b

        snapshot = None
        try:
            with tracer:
                buggy_flow()
        except ZeroDivisionError as exc:
            snapshot = tracer.capture_snapshot(exc)

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.exc_type, "ZeroDivisionError")
        self.assertGreater(len(snapshot.timeline), 0)

        last_frame = snapshot.timeline[-1]
        self.assertIn("a", last_frame.locals)
        self.assertEqual(last_frame.locals["a"], "10")
        self.assertEqual(last_frame.locals["b"], "0")

    def test_save_json(self) -> None:
        tracer = CrashTracer()
        try:
            with tracer:
                x = [1, 2]
                y = x[10]
        except IndexError as exc:
            snapshot = tracer.capture_snapshot(exc)
            out_file = os.path.join(self.home, "crash.json")
            path = snapshot.save_json(out_file)
            self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()
