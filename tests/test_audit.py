from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from conda.exceptions import CondaError

from conda_sigstore.audit import EnvironmentAuditor
from conda_sigstore.cache import DigestCache
from conda_sigstore.evidence import (
    SignerIdentity,
    VerificationResult,
    VerificationStatus,
)
from conda_sigstore.exceptions import (
    BundleVerificationError,
    TransportError,
    TrustMaterialUnavailableError,
)
from conda_sigstore.settings import SigstoreSettings
from conda_sigstore.source_attestations import (
    SourceAttestationRequirement,
    resolve_embedded_file,
)
from conda_sigstore.statements import InTotoStatement, PublishStatement
from conda_sigstore.transport import SidecarTransport
from conda_sigstore.verification import CryptographicVerification

SOURCE_DIGEST = "ab" * 32
PREDICATE_TYPE = "https://example.org/source-publish/v1"
GITHUB_ISSUER = "https://token.actions.githubusercontent.com"


def statement(
    digest: str = SOURCE_DIGEST,
    predicate_type: str = PREDICATE_TYPE,
) -> bytes:
    return json.dumps(
        {
            "_type": InTotoStatement.STATEMENT_TYPE,
            "subject": [{"name": "source.tar.gz", "digest": {"sha256": digest}}],
            "predicateType": predicate_type,
            "predicate": {},
        }
    ).encode()


def indexed_bundle(path: str, body: str) -> dict[str, str]:
    return {
        "path": path,
        "sha256": hashlib.sha256(body.encode()).hexdigest(),
        "predicate_type": "untrusted-recipe-claim",
        "san": "untrusted-recipe-claim",
        "issuer": "untrusted-recipe-claim",
    }


def recipe(
    publishers: list[object],
    bundles: list[object],
    *,
    predicate_type: str | None = PREDICATE_TYPE,
    source_digest: str = SOURCE_DIGEST,
) -> dict[str, object]:
    attestation: dict[str, object] = {
        "publishers": publishers,
        "verified": bundles,
    }
    if predicate_type is not None:
        attestation["predicate_type"] = predicate_type
    return {
        "source": {
            "url": "https://example.org/source.tar.gz",
            "sha256": source_digest,
            "attestation": attestation,
        }
    }


class FakeVerifier:
    def __init__(
        self,
        identities: dict[str, SignerIdentity],
        payloads: dict[str, bytes],
        *,
        payload_type: str = InTotoStatement.PAYLOAD_TYPE,
    ) -> None:
        self.identities = identities
        self.payloads = payloads
        self.payload_type = payload_type

    def verify(self, bundle_json: str) -> CryptographicVerification:
        try:
            identity = self.identities[bundle_json]
        except KeyError:
            raise BundleVerificationError("invalid bundle") from None
        return CryptographicVerification(
            self.payload_type,
            self.payloads[bundle_json],
            identity,
            ("signed-time",),
        )


@pytest.fixture
def installed_records(monkeypatch: pytest.MonkeyPatch):
    import conda.core.prefix_data

    def install(*records: SimpleNamespace) -> None:
        class FakePrefixData:
            def __init__(self, _prefix: Path) -> None:
                pass

            def iter_records(self):
                return iter(records)

        monkeypatch.setattr(conda.core.prefix_data, "PrefixData", FakePrefixData)

    return install


def source_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    rendered_recipe: dict[str, object],
    bundle_files: dict[str, str],
    identities: dict[str, SignerIdentity],
    payloads: dict[str, bytes] | None = None,
    payload_type: str = InTotoStatement.PAYLOAD_TYPE,
    maximum: int = 1024,
) -> list[dict[str, object]]:
    import conda_package_handling.api

    record = SimpleNamespace(fn="pkg-1-0.conda")
    source = tmp_path / "source"
    recipe_root = source / "info" / "recipe"
    recipe_root.mkdir(parents=True)
    (recipe_root / "rendered_recipe.yaml").write_text(json.dumps(rendered_recipe))
    for relative, body in bundle_files.items():
        path = recipe_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    conda_package_handling.api.create(source, None, record.fn, tmp_path)
    archive = tmp_path / record.fn
    package_sha256 = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )

    verifier = FakeVerifier(
        identities,
        payloads or {body: statement() for body in bundle_files.values()},
        payload_type=payload_type,
    )
    auditor = EnvironmentAuditor(
        settings=SigstoreSettings(max_sidecar_bytes=maximum),
        verifier=verifier,
    )
    return auditor.audit_sources(
        record,
        package_verified=True,
        package_sha256=package_sha256,
    )


