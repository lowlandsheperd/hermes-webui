"""Regression coverage for browser session-export URLs under subpath mounts."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
BOOT_JS = ROOT / "static" / "boot.js"
NODE = shutil.which("node")


def _boot_source() -> str:
    return BOOT_JS.read_text(encoding="utf-8")


def _export_url_helper_source() -> str:
    """Extract the product helper so the test exercises its actual wiring."""
    source = _boot_source()
    marker = "function _buildSessionExportUrl("
    start = source.find(marker)
    assert start >= 0, "boot.js must centralize browser session-export URL building"
    brace = source.find("{", start)
    assert brace >= 0
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError("unterminated _buildSessionExportUrl helper")


def _run_builder(base_uri: str) -> list[dict[str, str]]:
    helper = _export_url_helper_source()
    script = f"""
const helper = {json.dumps(helper)};
const document = {{baseURI: {json.dumps(base_uri)}}};
const location = {{href: {json.dumps(base_uri)}}};
const build = new Function('document', 'location', 'URL', `${{helper}}; return _buildSessionExportUrl;`)(document, location, URL);
const sessionId = 'session /?&=✓';
const palette = 'eyJiZyI6IiNmZmYifQ==';
const urls = [
  new URL(build(sessionId)),
  new URL(build(sessionId, {{format: 'html', theme: 'dark', palette}})),
].map((url) => ({{
  pathname: url.pathname,
  session_id: url.searchParams.get('session_id'),
  format: url.searchParams.get('format') || '',
  theme: url.searchParams.get('theme') || '',
  palette: url.searchParams.get('palette') || '',
}}));
console.log(JSON.stringify(urls));
"""
    result = subprocess.run(
        [NODE, "-e", script],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(NODE is None, reason="node is required for browser URL checks")
def test_export_builder_keeps_root_and_subpath_mounts() -> None:
    for base_uri, expected_path in (
        ("https://example.test/", "/api/session/export"),
        ("https://example.test/hermes-webui/", "/hermes-webui/api/session/export"),
    ):
        json_export, html_export = _run_builder(base_uri)
        assert json_export == {
            "pathname": expected_path,
            "session_id": "session /?&=✓",
            "format": "",
            "theme": "",
            "palette": "",
        }
        assert html_export == {
            "pathname": expected_path,
            "session_id": "session /?&=✓",
            "format": "html",
            "theme": "dark",
            "palette": "eyJiZyI6IiNmZmYifQ==",
        }


def test_both_export_actions_use_the_shared_builder() -> None:
    source = _boot_source()
    assert "const url=_buildSessionExportUrl(S.session.session_id);" in source
    assert "const url=_buildSessionExportUrl(sid,{format:'html',theme,palette:paletteB64});" in source
    assert "`/api/session/export?" not in source
