from __future__ import annotations

import unittest

from services.mobile_ocr_service import parse_mobile_ocr_paste


PROFILE = "profile_wild_shards_wf_gold"


class MobileOcrPasteParserTest(unittest.TestCase):
    def assert_values(self, text: str) -> None:
        parsed = parse_mobile_ocr_paste(text, PROFILE)
        self.assertEqual(parsed["values"]["wild_shards"], 10054)
        self.assertEqual(parsed["values"]["wf"], 2221.50)
        self.assertEqual(parsed["values"]["gold"], 280486)

    def test_multiline_space_separators(self) -> None:
        self.assert_values("10 054\n2 221.50\n280 486")

    def test_comma_separators(self) -> None:
        self.assert_values("10,054\n2,221.50\n280,486")

    def test_single_line_with_labels(self) -> None:
        self.assert_values("Wild Shards 10 054 WF 2 221.50 Gold 280 486")

    def test_fewer_numbers_warns_and_keeps_available_values(self) -> None:
        parsed = parse_mobile_ocr_paste("10 054\n2 221.50", PROFILE)
        self.assertEqual(parsed["values"]["wild_shards"], 10054)
        self.assertEqual(parsed["values"]["wf"], 2221.50)
        self.assertIsNone(parsed["values"]["gold"])
        self.assertTrue(parsed["warnings"])

    def test_extra_numbers_warns_and_uses_first_three(self) -> None:
        parsed = parse_mobile_ocr_paste("Wild Shards 10 054 WF 2 221.50 Gold 280 486 Extra 999", PROFILE)
        self.assertEqual(parsed["values"]["wild_shards"], 10054)
        self.assertEqual(parsed["values"]["wf"], 2221.50)
        self.assertEqual(parsed["values"]["gold"], 280486)
        self.assertTrue(parsed["warnings"])


if __name__ == "__main__":
    unittest.main()
