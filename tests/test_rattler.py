"""Hermetic verification of the public package used by Rattler's tests."""

from __future__ import annotations

import base64
import hashlib
import json
import socket
from pathlib import Path

import pytest

from conda_sigstore.evidence import SignerIdentity, VerificationStatus
from conda_sigstore.exceptions import TransportError
from conda_sigstore.source_attestations import (
    EmbeddedSourceBundle,
    SourceAttestationRequirement,
)
from conda_sigstore.statements import PublishStatement
from conda_sigstore.transport import SidecarTransport
from conda_sigstore.verification import SigstoreVerifier, verify_bundles

FIXTURES = Path(__file__).with_name("fixtures") / "rattler"


@pytest.fixture(autouse=True)
def deny_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args, **kwargs):
        pytest.fail(
            "the frozen Rattler interoperability tests must not use the network"
        )

    monkeypatch.setattr(socket, "getaddrinfo", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_network)


@pytest.fixture(scope="module")
def rattler_body(rattler_manifest: dict[str, str]) -> bytes:
    return (FIXTURES / rattler_manifest["sidecar_filename"]).read_bytes()


@pytest.fixture
def rattler_verifier(rattler_manifest: dict[str, str]) -> SigstoreVerifier:
    return SigstoreVerifier(
        offline=True,
        trust_config=FIXTURES / rattler_manifest["client_trust_config_filename"],
    )


@pytest.mark.parametrize(
    "component",
    ["package", "sidecar", "trusted_root", "signing_config", "client_trust_config"],
)
def test_rattler_fixture_matches_recorded_digest(
    rattler_manifest: dict[str, str], component: str
) -> None:
    path = FIXTURES / rattler_manifest[f"{component}_filename"]
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == rattler_manifest[f"{component}_sha256"]
    )


@pytest.mark.parametrize("transport_kind", ["repodata", "prefix"])
def test_rattler_publication_verifies_through_supported_transports(
    rattler_manifest: dict[str, str],
    rattler_body: bytes,
    rattler_verifier: SigstoreVerifier,
    transport_kind: str,
) -> None:
    requests: list[tuple[str, int]] = []

    def fetch(url: str, limit: int) -> bytes:
        requests.append((url, limit))
        return rattler_body

    transport = SidecarTransport(max_bytes=len(rattler_body), fetcher=fetch)
    if transport_kind == "repodata":
        suffix = f".sigs.{rattler_manifest['sidecar_sha256']}"
        sidecar = transport.load_repodata(
            rattler_manifest["package_url"], rattler_manifest["sidecar_sha256"]
        )
    else:
        suffix = ".v0.sigs"
        sidecar = transport.load_prefix(rattler_manifest["package_url"])
    assert requests == [(rattler_manifest["package_url"] + suffix, len(rattler_body))]
    assert sidecar.prefix_sidecar == (transport_kind == "prefix")
    assert sidecar.sha256 == rattler_manifest["sidecar_sha256"]

    result = verify_bundles(
        sidecar,
        artifact_name=rattler_manifest["package_filename"],
        artifact_sha256=rattler_manifest["package_sha256"],
        channel=rattler_manifest["target_channel"],
        verifier=rattler_verifier,
    )

    assert result.status is VerificationStatus.VERIFIED, result.to_dict()
    assert result.failures == ()
    assert len(result.evidence) == 1
    evidence = result.evidence[0]
    assert evidence.verified
    assert evidence.signer == SignerIdentity(
        rattler_manifest["identity"], rattler_manifest["issuer"]
    )
    assert evidence.predicate_type == PublishStatement.PREDICATE_TYPE
    assert evidence.details["target_channel"] == rattler_manifest["target_channel"]
    assert result.to_dict()["authorization"] == "not-evaluated"


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("artifact_name", "different-1-0.conda", "subject filename"),
        ("artifact_sha256", "00" * 32, "subject sha256"),
        ("channel", "https://prefix.dev/another-channel", "targetChannel"),
    ],
    ids=["filename", "digest", "channel"],
)
def test_rattler_publication_rejects_mismatched_artifact_or_channel(
    rattler_manifest: dict[str, str],
    rattler_body: bytes,
    rattler_verifier: SigstoreVerifier,
    field: str,
    replacement: str,
    message: str,
) -> None:
    inputs = {
        "artifact_name": rattler_manifest["package_filename"],
        "artifact_sha256": rattler_manifest["package_sha256"],
        "channel": rattler_manifest["target_channel"],
    }
    inputs[field] = replacement

    result = verify_bundles(
        SidecarTransport.parse(rattler_body),
        verifier=rattler_verifier,
        **inputs,
    )

    assert result.status is VerificationStatus.INVALID
    assert result.failures[0].code == "invalid-cep27"
    assert message in result.failures[0].message
    assert len(result.evidence) == 1
    assert not result.evidence[0].verified


