import contextlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from continuity.core import ContinuityError
from continuity.estimator import estimate_handoff, format_report
from continuity.tokenizers import load_encodings, DATA_DIR
from examples.capacity_demo import samples, scenario


class EstimatorTests(unittest.TestCase):
    def estimate(self, original=None, inserted=None, **kwargs):
        return estimate_handoff(original or ["long archive " * 100],
                                inserted if inserted is not None else ["요약 summary"],
                                mode="heuristic", observed_at="2026-11-26", **kwargs)

    def test_original_is_inventory_not_current_context(self):
        a, b = self.estimate(original=["tiny"]), self.estimate(original=["huge " * 100000])
        self.assertEqual(a["estimated_used_tokens"], b["estimated_used_tokens"])
        self.assertNotEqual(a["original_archive"], b["original_archive"])

    def test_full_original_counts_only_when_explicitly_inserted(self):
        raw = "전체 원문입니다. " * 1000
        a = self.estimate(original=[raw])
        b = self.estimate(original=[raw], inserted=[raw])
        self.assertGreater(b["estimated_used_tokens"]["low"], a["estimated_used_tokens"]["high"])

    def test_followup_counts_and_no_automatic_understanding_multiplier(self):
        a = self.estimate(inserted=["hello"])
        b = self.estimate(inserted=["hello"], followup_texts=["followup"])
        for side in ("low", "high"):
            self.assertEqual(b["estimated_used_tokens"][side], a["estimated_used_tokens"][side]
                             + b["followup"]["totals"]["selected_token_range"][side])

    def test_repeated_material_counts_twice(self):
        a, b = self.estimate(inserted=["한국어 text"]), self.estimate(inserted=["한국어 text"] * 2)
        self.assertEqual(b["estimated_used_tokens"]["high"], 2 * a["estimated_used_tokens"]["high"])

    def test_empty_selected_text_is_explicit_zero(self):
        r = self.estimate(inserted=[""])
        self.assertEqual(r["estimated_used_tokens"], {"low": 0, "high": 0})
        self.assertIsNone(r["native_capacity_report"]["used_percent"])

    def test_missing_inserted_is_rejected(self):
        with self.assertRaises(ContinuityError):
            self.estimate(inserted=[])

    def test_overhead_added_reserve_not_used(self):
        r = self.estimate(inserted=[""], overhead_min=10, overhead_max=30,
                          context_limits=[100], next_turn_reserve=20)
        s = r["scenarios"][0]
        self.assertEqual(s["used_tokens"], {"low": 10, "high": 30})
        self.assertEqual(s["remaining_percent"], {"low": 70, "high": 90})
        self.assertEqual(s["available_after_reserve"], {"low": 50, "high": 70})

    def test_capacity_report_integration_and_provenance(self):
        r = self.estimate()
        self.assertFalse(r["native_chatgpt_capacity_known"])
        self.assertFalse(r["range_is_confidence_interval"])
        for s in r["scenarios"]:
            for side, c in s["capacity_report_bounds"].items():
                self.assertEqual(c["used_tokens"], s["used_tokens"][side])
                self.assertEqual(c["source"], "estimated")
                self.assertIn("assumed context limit", c["evidence"])

    def test_overflow_not_hidden(self):
        r = self.estimate(inserted=[""], overhead_min=110, overhead_max=150, context_limits=[100])
        s = r["scenarios"][0]
        self.assertEqual(s["used_percent"], {"low": 110, "high": 150})
        self.assertEqual(s["remaining_tokens"], {"low": 0, "high": 0})
        self.assertEqual(s["overflow"], "all")

    def test_possible_overflow_and_reserve_shortfall(self):
        s = self.estimate(inserted=[""], overhead_min=80, overhead_max=110,
                          next_turn_reserve=40, context_limits=[100])["scenarios"][0]
        self.assertEqual(s["overflow"], "possible")
        self.assertEqual(s["shortfall_with_reserve"], {"low": 20, "high": 50})

    def test_percent_order_and_multiple_limits(self):
        r = self.estimate(context_limits=[32000, 64000, 128000, 32000])
        self.assertEqual(len(r["scenarios"]), 3)
        for s in r["scenarios"]:
            self.assertLessEqual(s["remaining_percent"]["low"], s["remaining_percent"]["high"])
        self.assertLess(r["scenarios"][1]["used_percent"]["high"], r["scenarios"][0]["used_percent"]["high"])

    def test_invalid_ranges_and_types(self):
        for kwargs in ({"context_limits": []}, {"context_limits": [0]}, {"context_limits": [True]},
                       {"context_limits": "128000"}, {"overhead_min": -1}, {"overhead_min": 2, "overhead_max": 1},
                       {"overhead_max": 1.5}, {"next_turn_reserve": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ContinuityError):
                self.estimate(**kwargs)
        for text in ([1], "not a list", ["\ud800"]):
            with self.subTest(text=repr(text)), self.assertRaises(ContinuityError):
                self.estimate(inserted=text)

    def test_report_excludes_source_text_and_filenames(self):
        marker = "SYNTHETIC_SECRET_MARKER_73"
        r = self.estimate(original=[marker], inserted=[marker])
        self.assertNotIn(marker, json.dumps(r))
        self.assertNotIn(marker, format_report(r))

    def test_auto_fallback_explicit_bpe_error(self):
        with patch("continuity.estimator.load_encodings", side_effect=ContinuityError("missing")):
            r = estimate_handoff(["a"], ["b"])
            self.assertEqual(r["basis"], "uncalibrated_script_heuristic")
            with self.assertRaises(ContinuityError):
                estimate_handoff(["a"], ["b"], mode="bpe")

    def test_consistent_encoding_across_segments(self):
        class Encoding:
            def __init__(self, counts): self.counts = counts
            def encode_ordinary(self, text): return [0] * self.counts[text]
        encs = {"a": Encoding({"x": 10, "y": 1}), "b": Encoding({"x": 1, "y": 10})}
        with patch("continuity.estimator.load_encodings", return_value=encs):
            r = estimate_handoff(["x"], ["x"], ["y"])
        self.assertEqual(r["estimated_used_tokens"], {"low": 11, "high": 11})

    def test_estimate_never_needs_network(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            self.estimate()


class BPEIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.encodings = load_encodings()
        except ContinuityError as exc:
            raise unittest.SkipTest(str(exc))

    def test_matches_official_encodings_for_mixed_synthetic_text(self):
        import tiktoken
        from tiktoken_ext import openai_public
        for name, enc in self.encodings.items():
            # Supply verified local vocabulary to the official constructor; no download.
            with patch.object(openai_public, "load_tiktoken_bpe", return_value=enc._mergeable_ranks):
                official = tiktoken.Encoding(**getattr(openai_public, name)())
            for label, text in samples().items():
                with self.subTest(encoding=name, text=label):
                    self.assertEqual(enc.encode_ordinary(text), official.encode_ordinary(text))

    def test_bpe_offline_and_literal_special_tokens(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")), \
             patch("socket.create_connection", side_effect=AssertionError("network forbidden")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            r = estimate_handoff(["archive"], ["hello world <|endoftext|> 한국어"], mode="bpe")
        self.assertEqual(r["basis"], "bpe_encoding_comparison")
        self.assertIsNone(r["bpe_unavailable_reason"])

    def test_corrupt_or_missing_vocabulary_never_downloads(self):
        with tempfile.TemporaryDirectory() as d, \
             patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            with self.assertRaises(ContinuityError): load_encodings(d)
            (Path(d) / "cl100k_base.tiktoken").write_bytes(b"corrupt")
            with self.assertRaisesRegex(ContinuityError, "hash mismatch"): load_encodings(d)

    def test_korean_character_div_four_underestimates_this_sample(self):
        r = estimate_handoff(["a"], [samples()["korean"]], mode="bpe")
        t = r["inserted"]["totals"]
        self.assertLess(t["chars_div_4"], min(t["bpe"].values()))

    def test_heuristic_encloses_reference_samples_without_claiming_general_bound(self):
        for label, text in samples().items():
            r = estimate_handoff([text], [text], mode="bpe")
            t = r["inserted"]["totals"]
            with self.subTest(label=label):
                self.assertLessEqual(t["script_heuristic"]["low"], min(t["bpe"].values()))
                self.assertGreaterEqual(t["script_heuristic"]["high"], max(t["bpe"].values()))

    def test_long_archive_small_handoff(self):
        original, handoff, followup = scenario()
        r = estimate_handoff([original], [handoff], [followup], mode="bpe",
                             overhead_min=2000, overhead_max=8000)
        self.assertGreater(r["original_archive"]["totals"]["selected_token_range"]["low"], 128000)
        self.assertLess(r["estimated_used_tokens"]["high"], 32000)


class EstimatorCLITests(unittest.TestCase):
    def run_cli(self, args, cwd):
        import os
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        return subprocess.run([sys.executable, "-m", "continuity", *args], cwd=cwd,
                              env=env, capture_output=True, text=True, encoding="utf-8")

    def test_unicode_space_paths_bom_crlf_and_no_database_created(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "한글 공백.txt"
            p.write_bytes(b"\xef\xbb\xbf" + "한국어\r\nhello".encode())
            args = ["estimate-capacity", "--original", str(p), "--inserted", str(p), "--mode", "heuristic", "--json"]
            out = self.run_cli(args, root)
            self.assertEqual(out.returncode, 0, out.stderr)
            r = json.loads(out.stdout)
            self.assertEqual(r["inserted"]["totals"]["characters"], len("한국어\r\nhello"))
            self.assertEqual(r["input_file_bytes"]["inserted"][0], len(p.read_bytes()))
            self.assertFalse((root / ".continuity").exists())
            self.assertNotIn(str(p), out.stdout)

    def test_output_never_overwrites_input_or_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "input.txt"
            p.write_text("keep", encoding="utf-8")
            args = ["estimate-capacity", "--original", str(p), "--inserted", str(p), "--mode", "heuristic"]
            self.assertEqual(self.run_cli(args + ["--output", str(p)], d).returncode, 2)
            self.assertEqual(p.read_text(), "keep")
            out = Path(d) / "report.json"
            self.assertEqual(self.run_cli(args + ["--output", str(out)], d).returncode, 0)
            self.assertEqual(self.run_cli(args + ["--output", str(out)], d).returncode, 2)

    def test_non_utf8_binary_missing_file_and_no_input_content_in_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "input.txt"
            for data in (b"\xffSECRET", b"\x00SECRET"):
                p.write_bytes(data)
                out = self.run_cli(["estimate-capacity", "--original", str(p), "--inserted", str(p)], d)
                self.assertEqual(out.returncode, 2)
                self.assertNotIn("SECRET", out.stderr)
            p.unlink()
            self.assertEqual(self.run_cli(["estimate-capacity", "--original", str(p), "--inserted", str(p)], d).returncode, 2)


if __name__ == "__main__":
    unittest.main()
