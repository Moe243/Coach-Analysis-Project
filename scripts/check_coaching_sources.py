#!/usr/bin/env python3
"""Separately callable network check for checkpoint-four citation URLs."""

from __future__ import annotations

import csv
import ssl
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parents[1]
registry = ROOT / "data" / "manual" / "coaching_source_registry.csv"
context = ssl.create_default_context(cafile=certifi.where())

with registry.open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))
for row in rows:
    request = urllib.request.Request(row["source_url"], method="HEAD")
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
    except Exception as first_error:
        request = urllib.request.Request(
            row["source_url"], headers={"Range": "bytes=0-0", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            if response.status >= 400:
                raise RuntimeError(f"{row['season']}: HTTP {response.status}") from first_error
    print(f"{row['season']}: ok")
