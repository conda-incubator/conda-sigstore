"""Draft embedded source-attestation evidence."""

from __future__ import annotations

import hashlib
import hmac
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from .evidence import SignerIdentity, validate_sha256
from .exceptions import (
    BundleVerificationError,
    StatementError,
    TrustMaterialUnavailableError,
)
from .statements import InTotoStatement
from .transport import read_bounded_file

if TYPE_CHECKING:
    from pathlib import Path

    from .verification import BundleVerifier

MAX_RECIPE_SOURCES = 100
MAX_RENDERED_RECIPE_BYTES = 1024 * 1024
MAX_SOURCE_PUBLISHERS = 16
MAX_SOURCE_BUNDLES = 32
MAX_RECIPE_DECLARATIONS = 256
MAX_RECIPE_YAML_EVENTS = 10_000
MAX_RECIPE_YAML_DEPTH = 32


def resolve_embedded_file(root: Path, relative: str) -> Path | None:
    """Resolve a regular embedded file without following any symlink."""
    parsed = PurePosixPath(relative)
    candidate = root
    for part in parsed.parts:
        candidate /= part
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(mode):
            raise ValueError(f"embedded path contains a symlink: {relative}")
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise ValueError(f"embedded path escapes the package: {relative}") from exc
    if not stat.S_ISREG(candidate.lstat().st_mode):
        raise ValueError(f"embedded path is not a regular file: {relative}")
    return candidate


