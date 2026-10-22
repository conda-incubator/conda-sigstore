# conda-sigstore

`conda-sigstore` creates and verifies Sigstore attestations for conda packages.
It can also audit installed environments and, when explicitly enabled, reject a
package before extraction when acceptable evidence is unavailable or invalid.

The project is part of [conda-incubator](https://github.com/conda-incubator),
maintained by Jannis Leidel and Travis Hathaway. It is alpha software,
distributed through PyPI and the personal `jezdez` channel on Anaconda.org.
The opt-in install integration requires the unreleased package-verifier API in
[conda/conda#16518](https://github.com/conda/conda/pull/16518). The draft
source-evidence formats may still change incompatibly.

## What it does

- Verify a package against a local or remote Sigstore bundle.
- Create a signed [CEP 27](https://github.com/conda/ceps/blob/main/cep-0027.md)
  publication statement.
- Audit installed packages for publication, provenance, and recipe source
  evidence.
- Require valid CEP 27 evidence before conda extracts a package.
- Read CEP 50 repodata-advertised immutable `.sigs.<sha256>` sidecars and,
  separately, Prefix.dev's current `.v0.sigs` convention.

The repodata transport follows accepted
[CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md). Current conda
`PackageRecord` objects do not preserve its `attestations_sha256` field, so
real solver, install, and installed-environment audit flows require a
corresponding conda change before they can select this transport. CEP 50
does not define trusted signer identities or install enforcement policy.

## Install

conda-sigstore requires Python 3.11 or newer. Install it in the Python
environment that owns the `conda` executable.

For a standard conda installation, activate `base` and install 0.1.2 from the
personal `jezdez` channel, with dependencies from conda-forge:

```console
conda activate base
conda install --override-channels -c jezdez -c conda-forge "conda-sigstore=0.1.2"
```

The [installation guide](https://conda-incubator.github.io/conda-sigstore/how-to/install/)
also documents PyPI installation, the source preview, and the separate
requirements for install enforcement.

## Commands

```console
conda sigstore attest PACKAGE --target-channel URL [--output PATH]
conda sigstore verify ARTIFACT --bundle PATH_OR_URL [--channel URL] \
  [--cert-identity IDENTITY --cert-oidc-issuer URL] [--json]
conda sigstore audit [-n ENV | -p PREFIX] [--sources] [--prefix-sidecars] [--json]
```

Choose the path that matches your task:

- [Verify a public package](https://conda-incubator.github.io/conda-sigstore/tutorials/getting-started/)
- [Sign a package](https://conda-incubator.github.io/conda-sigstore/tutorials/sign-package/)
- [Audit an installed environment](https://conda-incubator.github.io/conda-sigstore/how-to/audit-environment/)
- [Configure install verification](https://conda-incubator.github.io/conda-sigstore/how-to/configure-verification/)
- [Publish attestations to Prefix.dev](https://conda-incubator.github.io/conda-sigstore/how-to/publish-prefix/)
- [Look up commands and output formats](https://conda-incubator.github.io/conda-sigstore/reference/commands/)

## Security boundary

A successful result proves that Sigstore verified the bundle and that its CEP
27 statement binds the package filename and SHA-256. It reports the
authenticated signer and can compare an included target-channel claim.

It does not prove that the signer was authorized to publish to that channel,
that the package was built safely, or that its contents are benign.

Read the
[security model](https://conda-incubator.github.io/conda-sigstore/explanation/security-model/)
and report vulnerabilities according to the
[security policy](https://github.com/conda-incubator/conda-sigstore/security/policy).

## Development

```console
pixi run --locked -e dev check
pixi run --locked -e test test
pixi run --locked -e test bench
pixi run --locked -e docs docs
```

See the
[contribution guide](https://github.com/conda-incubator/conda-sigstore/blob/main/CONTRIBUTING.md)
for the full development and release workflow. `conda-sigstore` is licensed
under the BSD 3-Clause License.
