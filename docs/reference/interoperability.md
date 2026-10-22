# Pixi and Rattler interoperability

The interoperability tests use released tools and captured signed evidence.
They exercise real Sigstore verification without adding a Rust build or a
runtime dependency to `conda-sigstore`.

## Versions and scope

| Component | Version | Coverage |
| --- | --- | --- |
| Pixi | 0.82.0 | Runs the locked development and publishing environments |
| Rattler-Build | 0.77.0 | Builds and tests the conda package |
| `py-rattler` | 0.27.1 | Test-only Rust consumer for CEP 27 bundles and CEP 50 sidecars |
| Captured Rattler-Build producer | 0.74.0 | Supplies the real signed package used by offline tests |
| `conda-sigstore` | Current checkout | Verifies the captured Rust bundle and produces a bundle for the live Rust consumer test |

The released Python binding calls `rattler_sigstore` 0.2.2. Pixi 0.82.0 uses
0.2.3, and Rattler-Build 0.77.0 uses 0.2.5. The binding tests establish
compatibility with the released Python API and its native verifier. They do
not test every consumer crate version carried by the other tools.

The [fixture manifest](https://github.com/conda-incubator/conda-sigstore/blob/main/tests/fixtures/rattler/manifest.json)
records the package and sidecar digests, exact producer workflow, producer
version, and public trust-material sources. The fixture was signed by
`rattler-build publish --generate-attestation`. Its producer is older than the
current publishing-tool pin, so passing this fixture does not prove that a
new signing operation with Rattler-Build 0.77.0 succeeded.

## What the tests check

Normal tests load the captured bundle with configured local trust material.
They verify the certificate, signature, transparency-log inclusion, checkpoint,
package filename, SHA-256, and target channel. They also reject changed
artifacts, mismatched names or channels, invalid signatures, malformed
sidecars, and incorrect advertised sidecar digests.

| Input or operation | `conda-sigstore` | `py-rattler` 0.27.1 |
| --- | --- | --- |
| Advertised immutable CEP 50 sidecar | Supported | Supported |
| Prefix.dev adjacent `.v0.sigs` discovery | Explicit compatibility transport | Not automatic |
| Prefix.dev bundle array copied to an advertised immutable sidecar | Supported | Supported |
| Valid bundle with a parseable invalid-signature sibling | Valid evidence is retained | Valid evidence can satisfy verification |
| Valid bundle with an unparseable bundle sibling | Invalid sibling is reported separately | The whole sidecar is rejected during parsing |
| Configured local trust root | Supported | Supported |

The Python tests exercise both `SidecarTransport.load_repodata()` and
`SidecarTransport.load_prefix()`. The native binding reads a local `file://`
package URL and its advertised immutable sidecar. This tests the native
retrieval and digest checks without requiring an external channel.

Frozen trust material makes these tests repeatable. It is not a deployment
trust-root update mechanism or evidence of freshness. Operators remain
responsible for authenticated distribution, updates, and rollback protection
when configuring their own trust material.

## Run the checks

Run all normal tests, including both consumers, through the locked environment:

```console
pixi run --locked -e test test
```

For just the captured-evidence cases:

```console
pixi run --locked -e test pytest tests/test_rattler.py tests/test_py_rattler.py
```

The existing Sigstore staging workflow also signs a synthetic package with
`conda-sigstore` and verifies its bundle with the Rust consumer. This check
requires `CONDA_SIGSTORE_STAGING_INTEROP=1` and
`CONDA_SIGSTORE_STAGING_IDENTITY`, uses the `live_interop` marker, and is
excluded from normal tests. It runs in the Live interoperability workflow,
where GitHub supplies the OIDC identity.

## Limits of the result

Pixi signing and upload support does not enable install-time attestation
verification. [Pixi 0.82.0's installer](https://github.com/prefix-dev/pixi/blob/v0.82.0/crates/pixi_command_dispatcher/src/install_binary.rs)
does not configure Rattler's verification policy. Its
[Prefix upload command](https://github.com/prefix-dev/pixi/blob/v0.82.0/docs/reference/cli/pixi/upload/prefix.md)
supports attestation generation, while the
[Anaconda upload command](https://github.com/prefix-dev/pixi/blob/v0.82.0/docs/reference/cli/pixi/upload/anaconda.md)
has no equivalent option.

The Rust checks here require the target channel to match and accept the
cryptographically authenticated identity as evidence. They do not establish
that a channel authorized that identity to publish. Publisher authorization
and persistent signer policy remain separate work.

Relevant upstream interfaces are the
[released Python verification API](https://github.com/conda/rattler/blob/py-rattler-v0.27.1/py-rattler/rattler/sigstore/sigstore.py),
[CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md), and the
[native publication statement generator](https://github.com/conda/rattler/blob/rattler_upload-v0.13.5/crates/rattler_upload/src/upload/attestation.rs).
