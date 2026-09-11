"""Deployment-only gate/transport tests; approved artifacts are never regenerated."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from nfl_coaching_impact import release_snapshot as release

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/processed/ask_anything" / release.VERSION


def test_approved_snapshot_contract():
    service = release.validate(SNAPSHOT)
    assert service.version == release.VERSION
    assert len(service.bundle["projections"]) == 57


@pytest.mark.parametrize("failure", ["missing", "corrupt", "wrong_manifest", "symlink"])
def test_reject_invalid_snapshot(tmp_path, failure):
    directory = tmp_path / release.VERSION
    shutil.copytree(SNAPSHOT, directory)
    if failure == "missing":
        (directory / "MANIFEST.json").unlink()
    elif failure == "wrong_manifest":
        p = directory / "MANIFEST.json"
        p.write_bytes(p.read_bytes().replace(release.VERSION.encode(), b"c19-0000000000000000"))
    elif failure == "symlink":
        (directory / "MANIFEST.json").unlink()
        (directory / "MANIFEST.json").symlink_to(SNAPSHOT / "MANIFEST.json")
    else:
        p = directory / "analytical_bundle.json"
        raw = p.read_bytes()
        p.write_bytes(b"!" + raw[1:])
    with pytest.raises(release.ReleaseError):
        release.validate(directory)


def test_absent_snapshot_blocks_socket_and_sanitizes_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ASK_DATA_DIR", str(tmp_path / "private-path"))
    with patch("uvicorn.run") as run:
        assert release.main(["start"]) == 1
        run.assert_not_called()
    assert "private-path" not in capsys.readouterr().err


def test_missing_configuration_fails(monkeypatch):
    monkeypatch.delenv("ASK_DATA_DIR", raising=False)
    with patch("uvicorn.run") as run:
        assert release.main(["start"]) == 1
        run.assert_not_called()


def test_start_uses_gate_and_clears_download_secret(monkeypatch):
    monkeypatch.setenv("ASK_DATA_DIR", str(SNAPSHOT))
    monkeypatch.setenv("ASK_ARTIFACT_TOKEN", "test-only-token")
    monkeypatch.setenv("PORT", "8019")
    with patch("uvicorn.run") as run:
        assert release.main(["start"]) == 0
        run.assert_called_once_with("nfl_coaching_impact.api:app", host="0.0.0.0", port=8019)
    import os

    assert "ASK_ARTIFACT_TOKEN" not in os.environ


def test_refusal_metadata_required():
    with patch.dict(release.REFUSALS, {}, clear=True):
        with pytest.raises(release.ReleaseError, match="metadata"):
            release.validate(SNAPSHOT)


@pytest.mark.parametrize("failure", ["count", "duplicate", "model", "active_roster"])
def test_projection_contract_rejected(failure):
    service = release.validate(SNAPSHOT)
    rows = service.bundle["projections"]
    if failure == "count":
        rows.pop()
    elif failure == "duplicate":
        rows[0] = rows[1].copy()
    elif failure == "model":
        rows[0]["model_version"] = "unapproved"
    else:
        rows[0]["active_roster_claim"] = True
    with patch.object(release.AnalyticalService, "from_directory", return_value=service):
        with pytest.raises(release.ReleaseError):
            release.validate(SNAPSHOT)


@pytest.mark.parametrize("failure", [None, "public", "corrupt", "missing"])
def test_private_transport_atomic_and_idempotent(tmp_path, monkeypatch, failure):
    monkeypatch.setenv("ASK_ARTIFACT_REPOSITORY", "owner/private-artifacts")
    monkeypatch.setenv("ASK_ARTIFACT_TOKEN", "test-only-token")
    names = list(release.FILES)
    seen = []

    def respond(request):
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer test-only-token"
        if request.url.path.endswith("private-artifacts"):
            return httpx.Response(200, json={"private": failure != "public"})
        if "/tags/" in request.url.path:
            assets = [
                {"id": i + 1, "name": name, "size": release.FILES[name][0]}
                for i, name in enumerate(names)
            ]
            return httpx.Response(
                200,
                json={
                    "tag_name": release.VERSION,
                    "draft": False,
                    "assets": [] if failure == "missing" else assets,
                },
            )
        name = names[int(request.url.path.rsplit("/", 1)[-1]) - 1]
        content = (SNAPSHOT / name).read_bytes()
        if failure == "corrupt":
            content = b"!" + content[1:]
        return httpx.Response(200, content=content)

    client = httpx.Client(transport=httpx.MockTransport(respond))
    destination = tmp_path / release.VERSION
    with patch.object(release.httpx, "Client", return_value=client):
        if failure:
            with pytest.raises(release.ReleaseError):
                release.restore(destination)
            assert not destination.exists()
            assert list(tmp_path.iterdir()) == []
        else:
            release.restore(destination)
            for name in names:
                assert (destination / name).read_bytes() == (SNAPSHOT / name).read_bytes()
            count = len(seen)
            release.restore(destination)
            assert len(seen) == count


def test_existing_corrupt_destination_is_not_overwritten(tmp_path):
    destination = tmp_path / release.VERSION
    destination.mkdir()
    (destination / "MANIFEST.json").write_text("retain-invalid-evidence")
    with patch.object(release.httpx, "Client") as client:
        with pytest.raises(release.ReleaseError):
            release.restore(destination)
        client.assert_not_called()
    assert (destination / "MANIFEST.json").read_text() == "retain-invalid-evidence"


def test_redirect_strips_token():
    def respond(request):
        if request.url.host == "api.github.com":
            assert request.headers["Authorization"] == "Bearer test-only-token"
            return httpx.Response(
                302,
                headers={
                    "Location": "https://release-assets.githubusercontent.com/pinned?sig=test"
                },
            )
        assert "Authorization" not in request.headers
        return httpx.Response(200, content=b"abc")

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert (
            release._asset(
                client,
                "https://api.github.com/asset",
                {"Authorization": "Bearer test-only-token"},
                3,
            )
            == b"abc"
        )


@pytest.mark.parametrize(
    "target", ["http://release-assets.githubusercontent.com/a", "https://evil.test/a"]
)
def test_unsafe_redirect_rejected(target):
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={"Location": target}))
    ) as client:
        with pytest.raises(release.ReleaseError):
            release._asset(client, "https://api.github.com/asset", {}, 3)


def test_http_failure_does_not_log_credentials(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ASK_DATA_DIR", str(tmp_path / release.VERSION))
    with patch.object(release, "restore", side_effect=ValueError("sensitive-test-token")):
        assert release.main(["restore"]) == 1
    assert "sensitive-test-token" not in capsys.readouterr().err
