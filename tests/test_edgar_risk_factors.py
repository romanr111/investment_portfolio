"""Offline tests for Item 1A extraction and diffing with local HTML fixtures."""
import unittest
from pathlib import Path

from src.edgar import risk_factors

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edgar"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class HtmlToTextTests(unittest.TestCase):
    def test_block_tags_become_lines_and_entities_decode(self):
        text = risk_factors.html_to_text(_load("tenk_v1.html"))
        self.assertIn("Competitive pressures could reduce demand for product lines & sampled services.", text)
        # The script block is skipped entirely.
        self.assertNotIn("never parsed", text)
        # Block tags separate lines instead of gluing words together.
        self.assertIn("\nItem 1A", text)

    def test_empty_and_none_inputs_do_not_crash(self):
        self.assertEqual(risk_factors.html_to_text("").strip(), "")
        self.assertEqual(risk_factors.html_to_text(None).strip(), "")


class ExtractItem1ATests(unittest.TestCase):
    def test_body_slice_wins_over_toc_markers(self):
        status, section = risk_factors.extract_item_1a(risk_factors.html_to_text(_load("tenk_v1.html")))
        self.assertEqual(status, "extracted")
        self.assertIn("Operational risks remain elevated", section)
        self.assertNotIn("Unresolved Staff Comments", section.rsplit("Item 1B")[0])
        # The TOC mentions Item 1A before the body; the chosen slice must be the body.
        self.assertGreater(len(section.splitlines()), 5)
        # Slice keeps boundaries: it does not leak into Item 2 content.
        self.assertNotIn("leases its facilities", section)

    def test_body_heading_beats_pre_body_cross_reference(self):
        # The cross-reference "Item 1A" sits far from any "Risk Factors"
        # label, so under the old longest-slice rule its slice (running to
        # the next Item 1B boundary, i.e. over the whole body) would win.
        status, section = risk_factors.extract_item_1a(risk_factors.html_to_text(_load("tenk_v3_crossref.html")))
        self.assertEqual(status, "extracted")
        self.assertIn("Operational risks remain elevated", section)
        self.assertNotIn("described in Item 1A", section)

    def test_item1a_not_found_status(self):
        status, section = risk_factors.extract_item_1a("No risk factors item here at all.")
        self.assertEqual(status, "item1a_not_found")
        self.assertEqual(section, "")

    def test_empty_slice_status(self):
        status, section = risk_factors.extract_item_1a("Item 1A.\nItem 1B. Unresolved Staff Comments")
        self.assertEqual(status, "empty")
        self.assertEqual(section, "")

    def test_none_input(self):
        self.assertEqual(risk_factors.extract_item_1a(None)[0], "item1a_not_found")


class DiffTextTests(unittest.TestCase):
    def setUp(self):
        self.v1 = risk_factors.extract_item_1a(risk_factors.html_to_text(_load("tenk_v1.html")))[1]
        self.v2 = risk_factors.extract_item_1a(risk_factors.html_to_text(_load("tenk_v2.html")))[1]

    def test_counts_are_deterministic_and_twosided(self):
        first = risk_factors.diff_text(self.v1, self.v2)
        second = risk_factors.diff_text(self.v1, self.v2)
        self.assertEqual(first, second)
        added, removed, _diff, _headers = first
        # v2 adds two paragraphs (one under a new header), v1 loses one.
        self.assertEqual(added, 5)
        self.assertEqual(removed, 1)

    def test_added_headers_come_from_header_like_lines(self):
        _added, _removed, _diff, headers = risk_factors.diff_text(self.v1, self.v2)
        self.assertIn("Supply chain concentration", headers)

    def test_no_changes(self):
        added, removed, diff_text, _headers = risk_factors.diff_text(self.v1, self.v1)
        self.assertEqual((added, removed), (0, 0))
        self.assertEqual(diff_text, "")

    def test_diff_text_is_capped_at_64k(self):
        big_old = "line\n" + ("old line\n" * 60000)
        big_new = "line\n" + ("new line\n" * 60000)
        _added, _removed, diff_text, _headers = risk_factors.diff_text(big_old, big_new)
        self.assertLessEqual(len(diff_text), risk_factors.MAX_DIFF_CHARS)


class RiskHeadersTests(unittest.TestCase):
    def test_header_like_lines_selected(self):
        text = "Intro paragraph.\n\nA standalone heading here\n\nFollow-up body text with a period.\n"
        self.assertIn("A standalone heading here", risk_factors.risk_headers(text))

    def test_sentences_and_long_lines_rejected(self):
        text = "Full sentence with a period.\n\n" + ("x" * 200) + "\n\n12345\n\nNext\n"
        headers = risk_factors.risk_headers(text)
        self.assertNotIn("Full sentence with a period.", headers)
        self.assertNotIn("x" * 200, headers)
        self.assertNotIn("12345", headers)


class ScanItemCodesTests(unittest.TestCase):
    def test_document_scan_finds_unique_codes(self):
        codes = risk_factors.scan_item_codes(_load("eightka.html"))
        self.assertEqual(codes, ["5.02", "9.01"])

    def test_no_codes(self):
        self.assertEqual(risk_factors.scan_item_codes("<p>plain</p>"), [])


if __name__ == "__main__":
    unittest.main()
