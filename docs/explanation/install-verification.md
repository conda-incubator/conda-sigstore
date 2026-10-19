# Installation verification across package managers

Package hashes and Sigstore attestations answer different questions. A hash
checks that downloaded bytes match a previously selected digest. A Sigstore
attestation checks that an authenticated identity signed a statement about
those bytes. Neither check alone establishes that the identity was authorized
to publish a package.

## Client behavior observed on 2026-08-11

This comparison reflects the linked public documentation on 2026-08-11. Pinned
source links identify the exact Pixi and uv revisions reviewed.

| Client | Artifact check during installation | Sigstore attestation check during installation |
| --- | --- | --- |
| pip | Checks an index-advertised download hash for corruption. `--require-hashes` requires locally supplied hashes for all resolved requirements. | None. PyPI documents a separate `pypi-attestations verify pypi` command for consumer verification. |
| uv | Records selected index hashes in `uv.lock` and verifies hashes supplied in requirements files. `--require-hashes` requires complete hash coverage. | None. `uv publish` discovers and uploads adjacent PEP 740 attestations, but does not generate them or verify them during installation. |
| npm | Uses `package-lock.json` to select exact dependency versions and records Subresource Integrity values for downloaded artifacts. | None. `npm audit signatures` is a separate command that verifies registry signatures and available provenance attestations after dependencies are installed. |
| Pixi | Verifies conda and PyPI package checksums recorded in `pixi.lock` when an artifact is installed or reused from cache. | None. Pixi creates or uploads Sigstore attestations for Prefix.dev publishing and documents external consumer verification with `gh` or `cosign`. |
| conda with conda-sigstore | Conda retains its package digest checks. | An opt-in direct package verifier requires valid CEP 27 evidence from a repodata-hash-pinned immutable sidecar or the separate deterministic Prefix.dev adjacent sidecar. Selecting the repodata-advertised sidecar also requires conda to preserve `attestations_sha256`. It is an integration preview against conda/conda#16518. |

The relevant primary documentation is:

- [pip secure installs](https://pip.pypa.io/en/stable/topics/secure-installs/)
- [PyPI consuming attestations](https://docs.pypi.org/attestations/consuming-attestations/)
- [uv package publishing](https://docs.astral.sh/uv/guides/package/#uploading-attestations-with-your-package)
- [uv package-index hashes](https://docs.astral.sh/uv/concepts/indexes/#requiring-a-hash-algorithm)
- [npm package-lock format](https://docs.npmjs.com/cli/configuring-npm/package-lock-json/)
- [npm registry signature verification](https://docs.npmjs.com/verifying-registry-signatures/)
- [npm provenance verification](https://docs.npmjs.com/generating-provenance-statements/#verifying-provenance-attestations)
- [Pixi supply-chain security](https://github.com/prefix-dev/pixi/blob/b91a274c9db6d8ca3586bc763f04354e927d971d/docs/security.md)
- [Pixi Prefix.dev upload options](https://github.com/prefix-dev/pixi/blob/b91a274c9db6d8ca3586bc763f04354e927d971d/docs/reference/cli/pixi/upload/prefix.md)

PyPI is the repository in this comparison, not pip. PyPI validates supported
attestations at upload, associates publish attestations with Trusted Publisher
identities, and exposes provenance through its Integrity API. That gives a
consumer enough repository context to perform an authorization check. pip does
not consume that evidence during an ordinary install.

uv's attestation support is also on the producer side. Its publisher passes
adjacent PEP 740 JSON objects to a supporting index. Its
[current upload implementation](https://github.com/astral-sh/uv/blob/a50af60fb4162d7f94812d64c481c30a0200b6d8/crates/uv-publish/src/lib.rs)
notes that it does not validate the interior attestation structure beyond JSON
before upload. This is transport behavior, not consumer verification.

npm also separates installation from signature and provenance verification.
`npm audit signatures` runs after `npm install` or `npm ci`, checks registry
signatures and available provenance attestations, and reports an error when a
registry that advertises signing keys omits or provides an invalid signature.
It verifies provenance when present rather than requiring every package to
carry it. It does not expose a consumer-managed identity policy or a reusable
verification receipt.

Pixi checks locked artifact digests during installation. Its Sigstore path is
separate and producer-oriented. `pixi publish --generate-attestation` and
`pixi upload prefix --generate-attestation` create and upload evidence for
Prefix.dev. The Pixi security guide directs consumers to external Sigstore
tools instead of claiming that `pixi install` verifies those attestations.

Rattler also exposes a native verifier through the released `py-rattler`
binding. This project uses it as a test-only consumer, including configured
local trust roots. See [Pixi and Rattler interoperability](../reference/interoperability.md)
for tested versions, transport support, and the separate live signing check.
This does not change Pixi's installation behavior described above.

The closest existing consumer pattern is PyPI's separate
`pypi-attestations verify pypi --repository ...` command. The repository is an
independent trust input. `conda sigstore verify` offers the corresponding
low-level choice through paired `--cert-identity` and
`--cert-oidc-issuer` options. They apply to one command and do not create
channel policy.

## Why enforcement has one switch

The plugin keeps installation enforcement either disabled or fail-closed.
`conda sigstore audit` is the nonblocking way to measure evidence coverage
before enabling enforcement. An `ignore` mode would duplicate the disabled
state, while a `warn` mode inside installation would duplicate the audit
workflow and make invalid evidence easy to overlook.

A client-maintained policy language would not establish who a channel
authorized to publish. That information needs to come from a standardized
channel delegation, like PyPI's Trusted Publisher relationship, rather than a
new `.condarc` identity allowlist.

Verification reports are output, not reusable trust decisions. Trust material,
transparency evidence, and verifier behavior can change between commands. This
matches pip's treatment of its
[installation report](https://pip.pypa.io/en/latest/reference/installation-report/),
which is not accepted as install input. The plugin therefore verifies evidence
fresh instead of caching receipts.

## Why verification runs before extraction

An audit can measure evidence coverage after installation, but it cannot prove
that invalid evidence was rejected before package files reached a prefix. The
package-verifier hook makes an opt-in decision before extraction while conda
still has the selected URL, expected digest, and archive.

The verifier uses the same evidence-validation pipeline as the explicit command
instead of caching a receipt or reimplementing Sigstore inside conda. Exact
transport behavior belongs in [Commands](../reference/commands.md), and the
setting and recovery controls belong in
[Configuration](../reference/configuration.md) and
[Configure verification](../how-to/configure-verification.md).

## Upstream status

[conda/conda#16518](https://github.com/conda/conda/pull/16518) provides the
pre-extraction verifier hook. This repository's locked developer environments
build a pinned revision from `jezdez/conda`'s `feature/package-verifiers`
branch as a conda package. No released conda version provides that API yet.

The current conda `PackageRecord` model and solver conversion paths do not
preserve CEP 50's `attestations_sha256` field. A separate conda change is
required before real solver and install flows can select
`<artifact>.sigs.<attestations_sha256>`. The adjacent Prefix.dev `.v0.sigs`
compatibility path needs only the selected package URL and digest. A rejection
prevents that archive from being extracted and linked, although concurrent
cache work for other packages may already have completed.

The exact upstream contract is listed in
[Upstream integration contracts](../reference/upstream-contracts.md).

For concrete `conda-lockfiles` and `conda-workspaces` commands, see
[Verify locked environments during installation](../how-to/verify-locked-environments.md).