@dataclass(frozen=True, slots=True)
class EmbeddedSourceBundle:
    """One recipe-indexed Sigstore bundle stored in a package archive."""

    path: str
    sha256: str

    @classmethod
    def from_mapping(cls, value: object) -> EmbeddedSourceBundle:
        """Parse only the path and digest from untrusted verified metadata."""
        if not isinstance(value, Mapping):
            raise ValueError("attestation.verified entries must be objects")
        path = value.get("path")
        if not isinstance(path, str) or not path or "\\" in path or "\0" in path:
            raise ValueError("verified.path must be a safe POSIX relative path")
        parsed = PurePosixPath(path)
        if (
            parsed.is_absolute()
            or ".." in parsed.parts
            or parsed.as_posix() != path
            or len(parsed.parts) != 2
            or parsed.parts[0] != "attestations"
            or not path.endswith(".sigstore.json")
        ):
            raise ValueError("verified.path must name an embedded Sigstore bundle")
        return cls(
            path=path,
            sha256=validate_sha256(
                value.get("sha256"),
                field_name="verified.sha256",
            ),
        )

    def audit(
        self,
        recipe_root: Path,
        requirement: SourceAttestationRequirement,
        *,
        verifier: BundleVerifier,
        max_bytes: int,
    ) -> tuple[dict[str, object], SignerIdentity | None]:
        """Verify this bundle against its bytes and source requirement."""
        report: dict[str, object] = {"path": self.path, "sha256": self.sha256}
        try:
            path = resolve_embedded_file(recipe_root, self.path)
            if path is None:
                return {**report, "status": "missing"}, None
            body = read_bounded_file(
                path,
                max_bytes,
                description="embedded bundle",
            )
            if not hmac.compare_digest(hashlib.sha256(body).hexdigest(), self.sha256):
                raise ValueError("embedded bundle SHA-256 does not match the recipe")
            verified = verifier.verify(body.decode("utf-8"))
            if verified.payload_type != InTotoStatement.PAYLOAD_TYPE:
                raise ValueError("bundle payload is not an in-toto JSON statement")
            statement = InTotoStatement.from_payload(verified.payload)
            predicate_type = statement.predicate_type
            if (
                requirement.predicate_type is not None
                and predicate_type != requirement.predicate_type
            ):
                raise ValueError("predicate type does not match the recipe requirement")
            if not any(
                hmac.compare_digest(
                    subject.digest.get("sha256", ""),
                    requirement.source_sha256,
                )
                for subject in statement.subjects()
            ):
                raise ValueError("attestation subject does not bind the recipe source")
        except TrustMaterialUnavailableError:
            return {
                **report,
                "status": "evidence-unavailable",
                "failure": "Sigstore trust material is unavailable",
            }, None
        except OSError as exc:
            return {
                **report,
                "status": "evidence-unavailable",
                "failure": f"embedded bundle could not be read ({type(exc).__name__})",
            }, None
        except (
            BundleVerificationError,
            StatementError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            return {**report, "status": "invalid", "failure": str(exc)}, None
        identity = verified.signer
        return (
            {
                **report,
                "status": "verified",
                **identity.to_dict(),
                "predicate_type": predicate_type,
                "timestamps": list(verified.timestamps),
            },
            identity,
        )


@dataclass(frozen=True, slots=True)
class SourceAttestationRequirement:
    """Publisher and predicate requirements declared by one recipe source."""

    source_index: int
    source_sha256: str
    publishers: tuple[SignerIdentity, ...]
    predicate_type: str | None
    bundles: tuple[EmbeddedSourceBundle, ...]

    @classmethod
    def from_yaml(cls, payload: str) -> tuple[SourceAttestationRequirement, ...]:
        """Check YAML structure before constructing recipe declarations."""
        from conda.common.serialize import yaml
        from ruamel.yaml import YAML
        from ruamel.yaml.events import (
            AliasEvent,
            CollectionEndEvent,
            CollectionStartEvent,
        )

        if (
            len(payload) > MAX_RENDERED_RECIPE_BYTES
            or len(payload.encode("utf-8")) > MAX_RENDERED_RECIPE_BYTES
        ):
            raise ValueError("rendered recipe exceeds the YAML byte limit")
        depth = 0
        for count, event in enumerate(YAML(typ="base").parse(payload), 1):
            if count > MAX_RECIPE_YAML_EVENTS:
                raise ValueError("rendered recipe contains too many YAML events")
            if isinstance(event, AliasEvent):
                raise ValueError("rendered recipe YAML aliases are not supported")
            if isinstance(event, CollectionStartEvent):
                depth += 1
                if depth > MAX_RECIPE_YAML_DEPTH:
                    raise ValueError("rendered recipe YAML is nested too deeply")
            elif isinstance(event, CollectionEndEvent):
                depth -= 1
        rendered = yaml.loads(payload)
        if not isinstance(rendered, Mapping):
            raise ValueError("rendered recipe must be an object")
        return cls.from_recipe(rendered)

    @staticmethod
    def publisher(value: object) -> SignerIdentity:
        """Read an explicit identity or a supported recipe publisher."""
        if isinstance(value, Mapping):
            if "provider" not in value:
                if set(value) != {"identity", "issuer"}:
                    raise ValueError("publisher mappings require identity and issuer")
                identity = value["identity"]
                issuer = value["issuer"]
                if not isinstance(identity, str) or not isinstance(issuer, str):
                    raise ValueError("publisher identity and issuer must be strings")
                return SignerIdentity(identity, issuer)
            fields = {"provider", "owner", "repo"}
            if not fields <= value.keys() or value.keys() - fields - {"ref_constraint"}:
                raise ValueError(
                    "rendered publisher mappings require provider, owner, and repo"
                )
            if value.get("ref_constraint") is not None:
                raise ValueError("publisher ref constraints are not supported")
            provider, owner, repository = (
                value["provider"],
                value["owner"],
                value["repo"],
            )
            if not all(
                isinstance(part, str) and part for part in (provider, owner, repository)
            ):
                raise ValueError(
                    "publisher provider, owner, and repo must be nonempty strings"
                )
            value = f"{provider}:{owner}/{repository}"
        if not isinstance(value, str) or not value:
            raise ValueError("publishers must contain strings or mappings")
        shorthand, separator, _ref = value.partition("@")
        if separator:
            raise ValueError("publisher ref constraints are not supported")
        provider, separator, repository = shorthand.partition(":")
        if not separator:
            raise ValueError("publisher shorthand must name a provider")
        parts = repository.split("/")
        if len(parts) < 2 or any(not part for part in parts):
            raise ValueError("publisher shorthand must name an owner and repository")
        providers = {
            "github": (
                "https://github.com",
                "https://token.actions.githubusercontent.com",
            ),
            "gitlab": ("https://gitlab.com", "https://gitlab.com"),
        }
        try:
            identity_root, issuer = providers[provider]
        except KeyError as exc:
            raise ValueError(f"unsupported publisher provider: {provider}") from exc
        return SignerIdentity(f"{identity_root}/{repository}", issuer)

    @classmethod
    def from_source(
        cls,
        source: Mapping[str, object],
        source_index: int,
    ) -> SourceAttestationRequirement | None:
        """Parse one source that may declare draft source attestations."""
        raw_attestation = source.get("attestation")
        if raw_attestation is None:
            return None
        if not isinstance(raw_attestation, Mapping):
            raise ValueError(f"source[{source_index}].attestation must be an object")
        if "url" not in source or "git" in source or "path" in source:
            raise ValueError("source attestations require a URL source")
        raw_publishers = raw_attestation.get("publishers")
        if isinstance(raw_publishers, str):
            raw_publishers = [raw_publishers]
        if not isinstance(raw_publishers, Sequence):
            raise ValueError("attestation.publishers must be a string or list")
        if len(raw_publishers) > MAX_SOURCE_PUBLISHERS:
            raise ValueError("too many source attestation publishers")
        publishers = tuple(cls.publisher(item) for item in raw_publishers)
        if not publishers:
            raise ValueError("attestation.publishers must not be empty")
        predicate_type = raw_attestation.get("predicate_type")
        if predicate_type is not None and (
            not isinstance(predicate_type, str) or not predicate_type
        ):
            raise ValueError("attestation.predicate_type must be a nonempty string")
        raw_bundles = raw_attestation.get("verified", ())
        if not isinstance(raw_bundles, Sequence) or isinstance(raw_bundles, str):
            raise ValueError("attestation.verified must be a list")
        if len(raw_bundles) > MAX_SOURCE_BUNDLES:
            raise ValueError("too many source attestation bundles")
        return cls(
            source_index=source_index,
            source_sha256=validate_sha256(
                source.get("sha256"),
                field_name=f"source[{source_index}].sha256",
            ),
            publishers=publishers,
            predicate_type=predicate_type,
            bundles=tuple(
                EmbeddedSourceBundle.from_mapping(item) for item in raw_bundles
            ),
        )

    @classmethod
    def from_recipe(
        cls,
        rendered_recipe: Mapping[str, object],
    ) -> tuple[SourceAttestationRequirement, ...]:
        """Parse every source-attestation requirement in a rendered recipe."""
        if "recipe" in rendered_recipe:
            if "source" in rendered_recipe:
                raise ValueError(
                    "rendered output must not contain both recipe and source"
                )
            recipe = rendered_recipe["recipe"]
            if not isinstance(recipe, Mapping):
                raise ValueError("rendered output recipe must be an object")
            if "recipe" in recipe:
                raise ValueError("nested recipe wrappers are not supported")
            rendered_recipe = recipe
        raw_sources = rendered_recipe.get("source", ())
        if isinstance(raw_sources, Mapping):
            sources: Sequence[object] = (raw_sources,)
        elif isinstance(raw_sources, Sequence) and not isinstance(raw_sources, str):
            sources = raw_sources
        else:
            raise ValueError("recipe source must be an object or list")
        if len(sources) > MAX_RECIPE_SOURCES:
            raise ValueError("too many recipe sources")
        declarations = 0
        # Count alias occurrences before constructing any requirement objects.
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            attestation = source.get("attestation")
            if not isinstance(attestation, Mapping):
                continue
            for field in ("publishers", "verified"):
                values = attestation.get(field, ())
                if isinstance(values, Sequence) and not isinstance(values, str):
                    declarations += len(values)
                elif field == "publishers" and isinstance(values, str):
                    declarations += 1
            if declarations > MAX_RECIPE_DECLARATIONS:
                raise ValueError("too many source attestation declarations in recipe")
        requirements: list[SourceAttestationRequirement] = []
        for source_index, source in enumerate(sources):
            if not isinstance(source, Mapping):
                raise ValueError(f"source[{source_index}] must be an object")
            requirement = cls.from_source(source, source_index)
            if requirement is not None:
                requirements.append(requirement)
        return tuple(requirements)

    @staticmethod
    def publisher_matches(expected: SignerIdentity, actual: SignerIdentity) -> bool:
        """Apply the draft repository-boundary publisher matching rule."""
        if expected.issuer != actual.issuer:
            return False
        if not expected.identity.startswith("https://"):
            return expected.identity == actual.identity
        publisher = expected.identity.casefold()
        identity = actual.identity.casefold()
        return identity == publisher or (
            identity.startswith(publisher)
            and len(identity) > len(publisher)
            and identity[len(publisher)] in {"/", "@"}
        )

    def audit(
        self,
        recipe_root: Path,
        *,
        verifier: BundleVerifier,
        max_bytes: int,
    ) -> dict[str, object]:
        """Verify every indexed bundle and require every declared publisher."""
        bundle_results = [
            bundle.audit(
                recipe_root,
                self,
                verifier=verifier,
                max_bytes=max_bytes,
            )
            for bundle in self.bundles
        ]
        bundles = [report for report, _identity in bundle_results]
        identities = tuple(
            identity for _report, identity in bundle_results if identity is not None
        )
        matched = tuple(
            publisher
            for publisher in self.publishers
            if any(
                self.publisher_matches(publisher, identity) for identity in identities
            )
        )
        status = "verified"
        failure: str | None = None
        if not self.bundles or any(item["status"] == "missing" for item in bundles):
            status = "missing"
            failure = "embedded source attestation bundle is missing"
        elif any(item["status"] == "invalid" for item in bundles):
            status = "invalid"
            failure = "one or more embedded source attestations are invalid"
        elif any(item["status"] == "evidence-unavailable" for item in bundles):
            status = "evidence-unavailable"
            failure = "source attestation verification could not run"
        elif len(matched) != len(self.publishers):
            status = "untrusted-identity"
            failure = "not every recipe publisher matched a verified bundle"
        report: dict[str, object] = {
            "source_index": self.source_index,
            "source_sha256": self.source_sha256,
            "status": status,
            "predicate_type": self.predicate_type,
            "required_publishers": [
                publisher.to_dict() for publisher in self.publishers
            ],
            "matched_publishers": [publisher.to_dict() for publisher in matched],
            "bundles": bundles,
            "package_publication": "verified",
            "verification_scope": "draft-source-attestation",
        }
        if failure is not None:
            report["failure"] = failure
        return report
