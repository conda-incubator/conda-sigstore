# Source-attestation audit format

`conda sigstore audit --sources` implements an audit-only subset of the open
[conda/ceps#168](https://github.com/conda/ceps/pull/168) proposal. The proposal
is not an accepted CEP and its recipe and package layout may change.
Accepted [CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md) covers
sidecar distribution and does not standardize this embedded source evidence.

This page describes the current `conda-sigstore` parser. It is not a stable
recipe-format standard.

## Rattler-Build support

Rattler-Build 0.77.0 accepts `bundle_url` and `publishers` in a source's
[`attestation` declaration](https://github.com/prefix-dev/rattler-build/blob/v0.77.0/crates/rattler_build_recipe/src/stage0/parser/source.rs#L374).
During download, it verifies sources and records an `attestation_verified` flag
in its [source cache](https://github.com/prefix-dev/rattler-build/blob/v0.77.0/crates/rattler_build_source_cache/src/cache.rs#L332).
The builder does not export the bundles and `verified` references needed by
this auditor. The auditor cannot verify a source from a declaration or cache
flag alone.

The auditor reads source declarations and supported publisher forms from direct
recipe mappings or Rattler-Build's serialized `BuildOutput`, where sources
appear under `recipe.source`. Without retained bundle references, the source
result is `missing`. Audits do not fetch `bundle_url` or discover
remote attestations.

[Rattler-Build #2721](https://github.com/prefix-dev/rattler-build/pull/2721) is
an open pull request for attestation discovery on immutable GitHub release
assets. It does not define how to export embedded evidence.

## Audit preconditions

Source auditing runs for a package only when:

1. the package has a verified, artifact-bound CEP 27 publication statement
2. the exact package archive remains in conda's package cache
3. the archive contains `info/recipe/rendered_recipe.yaml`

If a precondition fails, `source_evidence` contains an
`evidence-unavailable` result. Source evidence never substitutes for package
publication verification.

## Archive inspection

The auditor copies the retained archive to a temporary snapshot and checks its
SHA-256 against the verified package digest before inspecting it. It reads only
regular rendered-recipe and embedded-bundle files, without general package
extraction. For `.conda` packages, the original package filename selects the
exact `info-<package-filename-without-.conda>.tar.zst` component.

Unsafe archive paths are rejected. Selected recipe and bundle entries must be
regular files with unique paths. Links and special files at those paths are
invalid. Unrelated members are never copied or used as evidence. A malformed
archive, including an invalid bzip2 stream, produces an `invalid` source result.
A missing or unreadable archive produces `evidence-unavailable`.

Sparse files are unsupported. Skipped regular-file payload still counts toward
the expanded-byte limit but does not consume the tar metadata budget.

(source-audit-limits)=
## Source-audit limits

The fixed limits apply only to source auditing and do not restrict package
installation. Embedded bundles use the existing
`plugins.conda_sigstore.max_sidecar_bytes` setting. None of these limits
authorizes a signer.

| Input | Maximum | Result when exceeded |
| --- | --- | --- |
| Compressed retained package archive | 4 GiB | `evidence-unavailable` |
| Expanded tar stream, including headers and skipped payload in legacy `.tar.bz2` packages | 256 MiB | `invalid` |
| Tar parser reads outside regular-file payload reads | 16 MiB | `invalid` |
| Tar members | 10,000 | `invalid` |
| One ZIP metadata read | 1 MiB | `invalid` |
| ZIP entries | 16 | `invalid` |
| Zstandard decoder window | 64 MiB | `invalid` |
| Rendered recipe | 1 MiB of UTF-8 bytes | `invalid` |
| YAML collection nesting | 32 levels | `invalid` |
| YAML parsing events | 10,000 | `invalid` |
| Source mappings per recipe | 100 | `invalid` |
| Publishers per source | 16 | `invalid` |
| Embedded bundle descriptors per source | 32 | `invalid` |
| Publisher and embedded bundle declarations combined across a recipe | 256 | `invalid` |
| Each embedded bundle | Configured `max_sidecar_bytes` | `invalid` |

YAML aliases are rejected. The auditor checks YAML events and nesting before
constructing the recipe mapping, then counts publisher and bundle declarations
before constructing source-attestation requirements.

## Source declarations

Rattler-Build recipe inputs can declare `attestation` on URL sources:

```yaml
source:
  url: https://github.com/example/project/archive/v1.0.0.tar.gz
  sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  attestation:
    publishers:
      - github:example/project
    bundle_url: https://example.org/project-1.0.0.sigstore.json
```

The corresponding serialized declaration uses publisher objects inside a
`recipe` mapping:

```yaml
recipe:
  source:
    - url: https://github.com/example/project/archive/v1.0.0.tar.gz
      sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
      attestation:
        publishers:
          - provider: github
            owner: example
            repo: project
            ref_constraint: null
        bundle_url: https://example.org/project-1.0.0.sigstore.json
```

The auditor accepts either layout. `source` may be one mapping or a list of
mappings. A source without `attestation` is ignored.

`publishers` accepts a single shorthand string, such as
`publishers: github:example/project`, or a nonempty list. Rattler-Build renders
both forms as a list. Structured and explicit publisher mappings must appear
as list items.

| Field | Required | Parser behavior |
| --- | --- | --- |
| `source.url` | yes | Marks this as a URL source. `git` and `path` must be absent |
| `source.sha256` | yes | 64 hexadecimal characters, normalized to lowercase |
| `attestation.publishers` | yes | One supported shorthand string or a nonempty list of supported publisher strings or mappings |
| `attestation.bundle_url` | no | Builder input, never fetched during audit |

Rattler-Build permits `bundle_url` without publisher constraints. The auditor
still requires at least one publisher and a source SHA-256. Declarations that
omit these audit inputs produce an `invalid` result.

The experimental retained-evidence format below adds `predicate_type` and
`verified`. Rattler-Build 0.77.0 does not accept these fields as recipe inputs
or produce them in its rendered output.

## Publisher identities

The auditor accepts these hosted-provider shorthands:

| Shorthand | Identity expansion | Issuer expansion |
| --- | --- | --- |
| `github:OWNER/REPOSITORY` | `https://github.com/OWNER/REPOSITORY` | `https://token.actions.githubusercontent.com` |
| `gitlab:NAMESPACE/REPOSITORY` | `https://gitlab.com/NAMESPACE/REPOSITORY` | `https://gitlab.com` |

Rattler-Build's serialized publisher mappings contain `provider`, `owner`, and
`repo` strings. They expand to the same identity and issuer as the shorthands.
Only `github` and `gitlab` providers are supported. Nested repository paths are
accepted.

An `@REF` shorthand suffix or a non-null `ref_constraint` is rejected because
the auditor cannot enforce those constraints. Omitting `ref_constraint` or
setting it to null means no ref constraint.

The experimental format also accepts an explicit publisher with exactly two
fields:

```yaml
identity: https://github.com/example/project
issuer: https://token.actions.githubusercontent.com
```

Both values must be nonempty strings. The issuer is compared exactly.

For an identity beginning with `https://`, matching is case-insensitive. An
authenticated certificate identity matches when it is equal to the configured
identity or continues it with `/` or `@`.
This lets a repository identity match its workflow SAN without also matching a
similarly prefixed repository. Other identity forms, including email SANs, are
compared exactly and case-sensitively.

Every declared publisher must match at least one cryptographically verified
embedded bundle.

## Experimental retained evidence

The auditor supports this experimental extension for retained source bundles.
Released Rattler-Build output does not use this format:

```yaml
source:
  url: https://github.com/example/project/archive/v1.0.0.tar.gz
  sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
  attestation:
    publishers:
      - github:example/project
    predicate_type: https://slsa.dev/provenance/v1
    verified:
      - path: attestations/project-1.0.0.sigstore.json
        sha256: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
```

`predicate_type` is optional. When present, it must be a nonempty string and
every embedded statement must match it. An empty or omitted `verified` list
produces a `missing` source result.

### Embedded bundle descriptor

Each `attestation.verified` entry must provide:

```yaml
path: attestations/project-1.0.0.sigstore.json
sha256: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
```

| Field | Requirement |
| --- | --- |
| `path` | POSIX path relative to `info/recipe`, with exactly two components, first component `attestations`, and filename ending in `.sigstore.json` |
| `sha256` | 64-character hexadecimal digest of the exact embedded file bytes |

Absolute paths, backslashes, parent traversal, NUL characters, symlinks, and
non-regular files are rejected. Bundle bytes are bounded by
`plugins.conda_sigstore.max_sidecar_bytes` before parsing.

The draft proposal also shows copied `predicate_type`, `san`, and `issuer`
fields in `verified` entries. The auditor deliberately does not trust those
claims. It reads only `path` and `sha256`, then obtains the predicate type,
certificate identity, and issuer from the cryptographically verified bundle.

## Bundle acceptance

Every listed embedded bundle must pass all of these checks:

1. its bytes match the descriptor SHA-256
2. Sigstore verifies its certificate chain, transparency-log material, and
   DSSE signature against the selected trust configuration
3. its DSSE payload is an in-toto Statement v1 JSON object
4. at least one statement subject has a SHA-256 matching `source.sha256`
5. its `predicateType` matches `attestation.predicate_type` when configured

Missing, invalid, or unavailable sibling bundles make the source result
nonverified. When all bundles verify, every declared publisher must match an
authenticated bundle signer.

For converted PyPI PEP 740 responses, Rattler-Build 0.77.0
[skips transparency-log verification](https://github.com/prefix-dev/rattler-build/blob/v0.77.0/crates/rattler_build_source_cache/src/sigstore.rs#L376-L382)
because the conversion cannot reconstruct the canonical Rekor body. The
auditor requires verifiable transparency-log and checkpoint material for every
retained bundle. It rejects converted evidence that cannot satisfy those
checks. The embedded index has no authenticated conversion-provenance field
that could justify different verification rules.

## Requirements for exporting evidence

An independent source audit requires the builder to retain raw bundles in the
package, including the certificates and transparency-log material needed for
verification. The rendered recipe must reference each bundle's regular file
and SHA-256. Each signed statement must bind the recipe source's SHA-256.

The current auditor requires the paths and limits described above. A future
export format must also permit bounded reads and reject unsafe paths and links.
It must retain enough information to verify the original statement and signer.
Reconstructing a bundle from PEP 740 data also needs authenticated conversion
provenance and a defined way to verify its transparency evidence. A builder's
successful verification flag is insufficient.

The interoperability fixture covers a rendered Rattler-Build 0.77.0 declaration.
Testing evidence exported by a real package build requires builder support for
retaining that evidence.

## Result contract

Source results and embedded bundle variants are defined in
[JSON output and exit status](json-output.md). They report verified evidence
from a package archive. They do not authorize the package publisher, assign a
SLSA level, or prove that source contents are safe.
