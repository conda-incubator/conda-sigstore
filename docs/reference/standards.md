# Standards and formats

`conda-sigstore` implements accepted CEP 27 publication statements and CEP 50
sidecar distribution. It also supports Prefix.dev's compatibility transport
and draft source-attestation evidence.

| Contract | Status | Use in this plugin |
| --- | --- | --- |
| [CEP 27](https://github.com/conda/ceps/blob/main/cep-0027.md) publication statement | Accepted CEP | Required package statement |
| [Sigstore Bundle v0.3](https://github.com/sigstore/protobuf-specs/blob/main/protos/sigstore_bundle.proto) | Published Sigstore format | Signed evidence container |
| [CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md) sidecar distribution | Accepted CEP | Repodata transport, pending conda metadata propagation |
| Prefix.dev `.v0.sigs` | Current service-specific behavior | Compatibility transport |
| [conda/ceps#168](https://github.com/conda/ceps/pull/168) source attestations | Open proposal | Audit-only embedded source evidence |

(cep-27-publication-statement)=
## CEP 27 publication statement

CEP 27 defines a publication attestation as an
[in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)
with this predicate type:

```text
https://schemas.conda.org/attestations-publish-1.schema.json
```

A statement created by `conda sigstore attest` has this shape:

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [
    {
      "name": "example-1.0-0.conda",
      "digest": {
        "sha256": "<artifact digest>"
      }
    }
  ],
  "predicateType": "https://schemas.conda.org/attestations-publish-1.schema.json",
  "predicate": {
    "targetChannel": "https://conda.example.org/team"
  }
}
```

The plugin requires exactly one subject. The subject name must be a bare
`.conda` or `.tar.bz2` package filename containing name, version, and build
components. Its digest mapping must contain only a SHA-256 of the exact package
bytes.

CEP 27 permits an absent target channel. The plugin represents that as an
omitted or null `predicate`. When `predicate` is an object, it must contain a
valid credential-free HTTP or HTTPS `targetChannel` without a query, fragment,
or trailing slash. `conda sigstore attest` always requires and records the
target channel. Verification compares an included claim only when the caller
supplies an expected channel.

CEP 27 is a publication claim. It is not SLSA build provenance and does not
prove source, recipe, builder, or build-process properties.

## Sigstore Bundle v0.3

The CEP 27 statement is DSSE signed and stored in one Sigstore Bundle v0.3
object. The bundle contains the signing certificate and transparency-log
material. It may also contain supported signed timestamp material.

`conda sigstore attest` writes one bundle object as
`<artifact>.sigstore.json`. A channel sidecar is a nonempty JSON array of one
or more complete bundle objects. Multiple entries are independent attestations
or signatures. They are not described as countersignatures by this plugin.

One cryptographically valid, artifact-bound CEP 27 entry is sufficient for a
verified package result. Invalid, unsupported, or nonmatching siblings remain
visible as failures but do not overturn a valid entry.

## Tool responsibilities

| Tool | Behavior | Conda-specific boundary |
| --- | --- | --- |
| `sigstore sign` | Creates a message signature over bytes | Does not create a CEP 27 statement |
| `sigstore verify identity` | Verifies Sigstore material against an identity and issuer | Does not enforce the plugin's complete CEP 27 filename, predicate, and target-channel checks |
| `conda sigstore attest` | Creates and signs one strict CEP 27 statement | Writes evidence but does not upload it |
| `conda sigstore verify` | Verifies Sigstore material, CEP 27 artifact binding, optional target channel, and an optional exact signer pair | Does not discover channel publisher delegation |
| opt-in package verifier | Requires valid CEP 27 evidence before extraction | Enforces evidence validity, not signer authorization |
| Rattler-Build `--generate-attestation` | Creates CEP 27 bundles during Prefix.dev publication | Prefix.dev producer path |
| `actions/attest` | Creates a Sigstore-backed in-toto attestation with a caller-supplied predicate | Workflow must create the exact CEP 27 subject and predicate expected here |

See [Verify with sigstore-python](../how-to/verify-with-sigstore.md) and
[Publish attestations to Prefix.dev](../how-to/publish-prefix.md) for operator
workflows.

## CEP 50 repodata sidecar transport

[CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md) was accepted on
23 September 2026. It defines attestation sidecar distribution, called the
`repodata` transport in this plugin.

For `example-1.0-0.conda`, a channel serves the same exact sidecar bytes at two
URLs:

```text
example-1.0-0.conda.sigs
example-1.0-0.conda.sigs.<sha256>
```

The mutable `.sigs` URL supports generic tooling. Conda clients discover the
sidecar through repodata and fetch only the immutable content-addressed URL.
The package record contains one scalar field:

```json
{
  "attestations_sha256": "37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570"
}
```

The plugin applies these rules:

- `attestations_sha256` is a string containing exactly 64 lowercase
  hexadecimal characters
- an invalid field is rejected before a sidecar URL is constructed
- the client fetches `<artifact>.sigs.<attestations_sha256>`, never the mutable
  `.sigs` URL
- the configured implementation limit is enforced while the response streams
- the exact sidecar SHA-256 is verified before JSON parsing
- the sidecar is a nonempty JSON array of bundle objects
- bundle position does not affect verification or signer matching
- absence of `attestations_sha256` means no sidecar is advertised, is not a
  protocol error, and does not cause a request
- the HTTP `Content-Type` is advisory and does not decide bundle validity

A present `attestations_sha256` field selects the repodata transport.
Invalid-field, retrieval, streaming-limit, digest, container, or verification
failure does not fall back to `.v0.sigs`.

CEP 27 defines verification of publication statements, including filename and
SHA-256 binding. CEP 50 adds no publication-statement verification rules. The
reported `bundle_index` identifies evidence within the sidecar and implies no
trust, freshness, or preference.

CEP 50 also defines channel requirements for preserving accepted bundles
and publishing concurrent additions. See
[Channel sidecar publication](channel-sidecar-publication)
for the ordering and publication rules.

Current conda `PackageRecord` objects and solver conversion paths do not
preserve `attestations_sha256`. A conda change is therefore required before
real solver, install, package-cache, prefix-record, and installed-audit flows
can select this transport.

CEP 50 leaves trusted signer identities, TOFU, lockfile policy, and install
enforcement to separate specifications or tool policy. It does not define
upload authorization or channel admission rules. Its acceptance does not
provide conda's unreleased package-verifier hook or the metadata propagation
needed by this plugin.

## Prefix.dev compatibility transport

The current Prefix.dev producer path used by Pixi, Rattler-Build, and
`rattler_upload` publishes `<artifact>.v0.sigs` as a JSON array of Bundle v0.3
objects. Existing Prefix.dev channels do not advertise `attestations_sha256`
in repodata.

Explicit `.v0.sigs` input keeps the weaker discovery and integrity model
visible in verification and audit commands. The opt-in install verifier also
uses this deterministic adjacent name when the selected repodata record has no
`attestations_sha256` field. That fallback is plugin policy outside CEP 50.
It binds the signed CEP 27 statement to the package SHA-256 supplied by conda.

Public client behavior does not establish whether the proprietary Prefix.dev
server compares a bundle signer with the upload identity. The plugin reports
the authenticated signer without claiming that Prefix.dev authorized it.

## Draft source-attestation evidence

[conda/ceps#168](https://github.com/conda/ceps/pull/168) is an open proposal
for declaring and preserving source attestations in recipes and built
packages. It remains a draft, separate from accepted CEP 27 publication
statements and CEP 50 sidecar distribution.

`conda sigstore audit --sources` implements an audit-only subset over retained
package archives. It reads Rattler-Build 0.77.0 declarations under
`recipe.source` and their serialized GitHub and GitLab publisher mappings.
It rejects unsupported ref constraints. See
[Source-attestation audit format](source-attestations.md) for the parser and
bundle checks.
Source evidence cannot authorize a CEP 27 publication signer.

Rattler-Build 0.77.0 verifies source downloads but does not export the bundles
and recipe references this auditor needs. Supported declarations produce a
`missing` source result. The auditor's embedded `verified` descriptors remain
experimental. [Rattler-Build #2721](https://github.com/prefix-dev/rattler-build/pull/2721)
covers remote attestation discovery and does not define how to export evidence.

Generic SLSA Provenance v1 does not designate one resolved dependency as the
source. The plugin reports all materials without guessing which one represents
the source or assigning a SLSA level.

Converted PEP 740 or PyPI bundles without canonical Rekor entries are rejected.
The draft embedded index does not authenticate bundle-conversion provenance,
so the plugin does not disable Sigstore transparency-log verification for
those bundles.