@pytest.mark.parametrize("valid_position", [None, 0, 1], ids=["none", "first", "last"])
@pytest.mark.parametrize("invalid_kind", ["signature", "malformed"])
def test_rattler_publication_preserves_valid_evidence_beside_invalid_signature(
    rattler_manifest: dict[str, str],
    rattler_body: bytes,
    rattler_verifier: SigstoreVerifier,
    valid_position: int | None,
    invalid_kind: str,
) -> None:
    valid_bundle = json.loads(rattler_body)[0]
    invalid_bundle = json.loads(rattler_body)[0]
    payload = json.loads(base64.b64decode(invalid_bundle["dsseEnvelope"]["payload"]))
    payload["subject"][0]["digest"]["sha256"] = "00" * 32
    invalid_bundle["dsseEnvelope"]["payload"] = base64.b64encode(
        json.dumps(payload).encode()
    ).decode()
    bundles = [invalid_bundle if invalid_kind == "signature" else {}]
    if valid_position is not None:
        bundles.insert(valid_position, valid_bundle)

    result = verify_bundles(
        SidecarTransport.parse(json.dumps(bundles).encode()),
        artifact_name=rattler_manifest["package_filename"],
        artifact_sha256=rattler_manifest["package_sha256"],
        channel=rattler_manifest["target_channel"],
        verifier=rattler_verifier,
    )

    if valid_position is None:
        assert result.status is VerificationStatus.INVALID
        assert result.evidence == ()
    else:
        assert result.status is VerificationStatus.VERIFIED, result.to_dict()
        assert len(result.evidence) == 1
        assert result.evidence[0].bundle_index == valid_position
        assert result.evidence[0].verified
    assert result.failures[0].code == "invalid-bundle"
    assert result.failures[0].bundle_index == (0 if valid_position != 0 else 1)


@pytest.mark.parametrize("transport_kind", ["repodata", "prefix"])
@pytest.mark.parametrize("malformation", ["truncated", "single-bundle"])
def test_rattler_transport_rejects_malformed_sidecars(
    rattler_manifest: dict[str, str],
    rattler_body: bytes,
    transport_kind: str,
    malformation: str,
) -> None:
    body = (
        rattler_body[: len(rattler_body) // 2]
        if malformation == "truncated"
        else json.dumps(json.loads(rattler_body)[0]).encode()
    )
    transport = SidecarTransport(fetcher=lambda _url, _limit: body)
    if transport_kind == "repodata":
        with pytest.raises(TransportError) as raised:
            transport.load_repodata(
                rattler_manifest["package_url"], hashlib.sha256(body).hexdigest()
            )
    else:
        with pytest.raises(TransportError) as raised:
            transport.load_prefix(rattler_manifest["package_url"])
    assert raised.value.code == "invalid-sidecar"


def test_rattler_repodata_transport_rejects_changed_sidecar_bytes(
    rattler_manifest: dict[str, str], rattler_body: bytes
) -> None:
    # Whitespace preserves the signed bundle but changes the advertised bytes.
    transport = SidecarTransport(fetcher=lambda _url, _limit: rattler_body + b"\n")
    with pytest.raises(TransportError) as raised:
        transport.load_repodata(
            rattler_manifest["package_url"], rattler_manifest["sidecar_sha256"]
        )
    assert raised.value.code == "digest-mismatch"


@pytest.mark.parametrize(
    "transparency_material",
    [
        "complete",
        "missing-body",
        "empty-body",
        "missing-checkpoint",
        "tampered-checkpoint",
    ],
)
def test_source_audit_requires_complete_authenticated_transparency_material(
    tmp_path: Path,
    rattler_manifest: dict[str, str],
    rattler_body: bytes,
    rattler_verifier: SigstoreVerifier,
    transparency_material: str,
) -> None:
    # This captured CEP 27 bundle tests source verification, not PEP 740 conversion.
    bundle = json.loads(rattler_body)[0]
    entry = bundle["verificationMaterial"]["tlogEntries"][0]
    if transparency_material == "missing-body":
        del entry["canonicalizedBody"]
    elif transparency_material == "empty-body":
        entry["canonicalizedBody"] = ""
    elif transparency_material == "missing-checkpoint":
        del entry["inclusionProof"]["checkpoint"]
    elif transparency_material == "tampered-checkpoint":
        checkpoint = entry["inclusionProof"]["checkpoint"]
        lines = checkpoint["envelope"].splitlines(keepends=True)
        lines[1] = f"{int(lines[1]) + 1}\n"
        checkpoint["envelope"] = "".join(lines)
    body = json.dumps(bundle).encode()
    embedded = tmp_path / "attestations" / "source.sigstore.json"
    embedded.parent.mkdir()
    embedded.write_bytes(body)
    publisher = SignerIdentity(rattler_manifest["identity"], rattler_manifest["issuer"])
    requirement = SourceAttestationRequirement(
        source_index=0,
        source_sha256=rattler_manifest["package_sha256"],
        publishers=(publisher,),
        predicate_type=PublishStatement.PREDICATE_TYPE,
        # Rehash the modified bundle to reach the transparency-log checks.
        bundles=(
            EmbeddedSourceBundle(
                path="attestations/source.sigstore.json",
                sha256=hashlib.sha256(body).hexdigest(),
            ),
        ),
    )

    result = requirement.audit(
        tmp_path,
        verifier=rattler_verifier,
        max_bytes=len(body),
    )

    if transparency_material == "complete":
        assert result["status"] == "verified", result
        assert result["matched_publishers"] == [publisher.to_dict()]
        assert result["bundles"][0]["status"] == "verified"
        assert result["bundles"][0]["predicate_type"] == PublishStatement.PREDICATE_TYPE
    else:
        assert result["status"] == "invalid", result
        assert result["matched_publishers"] == []
        assert result["bundles"][0]["status"] == "invalid"
        assert result["bundles"][0]["failure"]
