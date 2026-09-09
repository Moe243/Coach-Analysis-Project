from __future__ import annotations

import os
import re
import unittest

import requests


@unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS") == "1", "network test is opt-in")
class PromptEightEvidenceNetworkTest(unittest.TestCase):
    def test_representative_play_caller_source_content(self) -> None:
        checks = (
            (
                "https://www.azcardinals.com/news/"
                "spencer-whipple-makes-most-of-chance-as-cardinals-playcaller",
                ("spencer whipple", "playcaller", "cleveland"),
            ),
            (
                "https://www.colts.com/news/"
                "parks-frazier-offensive-play-caller-jeff-saturday-interim-head-coach",
                ("parks frazier", "play caller", "remainder"),
            ),
            (
                "https://www.detroitlions.com/news/"
                "campbell-confirms-lions-are-parting-ways-with-anthony-lynn",
                ("anthony lynn", "playing calling", "week 9"),
            ),
            (
                "https://www.giants.com/news/"
                "brian-daboll-mike-kafka-offensive-coordinator-week-1-"
                "tennessee-titans-playcaller",
                ("mike kafka", "play caller", "tennessee"),
            ),
        )
        for url, terms in checks:
            with self.subTest(url=url):
                response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
                self.assertEqual(response.status_code, 200)
                normalized = " ".join(re.sub(r"[-–—]", " ", response.text.casefold()).split())
                for term in terms:
                    self.assertIn(term, normalized)


if __name__ == "__main__":
    unittest.main()
