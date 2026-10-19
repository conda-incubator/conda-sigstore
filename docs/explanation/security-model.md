# Security model and threat model

The plugin verifies that a Sigstore-authenticated identity signed a strict CEP
27 statement for exact conda package bytes. It reports that identity and the
available evidence. An explicit verification may require an exact identity and
issuer supplied independently by the operator. The plugin does not discover a
channel's publisher delegation. Its opt-in install verifier requires valid
repodata-hash-pinned or deterministic adjacent evidence before extraction, but
does not authorize the authenticated signer.

## Protected assets

- package bytes supplied for verification
- fetched or cached sidecar bytes
- target-channel claims in CEP 27 statements
- Sigstore trust material
- retained package archives inspected for source evidence

## Trust anchors

Cryptographic verification depends on:

- the selected Sigstore production or local trust configuration
- Fulcio certificate validation
- supported transparency-log, checkpoint, and timestamp verification material
- SHA-256 binding between the CEP 27 subject and package bytes

Accepted [CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md) lets repodata
bind exact sidecar bytes through `attestations_sha256`. The immutable
`.sigs.<sha256>` URL prevents cache races between sidecar revisions. This
binding is only as strong as the channel metadata path, including TLS.

Current conda `PackageRecord` objects do not preserve `attestations_sha256`, so
the CEP 50 transport cannot protect real solver, install, or installed-audit
flows until conda adds that field. Prefix.dev `.v0.sigs` compatibility does not
gain a repodata hash commitment from CEP 50.

A channel server's claim that an uploader was authorized is not currently a
trust anchor. The observed public client paths are documented in
[Publish attestations to Prefix.dev](../how-to/publish-prefix.md). Public
information does not establish whether Prefix.dev's server compares the bundle
signer with the uploader identity.

## Adversaries and assumptions

The model includes:

- a mirror or network intermediary substituting or removing artifacts,
  sidecars, or repodata
- a channel uploader attaching a bundle signed by another identity
- a holder of an unrelated but cryptographically valid Sigstore identity
- a signer replaying an attestation across channels
- a local attacker modifying caches between reads
- malformed or oversized evidence intended to exhaust client resources
- stale trust material
- a compromised signer workflow

The model does not assume that every Sigstore identity is trusted or that a
valid signature makes package contents safe.

## Threats and mitigations

| Threat | Mitigation | Remaining risk |
| --- | --- | --- |
| Artifact substitution | CEP 27 subject SHA-256 must match exact artifact bytes | Failure of SHA-256 collision resistance |
| Repodata sidecar substitution | The client validates `attestations_sha256`, fetches the immutable URL, enforces a streaming limit, and verifies the digest before parsing | Compromised or unauthenticated repodata |
| Prefix.dev sidecar substitution | Strict mode fails on absence and requires at least one valid bundle to bind the exact package digest. An included `targetChannel` must match | Without a repodata commitment or independent identity requirement, channel admission remains the trust assumption |
| Cross-channel replay | An included `targetChannel` must match the supplied channel | CEP 27 permits an absent target channel |
| Transparency-log omission | Sigstore verification requires supported verification material | Trust-root or verifier compromise |
| Converted PyPI bundle without canonical Rekor entry | Verification fails closed without authenticated conversion provenance | A future standard must define the exception |
| Oversized or malformed input | Bounded streaming reads, field validation, duplicate-key rejection, and strict parsing | Limits must fit the deployment |
| Invalid sibling denial | One valid CEP 27 sibling is sufficient | A malformed container still fails |
| Unrelated valid identity | An explicit verification can require an exact certificate identity and issuer | No channel standard distributes that requirement |
| Time-of-check package replacement during signing | The artifact is rehashed before bundle output is committed | An authorized signer can still sign malicious bytes |
| Embedded source path escape | Only regular recipe and bundle files are copied from a digest-checked snapshot. Unsafe archive paths and evidence paths with links, special files, or duplicates are rejected | Source evidence remains report-only |
| Source-audit resource exhaustion | Archive reads, decompression, YAML parsing, and declaration counts have explicit limits | Packages exceeding the audit limits cannot provide source evidence |

Source auditing does not use general package extraction. For `.conda`
packages, the original package filename selects the exact info component.
The {ref}`source-audit-limits` apply even when package publication evidence is
valid. These checks limit archive and recipe processing without changing signer
authorization.

The auditor cannot trust source declarations or a builder's
`attestation_verified` cache flag. A verified source result requires retained
bundles that match their recipe-declared digests. Their signed statements must
bind the source SHA-256. The auditor verifies the certificate, signature,
transparency-log material, and checkpoint before matching the signer to a
declared publisher. It rejects unsupported publisher ref constraints.

Rattler-Build 0.77.0 does not export these bundles. It also skips
transparency-log verification when verifying converted PyPI PEP 740 responses.
The auditor keeps those checks enabled and rejects converted bundles without
the required material. Supporting a conversion would require authenticated
conversion provenance and defined verification rules.

## Offline risk

Offline verification can validate embedded certificate and transparency-log
evidence against available local trust material. It cannot learn about a newly
rotated root, incident, or verifier update without an authenticated update
process.

A local trust configuration is not self-authenticating. Operators must protect
its distribution, freshness, and rollback behavior. Sidecars enter the cache
only after successful Sigstore and CEP 27 verification, then are rehashed and
cryptographically reverified on every read. Adjacent cache entries are used
only offline. The artifact-to-sidecar cache reference is discovery data, not a
verification receipt or authorization decision.

## Non-goals

The plugin does not prove:

- that a channel authorized a signer
- that signed package contents are benign or vulnerability-free
- that a recipe or source repository was reviewed
- reproducible or hermetic builds
- a SLSA level
- that a channel compared signer and uploader identities
- protection when local trust roots or the verifier itself are compromised
- repodata transparency

Those properties require separate standards, controls, and evidence.
