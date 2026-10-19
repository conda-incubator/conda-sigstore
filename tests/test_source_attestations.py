from __future__ import annotations

import pytest
from conda.common.serialize import yaml

from conda_sigstore import source_attestations
from conda_sigstore.evidence import SignerIdentity
from conda_sigstore.source_attestations import (
    EmbeddedSourceBundle,
    SourceAttestationRequirement,
)


@pytest.fixture
def source_declaration():
    return {
        "url": "https://example.org/source.tar.gz",
        "sha256": "ab" * 32,
        "attestation": {
            "publishers": ["github:example/project"],
            "verified": [
                {
                    "path": "attestations/source.sigstore.json",
                    "sha256": "cd" * 32,
                }
            ],
        },
    }


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "entries must be objects"),
        ({"path": 1, "sha256": "ab" * 32}, "safe POSIX"),
        (
            {"path": "attestations/source.json", "sha256": "ab" * 32},
            "embedded Sigstore bundle",
        ),
        (
            {
                "path": "attestations/source.sigstore.json",
                "sha256": "invalid",
            },
            "verified.sha256",
        ),
    ],
)
def test_embedded_bundle_rejects_malformed_descriptor(
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        EmbeddedSourceBundle.from_mapping(value)


@pytest.mark.parametrize(
    ("publisher", "message"),
    [
        ({"identity": "publisher"}, "require identity and issuer"),
        ({"identity": 1, "issuer": "issuer"}, "must be strings"),
        (1, "strings or mappings"),
        ("github:example/project@main", "ref constraints"),
        ("example", "name a provider"),
        ("github:example", "owner and repository"),
        ("unknown:example/project", "unsupported publisher provider"),
        (
            {
                "provider": "github",
                "owner": "example",
                "repo": "project",
                "ref_constraint": "refs/tags/*",
            },
            "ref constraints",
        ),
        (
            {
                "provider": "github",
                "owner": "example",
                "repo": "project",
                "workflow": "release.yml",
            },
            "publisher mappings",
        ),
        ({"provider": "github", "owner": "example"}, "publisher mappings"),
        ({"provider": "github", "owner": None, "repo": "project"}, "nonempty strings"),
        ({"provider": "github", "owner": "example", "repo": ""}, "nonempty strings"),
        (
            {"provider": "unknown", "owner": "example", "repo": "project"},
            "unsupported publisher provider",
        ),
    ],
)
def test_publisher_rejects_malformed_value(
    publisher: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        SourceAttestationRequirement.publisher(publisher)


@pytest.mark.parametrize(
    ("publisher", "identity", "issuer"),
    [
        (
            {
                "provider": "github",
                "owner": "example",
                "repo": "project",
                "ref_constraint": None,
            },
            "https://github.com/example/project",
            "https://token.actions.githubusercontent.com",
        ),
        (
            {"provider": "gitlab", "owner": "group", "repo": "nested/project"},
            "https://gitlab.com/group/nested/project",
            "https://gitlab.com",
        ),
    ],
    ids=["github-rendered", "gitlab-rendered"],
)
def test_rendered_publisher_preserves_repository_and_issuer(
    publisher, identity, issuer
):
    assert SourceAttestationRequirement.publisher(publisher) == SignerIdentity(
        identity, issuer
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("invalid", "attestation must be an object"),
        ({"publishers": [], "verified": []}, "must not be empty"),
        ({"publishers": {"provider": "github"}}, "publishers must be"),
        (
            {"publishers": ["github:example/project"], "predicate_type": ""},
            "predicate_type",
        ),
        (
            {"publishers": ["github:example/project"], "verified": {}},
            "verified must be a list",
        ),
    ],
)
@pytest.mark.parametrize("from_recipe", [False, True], ids=["source", "recipe"])
def test_source_requirement_rejects_malformed_attestation(
    value: object,
    message: str,
    from_recipe: bool,
) -> None:
    source = {
        "url": "https://example.org/source.tar.gz",
        "sha256": "ab" * 32,
        "attestation": value,
    }
    if from_recipe:
        with pytest.raises(ValueError, match=message):
            SourceAttestationRequirement.from_recipe({"source": source})
    else:
        with pytest.raises(ValueError, match=message):
            SourceAttestationRequirement.from_source(source, 0)


@pytest.mark.parametrize(
    "value",
    [
        {"git": "https://example.org/repo", "sha256": "ab" * 32},
        {"path": "../source", "sha256": "ab" * 32},
        {"sha256": "ab" * 32},
    ],
)
def test_source_requirement_requires_url_source(value: dict[str, object]) -> None:
    value["attestation"] = {
        "publishers": ["github:example/project"],
        "verified": [],
    }
    with pytest.raises(ValueError, match="require a URL source"):
        SourceAttestationRequirement.from_source(value, 0)


@pytest.mark.parametrize(
    ("recipe", "message"),
    [
        ({"source": "source.tar.gz"}, "object or list"),
        ({"source": ["source.tar.gz"]}, r"source\[0\] must be an object"),
        ({"recipe": None}, "recipe must be an object"),
        ({"recipe": []}, "recipe must be an object"),
        ({"recipe": {}, "source": []}, "both recipe and source"),
        ({"recipe": {"recipe": {}}}, "nested recipe"),
    ],
)
def test_recipe_rejects_malformed_sources(
    recipe: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        SourceAttestationRequirement.from_recipe(recipe)


def test_recipe_ignores_source_without_attestation() -> None:
    assert (
        SourceAttestationRequirement.from_recipe(
            {"source": {"url": "https://example.org/source.tar.gz"}}
        )
        == ()
    )


@pytest.mark.parametrize("publisher_list", [False, True], ids=["scalar", "list"])
def test_recipe_accepts_rattler_publisher_input(source_declaration, publisher_list):
    publisher = "github:example/project"
    source_declaration["attestation"]["publishers"] = (
        [publisher] if publisher_list else publisher
    )
    requirement = SourceAttestationRequirement.from_source(source_declaration, 0)
    assert requirement.publishers == (
        SignerIdentity(
            "https://github.com/example/project",
            "https://token.actions.githubusercontent.com",
        ),
    )


@pytest.mark.parametrize(
    ("field", "limit_name", "message"),
    [
        (
            "publishers",
            "MAX_SOURCE_PUBLISHERS",
            "too many source attestation publishers",
        ),
        ("verified", "MAX_SOURCE_BUNDLES", "too many source attestation bundles"),
    ],
)
def test_source_requirement_limits_declarations_before_parsing(
    monkeypatch, source_declaration, field, limit_name, message
):
    monkeypatch.setattr(source_attestations, limit_name, 2)
    source_declaration["attestation"][field] = [None] * 3
    with pytest.raises(ValueError, match=message):
        SourceAttestationRequirement.from_source(source_declaration, 0)


@pytest.mark.parametrize(
    ("field", "limit_name", "attribute"),
    [
        ("publishers", "MAX_SOURCE_PUBLISHERS", "publishers"),
        ("verified", "MAX_SOURCE_BUNDLES", "bundles"),
    ],
)
def test_source_requirement_accepts_declarations_at_limit(
    monkeypatch, source_declaration, field, limit_name, attribute
):
    monkeypatch.setattr(source_attestations, limit_name, 2)
    source_declaration["attestation"][field] *= 2
    requirement = SourceAttestationRequirement.from_source(source_declaration, 0)
    assert len(getattr(requirement, attribute)) == 2


def test_recipe_limits_source_count_before_parsing(monkeypatch):
    monkeypatch.setattr(source_attestations, "MAX_RECIPE_SOURCES", 2)
    with pytest.raises(ValueError, match="too many recipe sources"):
        SourceAttestationRequirement.from_recipe({"source": [None] * 3})


def test_recipe_accepts_sources_at_limit(monkeypatch, source_declaration):
    monkeypatch.setattr(source_attestations, "MAX_RECIPE_SOURCES", 2)
    requirements = SourceAttestationRequirement.from_recipe(
        {"source": [source_declaration] * 2}
    )
    assert [requirement.source_index for requirement in requirements] == [0, 1]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publishers", [None]),
        ("verified", [None]),
        ("publishers", "github:example/project"),
    ],
    ids=["publishers", "bundles", "scalar-publisher"],
)
@pytest.mark.parametrize("wrapped", [False, True], ids=["recipe", "build-output"])
def test_recipe_limits_aggregate_declarations_before_parsing(
    monkeypatch, source_declaration, field, value, wrapped
):
    monkeypatch.setattr(source_attestations, "MAX_RECIPE_DECLARATIONS", 3)
    source_declaration["attestation"][field] = value
    recipe = {"source": [source_declaration] * 2}
    if wrapped:
        recipe = {"recipe": recipe}
    with pytest.raises(ValueError, match="too many source attestation declarations"):
        SourceAttestationRequirement.from_recipe(recipe)


