"""Offline tests for the 8-K item severity table and filing classification."""
import unittest

from src.edgar import severity


class SeverityTableTests(unittest.TestCase):
    def test_red_items_match_owner_decision(self):
        expected_red = {"1.03", "1.05", "2.03", "2.04", "3.01", "4.01", "4.02", "5.01", "6.04"}
        actual = {
            code
            for code, (_title, level) in severity.ITEM_TABLE.items()
            if level == severity.LEVEL_RED
        }
        self.assertEqual(actual, expected_red)

    def test_warn_items_match_owner_decision(self):
        expected_warn = {"2.05", "2.06", "5.05", "5.06", "6.03"}
        actual = {
            code
            for code, (_title, level) in severity.ITEM_TABLE.items()
            if level == severity.LEVEL_WARN
        }
        self.assertEqual(actual, expected_warn)

    def test_every_entry_carries_title_and_known_level(self):
        for code, (title, level) in severity.ITEM_TABLE.items():
            self.assertTrue(title, f"item {code} has a title")
            self.assertIn(level, (severity.LEVEL_RED, severity.LEVEL_WARN, severity.LEVEL_INFO))

    def test_treatments_cover_all_levels(self):
        self.assertEqual(
            set(severity.TREATMENTS),
            {severity.LEVEL_RED, severity.LEVEL_WARN, severity.LEVEL_INFO},
        )


class ClassifyTests(unittest.TestCase):
    def test_8k_red_item_and_info_exhibit(self):
        classification = severity.classify("8-K", "4.02,9.01")
        self.assertTrue(classification.monitored)
        self.assertEqual(classification.level, severity.LEVEL_RED)
        self.assertEqual(
            [event["item_code"] for event in classification.events], ["4.02", "9.01"]
        )
        self.assertEqual(classification.events[0]["level"], severity.LEVEL_RED)
        self.assertEqual(classification.events[-1]["level"], severity.LEVEL_INFO)
        self.assertEqual(
            classification.events[0]["items"], "4.02,9.01",
        )

    def test_8k_warn_level(self):
        classification = severity.classify("8-K", "2.05")
        self.assertEqual(classification.level, severity.LEVEL_WARN)

    def test_unknown_item_is_info_and_logged(self):
        with self.assertLogs("src.edgar.severity", level="WARNING"):
            classification = severity.classify("8-K", "7.01")
        self.assertEqual(classification.level, severity.LEVEL_INFO)
        self.assertEqual(classification.events[0]["item_code"], "7.01")
        self.assertIsNone(classification.events[0]["title"])

    def test_9_01_alone_stays_info(self):
        classification = severity.classify("8-K", "9.01")
        self.assertEqual(classification.level, severity.LEVEL_INFO)
        self.assertEqual(len(classification.events), 1)

    def test_form_4_is_info_event_without_item_code(self):
        classification = severity.classify("4", "")
        self.assertTrue(classification.monitored)
        self.assertEqual(classification.level, severity.LEVEL_INFO)
        self.assertEqual(len(classification.events), 1)
        self.assertIsNone(classification.events[0]["item_code"])

    def test_periodic_forms_create_no_item_events(self):
        for form in ("10-K", "10-K/A", "10-Q", "10-Q/A"):
            classification = severity.classify(form, "")
            self.assertTrue(classification.monitored, form)
            self.assertEqual(classification.events, [], form)
            self.assertFalse(classification.needs_doc_scan, form)

    def test_non_monitored_fund_and_proxy_forms_are_seen_without_events(self):
        for form in ("NPORT-P", "S-8", "DEF 14A", "25-NSE", "10-12G"):
            classification = severity.classify(form, "")
            self.assertFalse(classification.monitored, form)
            self.assertEqual(classification.events, [], form)
            self.assertFalse(classification.needs_doc_scan, form)

    def test_8ka_with_empty_items_needs_document_scan(self):
        classification = severity.classify("8-K/A", "")
        self.assertTrue(classification.monitored)
        self.assertTrue(classification.needs_doc_scan)
        self.assertEqual(classification.events, [])

    def test_plain_8k_with_empty_items_needs_no_scan(self):
        classification = severity.classify("8-K", "")
        self.assertTrue(classification.monitored)
        self.assertFalse(classification.needs_doc_scan)
        self.assertEqual(classification.events, [])

    def test_items_whitespace_and_duplicates_normalize(self):
        classification = severity.classify("8-K", " 2.02 , 2.02, 3.01 ")
        self.assertEqual(
            [event["item_code"] for event in classification.events], ["2.02", "3.01"]
        )

    def test_items_list_input(self):
        classification = severity.classify("8-K", ["2.02", "9.01"])
        self.assertEqual(len(classification.events), 2)


if __name__ == "__main__":
    unittest.main()
