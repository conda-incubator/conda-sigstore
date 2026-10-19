# Verify Prefix.dev .v0.sigs sidecars

Prefix.dev's `.v0.sigs` compatibility transport serves a JSON bundle array at
`<channel>/<subdir>/<artifact>.v0.sigs`.

[CEP 50 repodata sidecars](../reference/standards.md) use
`attestations_sha256` to select an immutable `.sigs.<sha256>` URL.

## Verify a sidecar explicitly

Download the fixed public package:

::::{tab-set}
:::{tab-item} Linux and macOS

```console
curl --fail --location --remote-name \
  https://prefix.dev/sigstore-example/linux-64/signed-package-2.1.0-hb0f4dca_0.conda
```

:::
:::{tab-item} PowerShell

```powershell
Invoke-WebRequest `
  -Uri https://prefix.dev/sigstore-example/linux-64/signed-package-2.1.0-hb0f4dca_0.conda `
  -OutFile signed-package-2.1.0-hb0f4dca_0.conda
```

:::
::::

Pass its adjacent sidecar URL explicitly:

```console
conda sigstore verify signed-package-2.1.0-hb0f4dca_0.conda \
  --bundle https://prefix.dev/sigstore-example/linux-64/signed-package-2.1.0-hb0f4dca_0.conda.v0.sigs \
  --channel https://prefix.dev/sigstore-example
```

The command should report `verified`, the GitHub Actions certificate identity,
and `https://prefix.dev/sigstore-example` as the target channel. JSON output
sets `prefix_sidecar` to `true`.

## Require evidence during installation

Use process-scoped enforcement for the fixed Linux package:

::::{tab-set}
:::{tab-item} Linux and macOS

```console
CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE=true conda create \
  --name sigstore-example \
  --yes \
  --override-channels \
  --channel https://prefix.dev/sigstore-example \
  --subdir linux-64 \
  --solver classic \
  --no-deps \
  signed-package=2.1.0=hb0f4dca_0
```

:::
:::{tab-item} PowerShell

```powershell
$env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE = 'true'
conda create `
  --name sigstore-example `
  --yes `
  --override-channels `
  --channel https://prefix.dev/sigstore-example `
  --subdir linux-64 `
  --solver classic `
  --no-deps `
  signed-package=2.1.0=hb0f4dca_0
Remove-Item Env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE
```

:::
::::

The environment is created only after the adjacent bundle verifies and binds
the exact package. Remove the example environment when finished:

```console
conda env remove --name sigstore-example
```

## Account for the transport limit

Current Prefix.dev repodata does not commit to the `.v0.sigs` bytes. The
verified statement still binds the exact package, but the result does not
establish Prefix.dev's publisher-admission policy.

See [Publish attestations to Prefix.dev](publish-prefix.md) for the producer
workflow.
