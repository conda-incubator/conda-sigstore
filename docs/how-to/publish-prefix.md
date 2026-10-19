# Publish attestations to Prefix.dev

Prefix.dev currently supports Trusted Publishing and Sigstore attestations in
its Rattler-Build upload path. This guide shows the recommended automatic path,
then the manual path for a bundle created by `conda-sigstore`.

These are Prefix-specific producer workflows. Prefix.dev serves uploaded
bundles through its `.v0.sigs` transport. The separate transport in accepted
[CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md) uses repodata
`attestations_sha256` plus mutable `.sigs` and immutable `.sigs.<sha256>`
endpoints.

You need a Prefix.dev channel, a GitHub repository, a built conda package, and
permission to configure Trusted Publishing for both services.

## Configure repository access

Create the target channel, then open **Settings → Repository Access** and add a
trusted publisher. Specify the GitHub owner, repository, and exact workflow
filename allowed to upload. Prefix documents this setup in its
[Repository Access guide](https://prefix.dev/docs/prefix/channels/access).

The workflow needs `id-token: write` so Rattler-Build can obtain an ambient
OIDC identity. It does not need a long-lived Prefix API key.

## Use Rattler-Build's automatic path

Prefix recommends Rattler-Build's `--generate-attestation` option. It creates
one CEP 27 bundle per package and uploads each package and bundle together.

```yaml
name: Publish conda package

on:
  push:
    tags:
      - "v*"

permissions: {}

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
      - uses: prefix-dev/rattler-build-action@1ca5f45832f419a46d1326ccc5861d7e14d67c44 # v0.2.39
        with:
          setup-only: true
      - name: Build, attest, and publish
        run: |
          rattler-build publish ./recipe.yaml \
            --to https://prefix.dev/MY-CHANNEL \
            --generate-attestation
```

Replace `MY-CHANNEL` and the recipe path. The trusted-publisher configuration
must name this workflow file. The option works only with Prefix Trusted
Publishing in a supported CI environment. It cannot be combined with an API
key.

Rattler-Build's current
[Sigstore guide](https://rattler-build.prefix.dev/latest/sigstore/) documents
this as the preferred path, especially for multi-output recipes because each
package requires its own CEP 27 statement.

## Upload a conda-sigstore bundle manually

Use this path when the package has already been built or when you need to create
the CEP 27 bundle separately. Both commands use the ambient CI workload
identity and request their own service-specific OIDC tokens:

```console
conda sigstore attest ./output/linux-64/example-1.0-0.conda \
  --target-channel https://prefix.dev/MY-CHANNEL

rattler-build upload prefix \
  --channel MY-CHANNEL \
  ./output/linux-64/example-1.0-0.conda \
  --attestation ./output/linux-64/example-1.0-0.conda.sigstore.json
```

Attach attestations to exactly one package per upload. A CEP 27 statement has
exactly one subject, so do not sign a glob that resolves to multiple packages
as one statement.

The upload identity and the Sigstore signing identity are separate credentials.
Public Prefix.dev documentation does not define their relationship as a
portable consumer-authorization rule.

## Use GitHub's attestation action manually

GitHub's standard attestation action can also create the custom CEP 27
predicate. Invoke it once for each package and pass its `bundle-path` output to
Rattler-Build. This example is for a public repository, where the action uses
the public Sigstore instance. GitHub uses a separate Sigstore instance for
private and internal repositories, whose Prefix interoperability is not
established here.

```yaml
permissions:
  contents: read
  id-token: write
  attestations: write

steps:
  - uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2
    id: attest
    with:
      subject-path: ./output/linux-64/example-1.0-0.conda
      predicate-type: https://schemas.conda.org/attestations-publish-1.schema.json
      predicate: '{"targetChannel":"https://prefix.dev/MY-CHANNEL"}'
  - name: Upload package and bundle
    run: |
      rattler-build upload prefix \
        --channel MY-CHANNEL \
        ./output/linux-64/example-1.0-0.conda \
        --attestation "${{ steps.attest.outputs.bundle-path }}"
```

The action also stores the attestation in GitHub's attestation API. Verify that
copy with the GitHub CLI:

```console
gh attestation verify ./example-1.0-0.conda \
  --owner MY-GITHUB-OWNER \
  --predicate-type https://schemas.conda.org/attestations-publish-1.schema.json
```

GitHub verifies against the selected repository owner and predicate type. Use
`conda sigstore verify` as well when you need CEP 27's exact filename,
single-subject, SHA-256, and target-channel checks.

## Verify the Prefix-served copy

Download the package bytes and the currently served Prefix.dev sidecar:

```console
curl --fail --location --remote-name \
  https://prefix.dev/MY-CHANNEL/linux-64/example-1.0-0.conda
curl --fail --location --remote-name \
  https://prefix.dev/MY-CHANNEL/linux-64/example-1.0-0.conda.v0.sigs
```

Verify them together and supply the intended channel:

```console
conda sigstore verify ./example-1.0-0.conda \
  --bundle ./example-1.0-0.conda.v0.sigs \
  --channel https://prefix.dev/MY-CHANNEL
```

The result verifies the package binding and reports the actual certificate
identity and issuer. The first output line should end in `verified`. Current
Prefix.dev repodata does not pin the `.v0.sigs` bytes, so direct verification
selects this transport explicitly.

For the transport limitation and live fixture, see
[Verify Prefix.dev .v0.sigs sidecars](prefix-sidecars.md).
