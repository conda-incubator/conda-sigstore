from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import TYPE_CHECKING

import pytest
from conda.base.context import reset_context
from conda.gateways.disk.read import compute_sum
from rattler import (
    ChannelCheck,
    PackageRecord,
    RepoDataRecord,
    TrustedRoot,
    VerificationPolicy,
    verify_attestation,
)

from conda_sigstore.attestation import create_attestation
from conda_sigstore.evidence import Sidecar, SignerIdentity, VerificationStatus
from conda_sigstore.statements import PublishStatement
from conda_sigstore.verification import SigstoreVerifier, verify_bundles

if TYPE_CHECKING:
    from pathlib import Path

    from conda.testing.fixtures import CondaCLIFixture

PREFIX_ARTIFACT_NAME = "signed-package-2.1.0-hb0f4dca_0.conda"
PREFIX_ARTIFACT_SHA256 = (
    "3862a3677d33a45134a2ce3452b23f8f7459fe581cefbc3818272648cd987cfb"
)
PREFIX_SIDECAR_SHA256 = (
    "823d6078e08809cdd85e40cf2d55a83f86226c9d9b6d4134d42ecf80456e55e1"
)
PREFIX_CHANNEL = "https://prefix.dev/sigstore-example"
PREFIX_IDENTITY = (
    "https://github.com/prefix-dev/sigstore-example/"
    ".github/workflows/action.yaml@refs/heads/main"
)
GITHUB_ISSUER = "https://token.actions.githubusercontent.com"
STAGING_CHANNEL = "https://staging.example.invalid/conda-sigstore"


@pytest.mark.live_interop
@pytest.mark.skipif(
    os.environ.get("CONDA_SIGSTORE_PREFIX_INTEROP") != "1",
    reason="set CONDA_SIGSTORE_PREFIX_INTEROP=1 to run",
)
def test_prefix_strict_install_reports_authenticated_signer(
    conda_cli: CondaCLIFixture,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prefix = tmp_path / "prefix"
    monkeypatch.setenv("CONDA_PKGS_DIRS", str(tmp_path / "pkgs"))
    monkeypatch.setenv("CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE", "true")
    reset_context()

    stdout, stderr, code = conda_cli(
        "create",
        "--yes",
        "--json",
        "--prefix",
        prefix,
        "--override-channels",
        "--channel",
        PREFIX_CHANNEL,
        "--subdir",
        "linux-64",
        "--solver",
        "classic",
        "--no-deps",
        "signed-package=2.1.0=hb0f4dca_0",
    )
    assert code == 0
    assert json.loads(stdout)["success"]
    assert stderr == ""

    stdout, stderr, code = conda_cli(
        "sigstore",
        "audit",
        "--prefix",
        prefix,
        "--prefix-sidecars",
        "--json",
    )
    assert code == 0
    assert stderr == ""
    report = json.loads(stdout)
    assert report["version"] == 1
    assert report["prefix"] == str(prefix.resolve())
    assert len(report["packages"]) == 1
    package = report["packages"][0]
    assert package["artifact"] == PREFIX_ARTIFACT_NAME
    assert package["artifact_sha256"] == PREFIX_ARTIFACT_SHA256
    assert package["sidecar_sha256"] == PREFIX_SIDECAR_SHA256
    assert package["channel"] == PREFIX_CHANNEL
    assert package["status"] == VerificationStatus.VERIFIED.value
    assert package["authorization"] == "not-evaluated"
    assert package["prefix_sidecar"] is True
    assert len(package["evidence"]) == 1
    evidence = package["evidence"][0]
    assert evidence["identity"] == PREFIX_IDENTITY
    assert evidence["issuer"] == GITHUB_ISSUER
    assert evidence["predicate_type"] == PublishStatement.PREDICATE_TYPE
    assert evidence["verified"] is True
    assert "authorized" not in evidence


@pytest.mark.live_interop
@pytest.mark.skipif(
    os.environ.get("CONDA_SIGSTORE_STAGING_INTEROP") != "1",
    reason="set CONDA_SIGSTORE_STAGING_INTEROP=1 to run",
)
def test_sigstore_staging_round_trip_reports_authenticated_signer(tmp_path) -> None:
    from sigstore.models import ClientTrustConfig

    expected_identity = os.environ["CONDA_SIGSTORE_STAGING_IDENTITY"]
    trust_config = ClientTrustConfig.staging()
    trust_config_path = tmp_path / "sigstore-staging.json"
    # sigstore-python 4.5 has no public ClientTrustConfig serializer. This
    # live-only round trip needs its exact combined trust-root and signing JSON.
    config_json = trust_config._inner.to_json()
    trust_config_path.write_text(config_json, encoding="utf-8")
    trusted_root_path = tmp_path / "trusted-root.json"
    trusted_root_path.write_text(
        json.dumps(json.loads(config_json)["trustedRoot"]), encoding="utf-8"
    )

    artifact = tmp_path / "conda-sigstore-staging-0-0.conda"
    artifact.write_bytes(b"conda-sigstore staging interoperability\n")
    output = create_attestation(
        artifact,
        target_channel=STAGING_CHANNEL,
        trust_config_path=trust_config_path,
    )
    bundle = output.read_text(encoding="utf-8").strip()
    sidecar = Sidecar(
        sha256=hashlib.sha256(bundle.encode()).hexdigest(),
        bundles=(bundle,),
    )

    artifact_sha256 = compute_sum(artifact, "sha256")
    result = verify_bundles(
        sidecar,
        artifact_name=artifact.name,
        artifact_sha256=artifact_sha256,
        verifier=SigstoreVerifier(trust_config=trust_config_path),
        channel=STAGING_CHANNEL,
    )

    assert result.status is VerificationStatus.VERIFIED
    assert result.evidence[0].signer == SignerIdentity(expected_identity, GITHUB_ISSUER)
    assert result.evidence[0].verified
    assert result.to_dict()["authorization"] == "not-evaluated"
    assert "authorized" not in result.evidence[0].to_dict()

    sidecar_bytes = json.dumps([json.loads(bundle)]).encode()
    sidecar_sha256 = hashlib.sha256(sidecar_bytes).digest()
    artifact.with_name(f"{artifact.name}.sigs.{sidecar_sha256.hex()}").write_bytes(
        sidecar_bytes
    )
    record = RepoDataRecord(
        PackageRecord(
            name="conda-sigstore-staging",
            version="0",
            build="0",
            build_number=0,
            subdir="noarch",
            sha256=bytes.fromhex(artifact_sha256),
            attestations_sha256=sidecar_sha256,
        ),
        artifact.name,
        artifact.as_uri(),
        STAGING_CHANNEL,
    )
    native_result = asyncio.run(
        verify_attestation(
            record,
            VerificationPolicy.require(channel_check=ChannelCheck.REQUIRE),
            trusted_root=TrustedRoot.from_path(trusted_root_path),
        )
    )

    assert native_result.is_verified
    native_attestation = native_result.attestation
    assert native_attestation is not None
    assert native_attestation.identity == expected_identity
    assert native_attestation.issuer == GITHUB_ISSUER
    assert native_attestation.target_channel == STAGING_CHANNEL
    assert native_attestation.index == 0
    assert native_attestation.checks.certificate_chain
    assert native_attestation.checks.signed_certificate_timestamp
    assert native_attestation.checks.transparency_log
    assert native_attestation.checks.inclusion_proof
