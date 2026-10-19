from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest
from conda.base.context import reset_context

import conda_sigstore.cli.verify as cli_verify
from conda_sigstore.evidence import (
    Sidecar,
    SignerIdentity,
    VerificationResult,
    VerificationStatus,
    VerifiedEvidence,
)
from conda_sigstore.exceptions import CondaSigstoreError, TransportError


@pytest.fixture
def rattler_publication(tmp_path, monkeypatch, rattler_manifest):
    fixtures = Path(__file__).parents[1] / "fixtures" / "rattler"
    artifact = tmp_path / rattler_manifest["package_filename"]
    artifact.write_bytes((fixtures / rattler_manifest["package_filename"]).read_bytes())
    bundle = json.loads(
        (fixtures / rattler_manifest["sidecar_filename"]).read_text(encoding="utf-8")
    )[0]
    bundle_path = tmp_path / f"{artifact.name}.sigstore.json"
    bundle_path.write_text(json.dumps(bundle) + "\n", encoding="utf-8")
    condarc = tmp_path / "condarc"
    condarc.write_text(
        json.dumps(
            {
                "plugins": {
                    "conda_sigstore": {
                        "trust_config": str(
                            fixtures / rattler_manifest["client_trust_config_filename"]
                        )
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def fail_network(*args, **kwargs):
        pytest.fail("publication verification must use frozen local trust material")

    with monkeypatch.context() as patch:
        patch.setenv("CONDARC", str(condarc))
        patch.setenv("CONDA_OFFLINE", "true")
        patch.setattr(socket, "getaddrinfo", fail_network)
        patch.setattr(socket.socket, "connect", fail_network)
        patch.setattr(socket.socket, "connect_ex", fail_network)
        yield artifact, bundle_path
    reset_context()


@pytest.mark.parametrize(
    ("change", "expected_status"),
    [
        ("valid", "verified"),
        ("artifact-bytes", "invalid"),
        ("channel", "invalid"),
        ("identity", "untrusted-identity"),
    ],
)
def test_verify_publication_bundle_requires_exact_artifact_channel_and_signer(
    rattler_publication,
    rattler_manifest,
    conda_cli,
    change,
    expected_status,
) -> None:
    artifact, bundle_path = rattler_publication
    channel = rattler_manifest["target_channel"]
    identity = rattler_manifest["identity"]
    issuer = rattler_manifest["issuer"]
    if change == "artifact-bytes":
        artifact.write_bytes(artifact.read_bytes() + b"changed")
    elif change == "channel":
        channel = "https://conda.anaconda.org/another-channel"
    elif change == "identity":
        identity = "https://github.com/example/project/.github/workflows/release.yml"
    stdout, stderr, exit_code = conda_cli(
        "sigstore",
        "verify",
        artifact,
        "--bundle",
        bundle_path,
        "--channel",
        channel,
        "--cert-identity",
        identity,
        "--cert-oidc-issuer",
        issuer,
        "--json",
    )

    assert exit_code == (0 if change == "valid" else 1)
    assert stderr == ""
    report = json.loads(stdout)
    assert report["status"] == expected_status
    assert report["artifact"] == artifact.name
    if change == "valid":
        assert report["artifact_sha256"] == rattler_manifest["package_sha256"]
        assert report["evidence"][0]["identity"] == identity
        assert report["authorization"] == "verified"


@pytest.mark.parametrize("output_option", [("--json",), ("--console", "json")])
def test_verify_json_passes_explicit_signer_requirement(
    monkeypatch, tmp_path, capsys, sigstore_parser, rich_console, output_option
) -> None:
    artifact = tmp_path / "demo-1-0.conda"
    artifact.write_bytes(b"package")
    trust_config = tmp_path / "trust.json"
    configured = SimpleNamespace(
        max_sidecar_bytes=1024,
        trust_config=trust_config,
    )
    sidecar = Sidecar("cd" * 32, ("{}",))
    captured = {}

    class FakeSidecarTransport:
        def __init__(self, *, max_bytes):
            captured["max_bytes"] = max_bytes

        def load_input(self, source):
            captured["bundle_source"] = source
            return sidecar

    def verify_artifact(artifact_path, loaded, *, verifier, channel, expected_signer):
        captured.update(
            artifact=artifact_path,
            sidecar=loaded,
            verifier=verifier,
            channel=channel,
            expected_signer=expected_signer,
        )
        result = VerificationResult(
            status=VerificationStatus.VERIFIED,
            artifact=artifact_path.name,
            artifact_sha256="ab" * 32,
            sidecar_sha256=loaded.sha256,
            channel=channel,
            evidence=(
                VerifiedEvidence(
                    bundle_index=0,
                    signer=SignerIdentity(
                        "publisher@example.org",
                        "https://issuer.example",
                    ),
                    predicate_type="https://example.org/predicate",
                    verified=True,
                    timestamps=("2026-08-10T12:00:00Z",),
                ),
            ),
            expected_signer=expected_signer,
        )
        captured["result"] = result
        return result

    monkeypatch.setattr(
        cli_verify.SigstoreSettings,
        "current",
        classmethod(lambda cls: configured),
    )
    monkeypatch.setattr(cli_verify, "SidecarTransport", FakeSidecarTransport)
    monkeypatch.setattr(cli_verify, "verify_artifact", verify_artifact)
    args = sigstore_parser.parse_args(
        [
            "verify",
            str(artifact),
            "--bundle",
            "bundle.json",
            "--channel",
            "https://user:password@example.test/t/super-secret/channel",
            "--cert-identity",
            "publisher@example.org",
            "--cert-oidc-issuer",
            "https://issuer.example",
            *output_option,
        ]
    )

    assert cli_verify.execute_verify(args, console=rich_console) == 0
    captured_output = capsys.readouterr()
    output = captured_output.out
    report = json.loads(output)
    assert report == captured["result"].to_dict()
    expected_output = json.dumps(
        captured["result"].to_dict(),
        indent=2,
        sort_keys=True,
    )
    assert output == f"{expected_output}\n"
    assert captured_output.err == ""
    assert rich_console.file.getvalue() == ""
    assert report["authorization"] == "verified"
    assert report["sidecar_sha256"] == sidecar.sha256
    assert report["expected_signer"] == {
        "identity": "publisher@example.org",
        "issuer": "https://issuer.example",
    }
    assert report["evidence"][0]["identity"] == "publisher@example.org"
    assert report["evidence"][0]["issuer"] == "https://issuer.example"
    assert report["evidence"][0]["verified"] is True
    assert "authorized" not in report["evidence"][0]
    assert captured["bundle_source"] == "bundle.json"
    assert captured["max_bytes"] == 1024
    assert captured["artifact"] == artifact
    assert captured["sidecar"] is sidecar
    assert captured["verifier"].trust_config == trust_config
    assert captured["channel"] == "https://example.test/channel"
    assert captured["expected_signer"].identity == "publisher@example.org"
    assert captured["expected_signer"].issuer == "https://issuer.example"
    assert "password" not in output
    assert "super-secret" not in output


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        (VerificationStatus.VERIFIED, 0),
        (VerificationStatus.INVALID, 1),
    ],
)
def test_verify_human_output_and_exit_status(
    monkeypatch,
    tmp_path,
    capsys,
    sigstore_parser,
    rich_console,
    status,
    expected_exit,
) -> None:
    artifact = tmp_path / "demo[1]-1-0.conda"
    artifact.write_bytes(b"package")
    result = VerificationResult(
        status=status,
        artifact=artifact.name,
        artifact_sha256="ab" * 32,
        evidence=(
            VerifiedEvidence(
                bundle_index=0,
                signer=SignerIdentity(
                    "publisher@example.org",
                    "https://issuer.example",
                ),
                predicate_type="https://example.org/predicate",
                verified=True,
            ),
        ),
    )

    class FakeSidecarTransport:
        def __init__(self, *, max_bytes):
            pass

        def load_input(self, source):
            return Sidecar("cd" * 32, ("{}",))

    monkeypatch.setattr(
        cli_verify.SigstoreSettings,
        "current",
        classmethod(
            lambda cls: SimpleNamespace(max_sidecar_bytes=1024, trust_config=None)
        ),
    )
    monkeypatch.setattr(cli_verify, "SidecarTransport", FakeSidecarTransport)
    monkeypatch.setattr(cli_verify, "verify_artifact", lambda *args, **kwargs: result)
    args = sigstore_parser.parse_args(
        ["verify", str(artifact), "--bundle", "bundle.json"]
    )

    assert cli_verify.execute_verify(args, console=rich_console) == expected_exit
    output = rich_console.file.getvalue()
    assert artifact.name in output
    assert status.value in output
    assert "publisher@example.org" in output
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--cert-identity", "publisher@example.org"),
        ("--cert-oidc-issuer", "https://issuer.example"),
    ],
)
def test_verify_requires_identity_and_issuer_together(
    tmp_path, option, value, sigstore_parser
) -> None:
    artifact = tmp_path / "demo-1-0.conda"
    artifact.write_bytes(b"package")
    args = sigstore_parser.parse_args(
        [
            "verify",
            str(artifact),
            "--bundle",
            "bundle.json",
            option,
            value,
        ]
    )

    with pytest.raises(
        CondaSigstoreError,
        match="--cert-identity and --cert-oidc-issuer must be used together",
    ):
        cli_verify.execute_verify(args)


def test_verify_preserves_transport_failure_code(
    monkeypatch, tmp_path, sigstore_parser
) -> None:
    artifact = tmp_path / "demo-1-0.conda"
    artifact.write_bytes(b"package")

    class FailingSidecarTransport:
        def __init__(self, *, max_bytes):
            pass

        def load_input(self, source):
            raise TransportError("invalid-sidecar", "bundle is malformed")

    monkeypatch.setattr(
        cli_verify.SigstoreSettings,
        "current",
        classmethod(
            lambda cls: SimpleNamespace(max_sidecar_bytes=1024, trust_config=None)
        ),
    )
    monkeypatch.setattr(cli_verify, "SidecarTransport", FailingSidecarTransport)
    args = sigstore_parser.parse_args(
        ["verify", str(artifact), "--bundle", "bundle.json"]
    )

    with pytest.raises(CondaSigstoreError, match="bundle is malformed") as error:
        cli_verify.execute_verify(args)

    assert error.value.code == "invalid-sidecar"