def test_retained_archive_requires_exact_package_filename(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from conda.core.package_cache_data import PackageCacheData

    wrong = SimpleNamespace(
        fn="pkg-1-0.tar.bz2",
        is_fetched=True,
        package_tarball_full_path=str(tmp_path / "pkg-1-0.tar.bz2"),
    )
    exact = SimpleNamespace(
        fn="pkg-1-0.conda",
        is_fetched=True,
        package_tarball_full_path=str(tmp_path / "pkg-1-0.conda"),
    )
    monkeypatch.setattr(
        PackageCacheData,
        "query_all",
        classmethod(lambda cls, record: iter((wrong, exact))),
    )

    assert EnvironmentAuditor.retained_archive(
        SimpleNamespace(fn="pkg-1-0.conda")
    ) == Path(exact.package_tarball_full_path)


def test_audit_record_reports_digest_only_without_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = SimpleNamespace(
        channel=SimpleNamespace(base_url="https://conda.example.org/team"),
        fn="pkg-1-0.conda",
        name="pkg",
        sha256="ab" * 32,
    )
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: None),
    )

    result = EnvironmentAuditor(
        SigstoreSettings(),
        FakeVerifier({}, {}),
    ).audit_record(record)

    assert result.status is VerificationStatus.RECORD_DIGEST_ONLY
    assert result.artifact_sha256 == "ab" * 32
    assert result.failures[0].code == "record-digest-only"


def test_audit_record_rejects_retained_archive_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "pkg-1-0.conda"
    archive.write_bytes(b"different package")
    record = SimpleNamespace(
        channel=SimpleNamespace(base_url="https://conda.example.org/team"),
        fn=archive.name,
        name="pkg",
        sha256="ab" * 32,
    )
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )

    result = EnvironmentAuditor(
        SigstoreSettings(),
        FakeVerifier({}, {}),
    ).audit_record(record)

    assert result.status is VerificationStatus.INVALID
    assert result.failures[0].code == "artifact-digest-mismatch"


def test_source_audit_requires_verified_package_publication() -> None:
    auditor = EnvironmentAuditor(SigstoreSettings(), FakeVerifier({}, {}))

    report = auditor.audit_sources(
        SimpleNamespace(),
        package_verified=False,
        package_sha256=None,
    )

    assert report[0]["status"] == "evidence-unavailable"
    assert "package publication" in str(report[0]["failure"])


def test_source_audit_requires_retained_archive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: None),
    )
    auditor = EnvironmentAuditor(SigstoreSettings(), FakeVerifier({}, {}))

    report = auditor.audit_sources(
        SimpleNamespace(fn="pkg-1-0.conda"),
        package_verified=True,
        package_sha256="cd" * 32,
    )

    assert report[0]["status"] == "evidence-unavailable"
    assert "archive" in str(report[0]["failure"])


@pytest.mark.parametrize(
    "rendered_publishers", [False, True], ids=["input", "rendered"]
)
def test_requires_every_recipe_publisher_and_ignores_index_claims(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    rendered_publishers: bool,
) -> None:
    first = "bundle-github"
    second = "bundle-gitlab"
    first_path = "attestations/source.tar.gz.0.sigstore.json"
    second_path = "attestations/source.tar.gz.1.sigstore.json"
    github = SignerIdentity(
        "https://github.com/EXAMPLE/Project/.github/workflows/release.yml@refs/tags/v1",
        GITHUB_ISSUER,
    )
    gitlab = SignerIdentity(
        "https://gitlab.com/group/project/-/jobs/123",
        "https://gitlab.com",
    )
    publishers = (
        [
            {
                "provider": "github",
                "owner": "example",
                "repo": "project",
                "ref_constraint": None,
            },
            {
                "provider": "gitlab",
                "owner": "group",
                "repo": "project",
                "ref_constraint": None,
            },
        ]
        if rendered_publishers
        else ["github:example/project", "gitlab:group/project"]
    )
    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe(
            publishers,
            [indexed_bundle(first_path, first), indexed_bundle(second_path, second)],
        ),
        bundle_files={first_path: first, second_path: second},
        identities={first: github, second: gitlab},
    )[0]

    assert report["status"] == "verified"
    assert len(report["matched_publishers"]) == 2
    assert report["bundles"][0]["identity"] == github.identity
    assert report["bundles"][0]["predicate_type"] == PREDICATE_TYPE
    assert "authorization" not in report["bundles"][0]


