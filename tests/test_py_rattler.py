"""Verify captured publication evidence through py-rattler's Rust bindings."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path

import pytest
from rattler import (
    ChannelCheck,
    RepoDataRecord,
    TrustedRoot,
    VerificationPolicy,
    verify_attestation,
)
from rattler.exceptions import AttestationError

FIXTURES = Path(__file__).with_name("fixtures") / "rattler"


@pytest.fixture
def rattler_record(rattler_manifest: dict[str, str], tmp_path: Path) -> RepoDataRecord:
    record = asyncio.run(
        RepoDataRecord.from_package_archive(
            FIXTURES / rattler_manifest["package_filename"]
        )
    )
    assert record.sha256 == bytes.fromhex(rattler_manifest["package_sha256"])
    record.url = (tmp_path / record.file_name).as_uri()
    record.channel = rattler_manifest["target_channel"]
    record.attestations_sha256 = bytes.fromhex(rattler_manifest["sidecar_sha256"])
    return record


@pytest.fixture
def rattler_sidecar(
    rattler_manifest: dict[str, str], rattler_record: RepoDataRecord, tmp_path: Path
) -> Path:
    path = tmp_path / (
        f"{rattler_record.file_name}.sigs.{rattler_manifest['sidecar_sha256']}"
    )
    path.write_bytes((FIXTURES / rattler_manifest["sidecar_filename"]).read_bytes())
    return path


@pytest.fixture
def rattler_root(rattler_manifest: dict[str, str]) -> TrustedRoot:
    return TrustedRoot.from_path(FIXTURES / rattler_manifest["trusted_root_filename"])


def test_py_rattler_verifies_local_evidence_against_configured_trusted_root(
    rattler_manifest: dict[str, str],
    rattler_record: RepoDataRecord,
    rattler_sidecar: Path,
    rattler_root: TrustedRoot,
) -> None:
    assert rattler_sidecar.is_file()
    # Both the sidecar and trust material are local. Passing the root prevents
    # the native verifier from fetching production trust material through TUF.
    outcome = asyncio.run(
        verify_attestation(
            rattler_record,
            VerificationPolicy.require(channel_check=ChannelCheck.REQUIRE),
            trusted_root=rattler_root,
        )
    )

    assert outcome.is_verified
    assert outcome.warnings == []
    evidence = outcome.attestation
    assert evidence is not None
    assert evidence.index == 0
    assert evidence.identity == rattler_manifest["identity"]
    assert evidence.issuer == rattler_manifest["issuer"]
    assert evidence.target_channel == rattler_manifest["target_channel"]
    assert evidence.checks.certificate_chain
    assert evidence.checks.signed_certificate_timestamp
    assert evidence.checks.transparency_log
    assert evidence.checks.inclusion_proof


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("file_name", "different-1-0.conda"),
        ("sha256", bytes(32)),
        ("channel", "https://prefix.dev/another-channel"),
    ],
    ids=["filename", "digest", "channel"],
)
def test_py_rattler_rejects_mismatched_artifact_or_channel(
    rattler_record: RepoDataRecord,
    rattler_sidecar: Path,
    rattler_root: TrustedRoot,
    field: str,
    replacement: str | bytes,
) -> None:
    setattr(rattler_record, field, replacement)

    with pytest.raises(AttestationError):
        asyncio.run(
            verify_attestation(
                rattler_record,
                VerificationPolicy.require(channel_check=ChannelCheck.REQUIRE),
                trusted_root=rattler_root,
            )
        )


@pytest.mark.parametrize("valid_position", [None, 0, 1], ids=["none", "first", "last"])
def test_py_rattler_accepts_valid_evidence_beside_invalid_signature(
    rattler_record: RepoDataRecord,
    rattler_sidecar: Path,
    rattler_root: TrustedRoot,
    valid_position: int | None,
) -> None:
    valid = json.loads(rattler_sidecar.read_bytes())[0]
    invalid = json.loads(rattler_sidecar.read_bytes())[0]
    signature = invalid["dsseEnvelope"]["signatures"][0]
    signature_bytes = bytearray(base64.b64decode(signature["sig"]))
    signature_bytes[-1] ^= 1
    signature["sig"] = base64.b64encode(signature_bytes).decode()
    bundles = [invalid]
    if valid_position is not None:
        bundles.insert(valid_position, valid)
    body = json.dumps(bundles).encode()
    rattler_record.attestations_sha256 = hashlib.sha256(body).digest()
    rattler_sidecar.with_name(
        f"{rattler_record.file_name}.sigs.{hashlib.sha256(body).hexdigest()}"
    ).write_bytes(body)

    verification = verify_attestation(
        rattler_record,
        VerificationPolicy.require(channel_check=ChannelCheck.REQUIRE),
        trusted_root=rattler_root,
    )
    if valid_position is None:
        with pytest.raises(AttestationError):
            asyncio.run(verification)
    else:
        outcome = asyncio.run(verification)
        assert outcome.is_verified
        assert outcome.attestation is not None
        assert outcome.attestation.index == valid_position


@pytest.mark.parametrize(
    "malformation", ["truncated", "single-bundle", "empty", "malformed-sibling"]
)
def test_py_rattler_rejects_malformed_sidecar(
    rattler_record: RepoDataRecord,
    rattler_sidecar: Path,
    rattler_root: TrustedRoot,
    malformation: str,
) -> None:
    body = rattler_sidecar.read_bytes()
    if malformation == "truncated":
        body = body[: len(body) // 2]
    elif malformation == "single-bundle":
        body = json.dumps(json.loads(body)[0]).encode()
    elif malformation == "empty":
        body = b"[]"
    else:
        body = json.dumps([*json.loads(body), {}]).encode()
    rattler_record.attestations_sha256 = hashlib.sha256(body).digest()
    rattler_sidecar.with_name(
        f"{rattler_record.file_name}.sigs.{hashlib.sha256(body).hexdigest()}"
    ).write_bytes(body)

    with pytest.raises(AttestationError, match="malformed"):
        asyncio.run(
            verify_attestation(
                rattler_record,
                VerificationPolicy.require(),
                trusted_root=rattler_root,
            )
        )


@pytest.mark.parametrize("failure", ["digest", "missing", "unadvertised"])
def test_py_rattler_never_falls_back_to_adjacent_prefix_sidecar(
    rattler_record: RepoDataRecord,
    rattler_sidecar: Path,
    rattler_root: TrustedRoot,
    failure: str,
) -> None:
    body = rattler_sidecar.read_bytes()
    rattler_sidecar.with_name(f"{rattler_record.file_name}.v0.sigs").write_bytes(body)
    if failure == "digest":
        rattler_sidecar.write_bytes(body + b"\n")
    elif failure == "missing":
        rattler_sidecar.unlink()
    else:
        rattler_record.attestations_sha256 = None

    with pytest.raises(AttestationError):
        asyncio.run(
            verify_attestation(
                rattler_record,
                VerificationPolicy.require(),
                trusted_root=rattler_root,
            )
        )


@pytest.mark.parametrize(
    "invalid_digest", [b"", bytes(31), bytes(33)], ids=["empty", "short", "long"]
)
def test_py_rattler_rejects_invalid_advertised_digest(
    rattler_record: RepoDataRecord, invalid_digest: bytes
) -> None:
    with pytest.raises(ValueError, match="Expected a 32 byte SHA256 digest"):
        rattler_record.attestations_sha256 = invalid_digest


def test_py_rattler_rejects_untrusted_signing_certificate(
    rattler_manifest: dict[str, str],
    rattler_record: RepoDataRecord,
    rattler_sidecar: Path,
) -> None:
    root = json.loads(
        (FIXTURES / rattler_manifest["trusted_root_filename"]).read_bytes()
    )
    root["certificateAuthorities"] = []

    with pytest.raises(AttestationError):
        asyncio.run(
            verify_attestation(
                rattler_record,
                VerificationPolicy.require(),
                trusted_root=TrustedRoot.from_json(json.dumps(root)),
            )
        )
