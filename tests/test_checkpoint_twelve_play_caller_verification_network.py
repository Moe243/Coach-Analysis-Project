from __future__ import annotations

import os
import re
import unittest

import requests


@unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS") == "1", "network test is opt-in")
class PromptNineEvidenceNetworkTest(unittest.TestCase):
    def test_representative_identity_transition_and_shared_sources(self) -> None:
        checks = (
            (
                "https://www.azcardinals.com/news/"
                "as-coach-kliff-kingsbury-understands-playcalling-under-microscope",
                ("kliff kingsbury", "playcalling"),
            ),
            (
                "https://www.nfl.com/news/"
                "jaguars-oc-press-taylor-to-debut-as-new-full-time-play-caller-in-2023",
                ("doug pederson", "press taylor", "first half", "second half"),
            ),
            (
                "https://www.clevelandbrowns.com/news/"
                "kevin-stefanski-tests-positive-for-covid-19-will-continue-to-coach-virtually",
                ("alex van pelt", "play-caller"),
            ),
            (
                "https://www.detroitlions.com/news/"
                "lions-shuffle-coaching-staff-ahead-of-saturday-s-game-bevell-prince-ryan",
                ("sean ryan", "call offensive plays"),
            ),
            (
                "https://www.nfl.com/news/"
                "dolphins-naming-eric-studesville-and-george-godsey-as-offensive-co-coordinators",
                ("eric studesville", "george godsey", "unclear", "play-calling"),
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