def test_rattler_rendered_source_without_retained_bundle_is_missing(
    monkeypatch, tmp_path, rattler_source_recipe
):
    reports = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=rattler_source_recipe,
        bundle_files={},
        identities={},
    )
    assert len(reports) == 1
    report = reports[0]
    assert report["status"] == "missing"
    assert report["source_sha256"] == "a" * 64
    assert report["required_publishers"] == [
        {
            "identity": "https://github.com/example/source-audit-fixture",
            "issuer": GITHUB_ISSUER,
        }
    ]
    assert report["matched_publishers"] == []
    assert report["bundles"] == []


def test_actual_signer_must_match_recipe_publisher(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    body = "bundle"
    path = "attestations/source.tar.gz.0.sigstore.json"
    attacker = SignerIdentity(
        "https://github.com/example/project-evil/.github/workflows/release.yml",
        GITHUB_ISSUER,
    )
    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe(
            ["github:example/project"],
            [indexed_bundle(path, body)],
        ),
        bundle_files={path: body},
        identities={body: attacker},
    )[0]

    assert report["status"] == "untrusted-identity"
    assert report["matched_publishers"] == []


def test_invalid_extra_indexed_bundle_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    good = "good-bundle"
    bad = "malformed-extra"
    good_path = "attestations/source.tar.gz.0.sigstore.json"
    bad_path = "attestations/source.tar.gz.1.sigstore.json"
    identity = SignerIdentity("publisher@example.org", "https://issuer.example")
    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe(
            [identity.to_dict()],
            [indexed_bundle(good_path, good), indexed_bundle(bad_path, bad)],
        ),
        bundle_files={good_path: good, bad_path: bad},
        identities={good: identity},
    )[0]

    assert report["status"] == "invalid"
    assert report["bundles"][0]["status"] == "verified"
    assert report["bundles"][1]["status"] == "invalid"


def test_missing_indexed_bundle_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    body = "missing-bundle"
    path = "attestations/source.tar.gz.0.sigstore.json"
    identity = SignerIdentity("publisher@example.org", "https://issuer.example")
    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe(
            [identity.to_dict()],
            [indexed_bundle(path, body)],
        ),
        bundle_files={},
        identities={},
    )[0]

    assert report["status"] == "missing"
    assert report["bundles"][0]["status"] == "missing"


def test_unavailable_source_trust_is_not_invalid(tmp_path: Path) -> None:
    body = "bundle"
    path = "attestations/source.tar.gz.0.sigstore.json"
    bundle = tmp_path / path
    bundle.parent.mkdir()
    bundle.write_text(body)
    requirement = SourceAttestationRequirement.from_recipe(
        recipe(
            [{"identity": "publisher@example.org", "issuer": "https://issuer"}],
            [indexed_bundle(path, body)],
        )
    )[0]

    class UnavailableVerifier:
        def verify(self, bundle_json: str):
            raise TrustMaterialUnavailableError("offline trust is unavailable")

    report = requirement.audit(
        tmp_path,
        verifier=UnavailableVerifier(),
        max_bytes=1024,
    )

    assert report["status"] == "evidence-unavailable"
    assert report["bundles"][0]["status"] == "evidence-unavailable"
    assert report["bundles"][0]["failure"] == "Sigstore trust material is unavailable"


