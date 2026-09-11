"""Deployment-only C19 delivery/startup gate; separate from analytical code identity."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

import httpx

from .ask import REFUSALS, AnalyticalService, Intent, Status

VERSION = "c19-62010b4bfffeb4af"
MODEL = "qb-calibrated-8c8063c5954e2a22"
FILES = {
    "MANIFEST.json": (
        5273,
        "e13a911037ef1761f6d9d0882a274745c0dfb563aecd3990ecdf7b72b73c2657",
    ),
    "analytical_bundle.json": (
        46987140,
        "cc2666a8b7506e3b7e766ec687043e24d3d4be454f8e97545e4dab26223d533d",
    ),
}
REFUSAL_QUESTIONS = {
    Intent.PLAYER_TEAM_SCENARIO: "What would Kyler Murray do in Minnesota?",
    Intent.CAREER_COUNTERFACTUAL: "What if Mahomes was drafted by Chicago?",
    Intent.COACH_EFFECT: "How much better does Andy Reid make quarterbacks?",
    Intent.ROOKIE_PROJECTION: "How will this college QB perform in the NFL?",
}


class ReleaseError(ValueError):
    """Only fixed, credential-free messages may reach the CLI."""


def validate(directory: Path) -> AnalyticalService:
    for name, (size, checksum) in FILES.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
            raise ReleaseError("Pinned snapshot file missing or incorrect size")
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ReleaseError("Pinned snapshot checksum mismatch")
    service = AnalyticalService.from_directory(directory)
    if service.version != VERSION:
        raise ReleaseError("Unapproved C19 version")
    projections = service.bundle["projections"]
    if len(projections) != 57 or len({r["player_id"] for r in projections}) != 57:
        raise ReleaseError("Expected 57 distinct approved projections")
    if any(
        r["target_season"] != 2026
        or r["outcome"] != "epa"
        or r["base_model"] != "B2"
        or r["calibration_method"] != "BIAS"
        or r["active_roster_claim"] is not False
        or r["model_version"] != MODEL
        for r in projections
    ):
        raise ReleaseError("Unapproved projection contract")
    # Refusal metadata lives in the code pinned by MANIFEST, not an invented bundle field.
    for intent, question in REFUSAL_QUESTIONS.items():
        if intent not in REFUSALS or not all(REFUSALS[intent]):
            raise ReleaseError("Required refusal metadata absent")
        answer = service.answer(question)
        if (
            answer.intent != intent
            or answer.status not in {Status.NOT_SUPPORTED, Status.NOT_YET_SUPPORTED}
            or answer.metrics
            or answer.model_version is not None
            or not answer.available_alternative
            or not answer.reason
        ):
            raise ReleaseError("Required refusal contract failed")
    return service


def _asset(
    client: httpx.Client, url: str, headers: dict, size: int, *, redirected: bool = False
) -> bytes:
    # GitHub serves either bytes or a signed CDN redirect. Never forward the PAT to the CDN.
    with client.stream("GET", url, headers={**headers, "Accept": "application/octet-stream"}) as r:
        if r.status_code == 302 and not redirected:
            location = httpx.URL(r.headers["Location"])
            if (
                location.scheme != "https"
                or location.host != "release-assets.githubusercontent.com"
                or location.userinfo
                or location.port not in {None, 443}
            ):
                raise ReleaseError("Unexpected artifact redirect")
            return _asset(client, str(location), {}, size, redirected=True)
        r.raise_for_status()
        content = bytearray()
        for chunk in r.iter_bytes():
            content.extend(chunk)
            if len(content) > size:
                raise ReleaseError("Artifact exceeds pinned size")
        if len(content) != size:
            raise ReleaseError("Incomplete artifact download")
        return bytes(content)


def restore(directory: Path) -> None:
    if directory.exists():
        validate(directory)  # Never overwrite an invalid existing publication.
        return
    repo = os.environ.get("ASK_ARTIFACT_REPOSITORY", "")
    token = os.environ.get("ASK_ARTIFACT_TOKEN", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
        raise ReleaseError("Configure ASK_ARTIFACT_REPOSITORY and ASK_ARTIFACT_TOKEN")
    base = f"https://api.github.com/repos/{repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    with httpx.Client(timeout=120, follow_redirects=False, trust_env=False) as client:
        metadata = client.get(base, headers=headers)
        metadata.raise_for_status()
        if metadata.json().get("private") is not True:
            raise ReleaseError("Artifact repository must be private")
        release = client.get(f"{base}/releases/tags/{VERSION}", headers=headers)
        release.raise_for_status()
        record = release.json()
        if record.get("tag_name") != VERSION or record.get("draft") is not False:
            raise ReleaseError("Pinned published release required")
        assets = record["assets"]
        directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".ask-restore-", dir=directory.parent) as temp:
            stage = Path(temp)
            for name, (size, _) in FILES.items():
                matches = [a for a in assets if a["name"] == name]
                if len(matches) != 1 or matches[0]["size"] != size:
                    raise ReleaseError("Pinned release asset missing or incorrect size")
                asset_id = matches[0]["id"]
                if type(asset_id) is not int or asset_id <= 0:
                    raise ReleaseError("Invalid asset identifier")
                content = _asset(client, f"{base}/releases/assets/{asset_id}", headers, size)
                (stage / name).write_bytes(content)
            validate(stage)
            stage.rename(directory)  # Atomic, same filesystem; no partial publication.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("restore", "validate", "start"))
    args = parser.parse_args(argv)
    try:
        configured = os.environ.get("ASK_DATA_DIR")
        if not configured:
            raise ReleaseError("ASK_DATA_DIR is required; API was not started")
        directory = Path(configured)
        if args.command == "restore":
            restore(directory)
        else:
            validate(directory)
        if args.command == "start":
            import uvicorn

            # Load the exact same pinned service into the endpoint cache before binding a socket.
            from .ask_api import _load

            _load(str(directory))
            os.environ.pop("ASK_ARTIFACT_TOKEN", None)
            uvicorn.run(
                "nfl_coaching_impact.api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000"))
            )
        else:
            print(f"C19 snapshot {VERSION}: {args.command} passed (57 projections)")
        return 0
    except ReleaseError as error:
        print(f"C19 release gate failed: {error}. API was not started.", file=sys.stderr)
        return 1
    except Exception:
        # HTTP exceptions can contain authenticated URLs; never emit exception text/tracebacks.
        print(
            "C19 release gate failed: check snapshot pins, private artifact access "
            "and configuration. "
            "No fallback or regeneration was attempted; API startup was blocked.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
