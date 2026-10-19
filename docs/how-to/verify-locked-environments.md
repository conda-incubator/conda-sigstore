# Verify locked environments during installation

Install `conda-sigstore`, `conda-lockfiles`, and `conda-workspaces` in the
Python environment that owns the `conda` command. The source-preview test
environment already includes all three.

For a future supported installation, install the companion plugins from
conda-forge into the owning conda prefix:

::::{tab-set}
:::{tab-item} Linux and macOS

```console
conda install --prefix "$(conda info --base)" --channel conda-forge \
  "conda-lockfiles>=0.2.1" "conda-workspaces>=0.8"
```

:::
:::{tab-item} PowerShell

```powershell
conda install --prefix (conda info --base) --channel conda-forge `
  'conda-lockfiles>=0.2.1' 'conda-workspaces>=0.8'
```

:::
::::

Confirm that conda discovers their commands:

```console
conda create --help
conda workspace --help
```

## Install from a lockfile

Enable verification for one `conda create` invocation.

::::{tab-set}
:::{tab-item} pixi.lock

```console
CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE=true \
  conda create --name example --file pixi.lock --format rattler-lock-v6
```

:::
:::{tab-item} conda-lock.yml

```console
CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE=true \
  conda create --name example --file conda-lock.yml --format conda-lock-v1
```

:::
::::

On PowerShell, set and remove the environment variable around the same command:

```powershell
$env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE = 'true'
conda create --name example --file pixi.lock --format rattler-lock-v6
Remove-Item Env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE
```

Every package archive extracted by the command must have one valid CEP 27
statement that binds its exact filename and SHA-256. Missing or invalid evidence
fails the installation.

## Install a workspace

Run the locked install from the workspace root:

::::{tab-set}
:::{tab-item} Linux and macOS

```console
CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE=true \
  conda workspace install --locked
```

:::
:::{tab-item} PowerShell

```powershell
$env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE = 'true'
conda workspace install --locked
Remove-Item Env:CONDA_PLUGINS_CONDA_SIGSTORE_ENFORCE
```

:::
::::

The workspace command routes conda package extraction through the same verifier
hook. The manifest still defines intent and the lockfile still defines the
selected package set.

## Know what remains outside the hook

- Keep lockfile SHA-256 entries. They select exact bytes while Sigstore verifies
  signed evidence for those bytes.
- Locked records that do not retain CEP 50's `attestations_sha256` field require
  adjacent `<artifact>.v0.sigs` evidence under the separate Prefix.dev
  compatibility policy. Current conda `PackageRecord` objects do not preserve
  that field.
- Pip packages and unchanged prefix contents are not newly verified by this
  hook. With enforcement enabled, conda does not reuse an extracted-only cache
  entry. It finds or redownloads the archive and verifies it before extraction,
  or fails offline.
- Offline installation also needs prepared package, repodata, sidecar, and
  trust-material caches. See [Verify offline](offline.md).

Use [Audit an environment](audit-environment.md) to inspect an existing prefix.
