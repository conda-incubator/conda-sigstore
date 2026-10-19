# Configure verification

Install verification is disabled by default. Audit your channels before
enabling it because every package extracted by an enforced command must have
valid evidence.

:::{warning}
This preview requires the unreleased conda API in
[conda/conda#16518](https://github.com/conda/conda/pull/16518).
:::

## Test one command first

Use a process-scoped environment variable so the setting disappears after the
command.

::::{tab-set}
:::{tab-item} Linux and macOS

```console
CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE=true conda install PACKAGE
```

:::
:::{tab-item} PowerShell

```powershell
$env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE = 'true'
conda install PACKAGE
Remove-Item Env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE
```

:::
::::

Replace `PACKAGE` with a package from a channel that serves valid adjacent
Prefix.dev evidence or a CEP 50 content-addressed sidecar advertised through
`attestations_sha256`. Missing or invalid evidence blocks the package before
extraction.

Current conda `PackageRecord` objects and solver conversion paths do not
preserve `attestations_sha256`. Real solver and install flows need a conda
change before they can select the CEP 50 sidecar. Until then, enforcement can
use only the separate adjacent Prefix.dev `.v0.sigs` compatibility path.

## Enable enforcement persistently

After a successful trial, enable the setting in the active conda configuration:

```console
conda config --set plugins.conda_sigstore_enforce true
conda config --show plugins.conda_sigstore_enforce
```

The displayed value should be `true`.

Disable enforcement before using channels that do not publish compatible
evidence:

```console
conda config --set plugins.conda_sigstore_enforce false
```

If an enforced operation prevents normal recovery, override the persistent
value for the repair command:

::::{tab-set}
:::{tab-item} Linux and macOS

```console
CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE=false \
  conda config --set plugins.conda_sigstore_enforce false
```

:::
:::{tab-item} PowerShell

```powershell
$env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE = 'false'
conda config --set plugins.conda_sigstore_enforce false
Remove-Item Env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE
```

:::
::::

## Change operational inputs

The structured setting controls the input limit and optional Sigstore client
trust configuration:

```yaml
plugins:
  conda_sigstore:
    max_sidecar_bytes: 10485760
    trust_config: /etc/conda/sigstore/client-trust-config.json
```

`max_sidecar_bytes` is applied before JSON and bundle parsing. The trust file
must be a complete Sigstore client trust configuration, not only a trusted-root
document. Use `null` to use Sigstore's production trust configuration.

Provision operator-managed trust configuration through an authenticated
process. The plugin does not establish its freshness or rollback protection.

These settings do not authorize publishers. A successful install check proves
that valid evidence binds the package and reports the signer.

See [Configuration](../reference/configuration.md) for the exact fields and
[Verify offline](offline.md) before using local trust material without network
access.
