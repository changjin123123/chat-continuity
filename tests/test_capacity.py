import unittest
from continuity.capacity import capacity_report
from continuity.core import ContinuityError
from continuity.mcp import call

class CapacityTests(unittest.TestCase):
    def measured(self, **kwargs):
        return capacity_report(source="caller_reported", evidence="host context meter", observed_at="2026-11-25T00:00:00Z", **kwargs)

    def test_unknown_is_not_zero(self):
        result = call(None, "capacity_report", {})
        self.assertIsNone(result["used_percent"])
        self.assertIsNone(result["should_prepare_handoff"])
        self.assertFalse(result["native_chatgpt_capacity_known"])

    def test_partial_data_is_unknown(self):
        self.assertIsNone(self.measured(context_limit=100000)["used_percent"])
        self.assertIsNone(self.measured(used_tokens=12000)["used_percent"])

    def test_real_zero_and_threshold(self):
        self.assertEqual(self.measured(context_limit=100000, used_tokens=0)["used_percent"], 0)
        self.assertFalse(self.measured(context_limit=100000, used_tokens=94999)["should_prepare_handoff"])
        self.assertTrue(self.measured(context_limit=100000, used_tokens=95000)["should_prepare_handoff"])
        self.assertTrue(self.measured(context_limit=100000, used_tokens=90000, next_turn_reserve=12000)["should_prepare_handoff"])

    def test_overflow_not_hidden(self):
        r=self.measured(context_limit=100, used_tokens=120)
        self.assertEqual(r["used_percent"],120)
        self.assertTrue(r["over_limit"])
        self.assertEqual(r["remaining_percent"],0)

    def test_estimates_are_labeled(self):
        r=capacity_report(100000,12000,"estimated","tokenizer estimate, assumed limit","2026-11-25")
        self.assertEqual(r["used_percent"],12)
        self.assertIn("추정",r["display"])
        self.assertFalse(r["native_chatgpt_capacity_known"])

    def test_missing_provenance_and_bad_input(self):
        for args in ({"context_limit":100}, {"source":"estimated"},
                     {"context_limit":0}, {"used_tokens":-1}, {"used_tokens":True},
                     {"next_turn_reserve":-1}, {"source":"native"}):
            with self.subTest(args=args), self.assertRaises(ContinuityError):capacity_report(**args)
        with self.assertRaises(ContinuityError):call(None,"capacity_report",{"used_tokens":1.5})

if __name__ == '__main__':unittest.main()