@pytest.mark.parametrize(
    ("payload_type", "payload", "failure"),
    [
        ("text/plain", statement(), "in-toto"),
        (
            InTotoStatement.PAYLOAD_TYPE,
            statement(predicate_type="https://example.org/other"),
            "predicate type",
        ),
        (
            InTotoStatement.PAYLOAD_TYPE,
            statement(digest="cd" * 32),
            "recipe source",
        ),
    ],
)
def test_enforces_payload_predicate_and_source_binding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload_type: str,
    payload: bytes,
    failure: str,
) -> None:
    body = "bundle"
    path = "attestations/source.tar.gz.0.sigstore.json"
    identity = SignerIdentity("publisher@example.org", "https://issuer.example")
    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe(
            [identity.to_dict()],
            [indexed_bundle(path, body)],
        ),
        bundle_files={path: body},
        identities={body: identity},
        payloads={body: payload},
        payload_type=payload_type,
    )[0]

    assert report["status"] == "invalid"
    assert failure in report["bundles"][0]["failure"]


@pytest.mark.parametrize(
    "path",
    [
        "../attestations/source.sigstore.json",
        "attestations\\source.sigstore.json",
        "/attestations/source.sigstore.json",
        "attestations/nested/source.sigstore.json",
    ],
)
def test_rejects_unsafe_embedded_paths(path: str) -> None:
    rendered = recipe(
        [{"identity": "publisher@example.org", "issuer": "https://issuer.example"}],
        [{"path": path, "sha256": "cd" * 32}],
    )
    with pytest.raises(ValueError, match="verified.path"):
        SourceAttestationRequirement.from_recipe(rendered)


def test_rejects_symlinked_bundle(tmp_path: Path) -> None:
    root = tmp_path / "recipe"
    root.mkdir()
    outside = tmp_path / "outside.sigstore.json"
    outside.write_text("bundle")
    link = root / "attestations"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")

    with pytest.raises(ValueError, match="symlink"):
        resolve_embedded_file(root, "attestations/outside.sigstore.json")


def test_enforces_embedded_bundle_size_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    body = "oversized-bundle"
    path = "attestations/source.tar.gz.0.sigstore.json"
    identity = SignerIdentity("publisher@example.org", "https://issuer.example")
    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe(
            [identity.to_dict()],
            [indexed_bundle(path, body)],
        ),
        bundle_files={path: body},
        identities={body: identity},
        maximum=4,
    )[0]

    assert report["status"] == "invalid"
    assert "exceeds 4 bytes" in report["failure"]


def test_bounds_rendered_recipe_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from conda_sigstore import audit

    body = "bundle"
    path = "attestations/source.tar.gz.0.sigstore.json"
    identity = SignerIdentity("publisher@example.org", "https://issuer.example")
    monkeypatch.setattr(audit, "MAX_RENDERED_RECIPE_BYTES", 32)

    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe(
            [identity.to_dict()],
            [indexed_bundle(path, body)],
        ),
        bundle_files={path: body},
        identities={body: identity},
    )[0]

    assert report["status"] == "invalid"
    assert report["failure"] == "rendered recipe exceeds 32 bytes"


def test_rendered_recipe_parser_failure_does_not_echo_input(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from conda.common.serialize import yaml
    from ruamel.yaml import YAMLError

    secret = "https://user:password@example.org/source.tar.gz"

    def reject_recipe(value: str) -> None:
        raise YAMLError(secret)

    monkeypatch.setattr(yaml, "loads", reject_recipe)
    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe([], []),
        bundle_files={},
        identities={},
    )[0]

    assert report["status"] == "invalid"
    assert report["failure"] == "rendered recipe is not valid YAML"
    assert secret not in str(report)


def test_hashes_archive_before_extraction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from conda_sigstore.source_archive import SourceArchive

    archive = tmp_path / "retained.conda"
    archive.write_bytes(b"changed")
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )
    monkeypatch.setattr(
        SourceArchive,
        "extract_recipe",
        lambda *_args, **_kwargs: pytest.fail("archive must be hashed first"),
    )
    auditor = EnvironmentAuditor(SigstoreSettings(), FakeVerifier({}, {}))

    report = auditor.audit_sources(
        SimpleNamespace(fn="pkg-1-0.conda"),
        package_verified=True,
        package_sha256="cd" * 32,
    )

    assert report[0]["status"] == "invalid"
    assert "verified package digest" in str(report[0]["failure"])


