from __future__ import annotations

import os
import re
import unittest

import requests


@unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS") == "1", "network test is opt-in")
class PromptTenEvidenceNetworkTest(unittest.TestCase):
    def test_representative_continuity_transition_and_bounded_sources(self) -> None:
        checks = (
            (
                "https://www.raiders.com/news/raiders-players-staying-focused-on-denver-"
                "eyeing-a-divisional-road-win",
                ("greg olson", "takes over playcalling"),
            ),
            (
                "https://www.denverbroncos.com/news/oc-pat-shurmur-expected-to-miss-"
                "phivsden-due-to-covid-19-protocols",
                ("pat shurmur", "mike shula", "assume shurmur's duties"),
            ),
            (
                "https://www.buffalobills.com/news/hackett-s-sideline-presence-helps-11869470",
                ("nathaniel hackett", "all season long", "calling plays"),
            ),
            (
                "https://www.newyorkjets.com/news/todd-downing-will-be-the-main-voice-"
                "in-the-jets-qb-room",
                ("downing called the plays", "titans", "2021-22"),
            ),
            (
                "https://www.nfl.com/news/saints-fire-offensive-coordinator-pete-"
                "carmichael-after-15-seasons",
                ("carmichael", "took over play-calling", "when payton left", "two seasons"),
            ),
        )
        for url, terms in checks:
            with self.subTest(url=url):
                response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=45)
                self.assertEqual(response.status_code, 200)
                normalized = " ".join(re.sub(r"[-–—]", "-", response.text.casefold()).split())
                for term in terms:
                    self.assertIn(term, normalized)


if __name__ == "__main__":
    unittest.main()