def test_recipe_accepts_aggregate_declarations_at_limit(
    monkeypatch, source_declaration
):
    monkeypatch.setattr(source_attestations, "MAX_RECIPE_DECLARATIONS", 4)
    requirements = SourceAttestationRequirement.from_recipe(
        {"source": [source_declaration] * 2}
    )
    assert len(requirements) == 2


@pytest.mark.parametrize(
    "payload",
    [
        "source: &source {url: 'https://example.org/source'}\nother: *source\n",
        "source: &source {nested: *source}\n",
    ],
    ids=["reused-alias", "recursive-alias"],
)
def test_recipe_yaml_rejects_aliases_before_loading(monkeypatch, payload):
    def unexpected_load(_payload):
        pytest.fail("YAML aliases reached the recipe object loader")

    monkeypatch.setattr(yaml, "loads", unexpected_load)
    with pytest.raises(ValueError, match="YAML aliases are not supported"):
        SourceAttestationRequirement.from_yaml(payload)


@pytest.mark.parametrize(
    ("limit_name", "limit", "payload", "message"),
    [
        ("MAX_RENDERED_RECIPE_BYTES", 8, "about: a\n", "YAML byte limit"),
        ("MAX_RENDERED_RECIPE_BYTES", 9, "about: é\n", "YAML byte limit"),
        ("MAX_RECIPE_YAML_EVENTS", 4, "source: {}\n", "too many YAML events"),
        (
            "MAX_RECIPE_YAML_DEPTH",
            2,
            "source: {nested: {child: 1}}\n",
            "nested too deeply",
        ),
    ],
)
def test_recipe_yaml_limits_structure_before_loading(
    monkeypatch, limit_name, limit, payload, message
):
    def unexpected_load(_payload):
        pytest.fail("oversized YAML structure reached the recipe object loader")

    monkeypatch.setattr(source_attestations, limit_name, limit)
    monkeypatch.setattr(yaml, "loads", unexpected_load)
    with pytest.raises(ValueError, match=message):
        SourceAttestationRequirement.from_yaml(payload)