def test_source_audit_inspects_verified_snapshot(monkeypatch, tmp_path):
    from conda_sigstore.source_archive import SourceArchive

    archive = tmp_path / "pkg-1-0.conda"
    extract_recipe = SourceArchive.extract_recipe
    inspected = []

    def inspect_snapshot(snapshot, *args, **kwargs):
        assert snapshot.path != archive
        assert snapshot.filename == archive.name
        assert (
            hashlib.sha256(snapshot.path.read_bytes()).digest()
            == hashlib.sha256(archive.read_bytes()).digest()
        )
        archive.write_bytes(b"replaced after snapshot")
        inspected.append(snapshot.path)
        return extract_recipe(snapshot, *args, **kwargs)

    monkeypatch.setattr(SourceArchive, "extract_recipe", inspect_snapshot)
    body = "bundle"
    path = "attestations/source.sigstore.json"
    report = source_audit(
        monkeypatch,
        tmp_path,
        rendered_recipe=recipe(
            ["github:example/project"],
            [indexed_bundle(path, body)],
        ),
        bundle_files={path: body},
        identities={
            body: SignerIdentity("https://github.com/example/project", GITHUB_ISSUER)
        },
    )

    assert len(inspected) == 1
    assert report[0]["status"] == "verified"
    assert archive.read_bytes() == b"replaced after snapshot"


def test_source_audit_bounds_retained_package_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from conda_sigstore import audit
    from conda_sigstore.source_archive import SourceArchive

    archive = tmp_path / "retained.conda"
    archive.write_bytes(b"oversized")
    monkeypatch.setattr(audit, "MAX_PACKAGE_ARCHIVE_BYTES", 4)
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )
    monkeypatch.setattr(
        SourceArchive,
        "extract_recipe",
        lambda *_args, **_kwargs: pytest.fail("oversized archive must not be parsed"),
    )
    auditor = EnvironmentAuditor(SigstoreSettings(), FakeVerifier({}, {}))

    report = auditor.audit_sources(
        SimpleNamespace(fn="pkg-1-0.conda"),
        package_verified=True,
        package_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )

    assert report[0]["status"] == "evidence-unavailable"
    assert report[0]["failure"] == (
        "the retained package archive exceeds the 4-byte audit limit"
    )


def package_record(
    archive: Path,
    sidecar: bytes,
    *,
    channel: str = "https://conda.example.org/team",
) -> SimpleNamespace:
    return SimpleNamespace(
        channel=SimpleNamespace(base_url=channel),
        fn="pkg-1-0.conda",
        name="pkg",
        subdir="linux-64",
        url=f"{channel}/linux-64/pkg-1-0.conda",
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        attestations_sha256=hashlib.sha256(sidecar).hexdigest(),
    )


def test_repodata_audit_caches_verified_sidecar_for_offline_reuse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_bytes = b"package"
    archive = tmp_path / "pkg-1-0.conda"
    archive.write_bytes(package_bytes)
    package_sha256 = hashlib.sha256(package_bytes).hexdigest()
    sidecar = json.dumps([{"bundle": "one"}]).encode()
    record = package_record(archive, sidecar)
    cache = DigestCache(tmp_path / "cache")
    fetched: list[str] = []
    canonical = json.dumps({"bundle": "one"}, separators=(",", ":"), sort_keys=True)
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )
    verifier = FakeVerifier(
        {
            canonical: SignerIdentity(
                "publisher@example.org",
                "https://issuer.example",
            )
        },
        {
            canonical: PublishStatement(
                record.fn,
                package_sha256,
                "https://conda.example.org/team",
            ).payload()
        },
    )
    auditor = EnvironmentAuditor(
        SigstoreSettings(),
        verifier,
        sidecars=SidecarTransport(
            cache=cache,
            fetcher=lambda url, _limit: fetched.append(url) or sidecar,
        ),
    )

    result = auditor.audit_record(record)
    monkeypatch.setattr(
        "conda.base.context.context",
        SimpleNamespace(offline=True),
    )
    cached_result = auditor.audit_record(record)

    assert result.status is VerificationStatus.VERIFIED
    assert cached_result.status is VerificationStatus.VERIFIED
    assert result.evidence[0].signer.identity == "publisher@example.org"
    assert result.to_dict()["authorization"] == "not-evaluated"
    assert fetched == [
        f"{record.url}.sigs.{record.attestations_sha256}",
    ]
    assert cache.load_sidecar(record.attestations_sha256) == sidecar


