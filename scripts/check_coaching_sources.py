#!/usr/bin/env python3
"""Separately callable network check for checkpoint-four citation URLs."""

from __future__ import annotations

import csv
import ssl
import urllib.request
from pathlib import Path

import certifi

from nfl_coaching_impact.coaching import validate_source_content

ROOT = Path(__file__).resolve().parents[1]
registry = ROOT / "data" / "manual" / "coaching_source_registry.csv"
context = ssl.create_default_context(cafile=certifi.where())


def check_url(url: str, label: str) -> None:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
    except Exception as first_error:
        request = urllib.request.Request(
            url, headers={"Range": "bytes=0-0", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            if response.status >= 400:
                raise RuntimeError(f"{label}: HTTP {response.status}") from first_error
    print(f"{label}: ok")


with registry.open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
for row in rows:
    check_url(row["source_url"], f"book {row['season']}")

with (ROOT / "data" / "manual" / "coach_assignment_sources.csv").open(
    newline="", encoding="utf-8"
) as handle:
    citation_urls = {row["source_url"] for row in csv.DictReader(handle)}
book_urls = {row["source_url"] for row in rows}
for index, url in enumerate(sorted(citation_urls - book_urls), start=1):
    check_url(url, f"assignment source {index}/{len(citation_urls - book_urls)}")

evidence_path = ROOT / "data" / "manual" / "coaching_source_content_checks.csv"
with evidence_path.open(newline="", encoding="utf-8") as handle:
    evidence_rows = list(csv.DictReader(handle))
content_by_url: dict[str, str] = {}
for row in evidence_rows:
    content = content_by_url.get(row["source_url"])
    if content is None:
        request = urllib.request.Request(row["source_url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            content = response.read().decode("utf-8", errors="replace")
        content_by_url[row["source_url"]] = content
    validate_source_content(content, row["required_terms"], row["evidence_id"])
    print(f"content {row['evidence_id']}: ok")