@pytest.mark.parametrize(
    "payload", ["about: a\n", "about: é\n"], ids=["ascii", "utf-8"]
)
def test_recipe_yaml_accepts_exact_byte_limit(monkeypatch, payload):
    monkeypatch.setattr(
        source_attestations, "MAX_RENDERED_RECIPE_BYTES", len(payload.encode("utf-8"))
    )
    assert SourceAttestationRequirement.from_yaml(payload) == ()


@pytest.mark.parametrize("wrapped", [False, True], ids=["recipe", "build-output"])
def test_recipe_yaml_accepts_plain_declarations(source_declaration, wrapped):
    payload = "\n".join(
        [
            "source:",
            "  url: https://example.org/source.tar.gz",
            "  sha256: " + "ab" * 32,
            "  attestation:",
            "    publishers: ['github:example/project']",
            "    verified:",
            "      - path: attestations/source.sigstore.json",
            "        sha256: " + "cd" * 32,
        ]
    )
    if wrapped:
        payload = "recipe:\n" + "\n".join("  " + line for line in payload.splitlines())
    assert SourceAttestationRequirement.from_yaml(payload) == (
        SourceAttestationRequirement.from_source(source_declaration, 0),
    )


@pytest.mark.parametrize("payload", ["[]", "null", "source.tar.gz"])
def test_recipe_yaml_requires_mapping(payload):
    with pytest.raises(ValueError, match="rendered recipe must be an object"):
        SourceAttestationRequirement.from_yaml(payload)