def test_repodata_audit_does_not_cache_invalid_bundle(tmp_path: Path) -> None:
    archive = tmp_path / "pkg-1-0.conda"
    archive.write_bytes(b"package")
    sidecar = json.dumps([{"bundle": "one"}]).encode()
    record = package_record(archive, sidecar)
    cache = DigestCache(tmp_path / "cache")
    auditor = EnvironmentAuditor(
        SigstoreSettings(),
        FakeVerifier({}, {}),
        sidecars=SidecarTransport(
            cache=cache,
            fetcher=lambda _url, _limit: sidecar,
        ),
    )

    result = auditor.verify_record_evidence(record, record.sha256)

    assert result.status is VerificationStatus.INVALID
    assert cache.load_sidecar(record.attestations_sha256) is None


def test_prefix_sidecar_audit_is_explicit_and_unpinned(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package_bytes = b"package"
    archive = tmp_path / "pkg-1-0.conda"
    archive.write_bytes(package_bytes)
    package_sha256 = hashlib.sha256(package_bytes).hexdigest()
    sidecar = json.dumps([{"bundle": "one"}]).encode()
    record = package_record(archive, sidecar)
    canonical = json.dumps({"bundle": "one"}, separators=(",", ":"), sort_keys=True)
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )
    verifier = FakeVerifier(
        {canonical: SignerIdentity("publisher@example.org", "https://issuer.example")},
        {
            canonical: PublishStatement(
                record.fn,
                package_sha256,
                "https://conda.example.org/team",
            ).payload()
        },
    )
    fetched: list[str] = []

    def fetch(url: str, _limit: int) -> bytes:
        fetched.append(url)
        return sidecar

    auditor = EnvironmentAuditor(
        SigstoreSettings(),
        verifier,
        transport="prefix",
        sidecars=SidecarTransport(fetcher=fetch),
    )

    result = auditor.audit_record(record)

    assert fetched[0].endswith(".conda.v0.sigs")
    assert result.status is VerificationStatus.VERIFIED
    assert result.prefix_sidecar


def test_repodata_audit_reports_missing_advertisement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "pkg-1-0.conda"
    archive.write_bytes(b"package")
    record = package_record(archive, b"[]")
    del record.attestations_sha256
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )
    auditor = EnvironmentAuditor(SigstoreSettings(), FakeVerifier({}, {}))

    result = auditor.audit_record(record)

    assert result.status is VerificationStatus.MISSING
    assert result.failures[0].code == "missing-attestations"


def test_repodata_audit_ignores_old_nested_attestations_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = tmp_path / "pkg-1-0.conda"
    archive.write_bytes(b"package")
    record = package_record(archive, b"[]")
    del record.attestations_sha256
    record.attestations = {"sha256": "ab" * 32, "size": 2}
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )
    auditor = EnvironmentAuditor(
        SigstoreSettings(),
        FakeVerifier({}, {}),
        sidecars=SidecarTransport(
            fetcher=lambda *_args: pytest.fail(
                "old nested attestations metadata must not be fetched"
            )
        ),
    )

    result = auditor.audit_record(record)

    assert result.status is VerificationStatus.MISSING
    assert result.failures[0].code == "missing-attestations"


