# Upstream integration contracts

The plugin uses accepted standards alongside unreleased conda APIs and draft
source-attestation formats.

## Status summary

| Interface | Status | Required by the plugin |
| --- | --- | --- |
| CEP 27 publication statement | Accepted | yes |
| [conda package-verifier hook](https://github.com/conda/conda/pull/16518) | Open conda pull request, unreleased | yes for install enforcement |
| [CEP 50 `attestations_sha256` field](https://github.com/conda/ceps/blob/main/cep-0050.md) | Accepted, pending conda metadata propagation | optional content-addressed transport |
| Prefix.dev adjacent `.v0.sigs` | Current service-specific compatibility | separate install fallback when the field is absent |
| [Recipe source attestations](https://github.com/conda/ceps/pull/168) | Open CEP proposal | optional audit input |
| Channel publisher delegation | No conda standard | unavailable |

## Current plugin contract

### Conda package-verifier hook

The plugin registers `conda_package_verifiers` directly against the unreleased API
in [conda/conda#16518](https://github.com/conda/conda/pull/16518). The locked
developer environments build a pinned revision from `jezdez/conda`'s
`feature/package-verifiers` branch as a conda package. Released conda versions
do not provide this hook.

The hook is disabled unless `plugins.conda_sigstore_enforce` is true. When
enabled, conda invokes the named verifier after validating the package size and
strongest available package digest and before extraction. Every registered
verifier must return successfully for extraction to proceed.

The callback receives:

- the selected `PackageRecord` or an explicit URL `MatchSpec`
- the read-only archive path
- the SHA-256 computed by conda

The callback raises `CondaVerificationError` to reject the archive. Callbacks
may run concurrently for different archives, may run more than once, and must
not mutate the archive.

The plugin requires the archive filename to match the selected record or URL.
For the CEP 50 transport, it also requires the selected record to preserve
`attestations_sha256`. Current conda `PackageRecord` objects and solver
conversion paths do not preserve that field, so real solver, install, and
installed-audit flows need a conda change before they can select the CEP 50
transport. The selected package URL and conda-supplied artifact SHA-256 are
sufficient only for the separate Prefix.dev adjacent compatibility path.

When only an extracted cache entry remains, conda must redownload the archive
or fail offline. A package-record digest does not authenticate extracted files.

### Install evidence selection

When enforcement is enabled:

1. a present, valid repodata `attestations_sha256` field selects
   `<artifact>.sigs.<attestations_sha256>`
2. an invalid `attestations_sha256` value is rejected before URL construction
3. without `attestations_sha256`, plugin enforcement policy requires adjacent
   `<artifact>.v0.sigs`
4. any selected retrieval, streaming-limit, digest, container, cryptographic,
   statement, or binding failure rejects the package
5. a present field never falls back to `.v0.sigs`

One cryptographically valid CEP 27 statement must bind the exact filename and
SHA-256. This is evidence-validity enforcement. It does not establish that the
channel authorized the authenticated signer.

### Prefix.dev compatibility

Prefix.dev `.v0.sigs` is explicit in verification and audit commands. The
install verifier also uses that deterministic adjacent name when no repodata
`attestations_sha256` field exists. This is service-specific plugin policy
outside CEP 50. Repodata discovery itself never probes for an undeclared
sidecar and never fetches the mutable `.sigs` URL.

## Repodata and source integration

### Repodata field preservation

[CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md) defines the optional scalar
`attestations_sha256` field on package records. It must contain exactly 64
lowercase hexadecimal characters. To remain usable after a solve, the field
must survive:

- monolithic and sharded repodata
- classic and libmamba solver conversion
- package-cache records
- prefix records and `repodata_record.json`
- repodata patching, JLAP, compression, mirroring, and indexing

The libmamba bridge must associate it with the exact artifact URL and filename
because `.conda` and `.tar.bz2` artifacts can otherwise share package identity
fields.

Current conda does not preserve `attestations_sha256` on `PackageRecord` or
through the solver conversions. Until conda adds that support, real solve,
install, package-cache, prefix-record, and installed-audit paths cannot consume
the CEP 50 field. The separate Prefix.dev adjacent path does not require this
field.

(channel-sidecar-publication)=
### Channel sidecar publication

`conda sigstore attest` emits one raw Bundle v0.3 object. It does not assemble
a sidecar array, modify repodata, or upload channel files.

A channel implementing CEP 50 must:

- associate one or more complete bundles with an immutable package artifact
- include every accepted attestation in the next published sidecar, including
  concurrent additions
- preserve existing bundle bytes and acceptance order, appending newly accepted
  bundles after them
- serialize the final nonempty bundle array once while preserving existing
  bundle bytes
- calculate the SHA-256 from the exact serialized bytes
- publish those bytes first at immutable `<artifact>.sigs.<sha256>`
- update mutable `<artifact>.sigs` to the same exact bytes for generic tooling
- place `attestations_sha256` in every relevant repodata representation only
  after publishing the immutable sidecar and updating the mutable URL
- retain old immutable URLs while the corresponding package remains available

A channel without a record of acceptance order may instead sort bundles by the
SHA-256 of their bytes. It must use that ordering consistently across all
sidecar revisions for the package. Transparency-log indexes and timestamps must
not be used as sort keys. The channel chooses how to collect and merge
additions, but concurrent additions must not be lost.

The exact field, endpoint, and container rules are in
[Standards and formats](standards.md).

### Source-evidence handoff

The proposal in [conda/ceps#168](https://github.com/conda/ceps/pull/168) is a
separate recipe and package-audit integration. `conda-sigstore` reads only its
embedded audit subset. See
[Source-attestation audit format](source-attestations.md).

Source and SLSA evidence do not authorize a CEP 27 publication signer and do
not assign a SLSA level.

Publisher delegation is a separate design problem. See
{ref}`publisher-delegation`.
