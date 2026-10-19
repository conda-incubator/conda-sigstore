"""Shared conda test fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import conda_package_handling.api as package_handling
import pytest
from conda.base.constants import PACKAGE_CACHE_MAGIC_FILE
from conda.base.context import context

pytest_plugins = ["conda.testing.fixtures"]


@pytest.fixture(scope="module")
def rattler_manifest() -> dict[str, str]:
    """Describe the captured native publication and its frozen trust material."""
    manifest = Path(__file__).with_name("fixtures") / "rattler" / "manifest.json"
    return json.loads(manifest.read_text(encoding="utf-8"))


@pytest.fixture
def rattler_source_recipe() -> dict[str, object]:
    """Load the captured Rattler-Build source declaration."""
    recipe = (
        Path(__file__).with_name("fixtures")
        / "rattler-build-source"
        / "rendered_recipe.yaml"
    )
    return json.loads(recipe.read_text(encoding="utf-8"))


@pytest.fixture
def locked_conda_package(tmp_path: Path) -> tuple[Path, str, str, Path]:
    """Build one retained package for lockfile interoperability tests."""
    package_cache = tmp_path / "pkgs"
    package_cache.mkdir()
    (package_cache / PACKAGE_CACHE_MAGIC_FILE).touch()
    source = tmp_path / "source"
    (source / "info").mkdir(parents=True)
    (source / "info" / "index.json").write_text(
        json.dumps(
            {
                "name": "pkg",
                "version": "1.0",
                "build": "0",
                "build_number": 0,
                "subdir": context.subdir,
                "depends": [],
            }
        ),
        encoding="utf-8",
    )
    (source / "info" / "files").write_text("payload.txt\n", encoding="utf-8")
    (source / "payload.txt").write_text("locked package\n", encoding="utf-8")
    filename = "pkg-1.0-0.conda"
    package_handling.create(source, None, filename, package_cache)
    archive = package_cache / filename
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    artifact_url = f"https://conda.example.org/team/{context.subdir}/{filename}"
    extracted_payload = package_cache / "pkg-1.0-0" / "payload.txt"
    return package_cache, digest, artifact_url, extracted_payload