@pytest.mark.parametrize(
    ("transport", "code", "expected"),
    [
        ("repodata", "missing-sidecar", VerificationStatus.RETRIEVAL_FAILED),
        ("repodata", "retrieval-failed", VerificationStatus.RETRIEVAL_FAILED),
        ("repodata", "digest-mismatch", VerificationStatus.RETRIEVAL_FAILED),
        ("repodata", "invalid-sidecar", VerificationStatus.RETRIEVAL_FAILED),
        ("repodata", "sidecar-too-large", VerificationStatus.RETRIEVAL_FAILED),
        (
            "repodata",
            "offline-cache-miss",
            VerificationStatus.EVIDENCE_UNAVAILABLE,
        ),
        ("prefix", "missing-sidecar", VerificationStatus.MISSING),
        ("prefix", "invalid-sidecar", VerificationStatus.INVALID),
    ],
)
def test_transport_failure_status_mapping(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    transport: str,
    code: str,
    expected: VerificationStatus,
) -> None:
    archive = tmp_path / "pkg-1-0.conda"
    archive.write_bytes(b"package")
    record = package_record(archive, b"[]")
    monkeypatch.setattr(
        EnvironmentAuditor,
        "retained_archive",
        staticmethod(lambda _record: archive),
    )

    def fail_fetch(_url: str, _limit: int) -> bytes:
        raise TransportError(code, "sidecar failure")

    auditor = EnvironmentAuditor(
        SigstoreSettings(),
        FakeVerifier({}, {}),
        transport=transport,
        sidecars=SidecarTransport(fetcher=fail_fetch),
    )

    result = auditor.audit_record(record)

    assert result.status is expected
    assert result.failures[0].code == code


def test_environment_audit_does_not_hide_programming_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    installed_records,
) -> None:
    record = SimpleNamespace(
        channel=SimpleNamespace(base_url="https://conda.example.org/team"),
        fn="pkg-1-0.conda",
        name="pkg",
        sha256="ab" * 32,
    )

    installed_records(record)
    monkeypatch.setattr(
        EnvironmentAuditor,
        "audit_record",
        lambda self, item: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    auditor = EnvironmentAuditor(SigstoreSettings(), FakeVerifier({}, {}))

    with pytest.raises(RuntimeError, match="boom"):
        auditor.audit_environment(tmp_path)


@pytest.mark.parametrize(
    "error",
    [CondaError("conda failed"), OSError("archive failed")],
    ids=["conda", "filesystem"],
)
def test_environment_audit_isolates_expected_record_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error: Exception,
    installed_records,
) -> None:
    record = SimpleNamespace(
        channel=SimpleNamespace(base_url="https://conda.example.org/team"),
        fn="pkg-1-0.conda",
        name="pkg",
        sha256="ab" * 32,
    )

    installed_records(record)
    monkeypatch.setattr(
        EnvironmentAuditor,
        "audit_record",
        lambda self, item: (_ for _ in ()).throw(error),
    )

    report = EnvironmentAuditor(
        SigstoreSettings(),
        FakeVerifier({}, {}),
    ).audit_environment(tmp_path)

    assert report["packages"][0]["status"] == "evidence-unavailable"
    assert str(error) not in str(report)


def test_environment_audit_orders_records_and_dispatches_source_audit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    installed_records,
) -> None:
    records = tuple(
        SimpleNamespace(
            channel=SimpleNamespace(base_url="https://conda.example.org/team"),
            fn=f"{name}-1-0.conda",
            name=name,
            sha256="ab" * 32,
        )
        for name in ("zeta", "alpha")
    )

    installed_records(*records)

    def verified(_self, record):
        return VerificationResult(
            status=VerificationStatus.VERIFIED,
            artifact=record.fn,
            artifact_sha256=record.sha256,
            channel="https://conda.example.org/team",
        )

    audited_sources: list[str] = []

    def sources(_self, record, *, package_verified, package_sha256):
        assert package_verified
        assert package_sha256 == record.sha256
        audited_sources.append(record.name)
        return [{"status": "verified", "source_index": 0}]

    monkeypatch.setattr(EnvironmentAuditor, "audit_record", verified)
    monkeypatch.setattr(EnvironmentAuditor, "audit_sources", sources)

    report = EnvironmentAuditor(
        SigstoreSettings(),
        FakeVerifier({}, {}),
    ).audit_environment(tmp_path, include_sources=True)

    packages = report["packages"]
    assert report["version"] == 1
    assert report["prefix"] == str(tmp_path.resolve())
    assert [package["artifact"] for package in packages] == [
        "alpha-1-0.conda",
        "zeta-1-0.conda",
    ]
    assert audited_sources == ["alpha", "zeta"]
    assert packages[0]["source_evidence"] == [{"status": "verified", "source_index": 0}]
