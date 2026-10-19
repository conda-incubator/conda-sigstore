# Install conda-sigstore

`conda-sigstore` must be installed in the Python environment that owns the
`conda` executable. A plugin installed in an unrelated environment is not
discovered by that `conda` executable. The environment must use Python 3.11 or
newer.

## Install from Anaconda.org

The personal [`jezdez` channel](https://anaconda.org/jezdez/conda-sigstore)
provides the noarch conda package. Its dependencies come from conda-forge.
For a standard conda installation, activate `base` and install 0.1.3:

```console
conda activate base
conda install --override-channels -c jezdez -c conda-forge "conda-sigstore=0.1.3"
conda sigstore --help
```

The help output should list `attest`, `verify`, and `audit`. Start with
[Verify a public package](../tutorials/getting-started.md).
See [Verify a conda-sigstore publication](verify-project-package.md) to check
which of this project's conda packages have CEP 27 evidence and retrieve it
from GitHub.

## Install from PyPI with conda-pypi

conda 26.5 and newer include the
[`conda-pypi` plugin](https://conda.github.io/conda-pypi/quickstart/), which can
download the published wheel from PyPI, convert it to a conda package, and
install it into the environment that owns conda.

For a standard conda installation, activate `base` and install 0.1.3 from PyPI:

```console
conda activate base
conda pypi install "conda-sigstore==0.1.3"
conda sigstore --help
```

`conda pypi install` is pending removal in conda 27.9. If the command is not
available, use the pip method below. The `conda-pypi` channel does not currently
serve `conda-sigstore`.

## Install with pip

Create a dedicated environment that contains conda, pip, and the plugin:

```console
conda create --name conda-sigstore "python>=3.11" conda pip
conda activate conda-sigstore
python -m pip install "conda-sigstore==0.1.3"
conda sigstore --help
```

The PyPI distribution does not install conda. If you instead add the plugin to
an existing conda installation, run pip with that installation's Python
interpreter.

:::{warning}
The opt-in pre-extraction verifier requires the unreleased package-verifier API
in [conda/conda#16518](https://github.com/conda/conda/pull/16518). Released
conda versions can load the other plugin commands, but they cannot enable that
install hook.

Current conda `PackageRecord` objects also do not preserve CEP 50's
`attestations_sha256` field. A corresponding conda change is required before
real solver and install flows can select its content-addressed sidecar.
`plugins.conda_sigstore_enforce` remains false by default.
:::

## Preview install enforcement from source

Use the repository's locked test environment to evaluate the unreleased conda
integration without changing your normal conda installation. You need
[Pixi](https://pixi.sh) and Git.

```console
git clone https://github.com/jezdez/conda-sigstore.git
cd conda-sigstore
pixi install --locked --all
pixi shell -e test
conda init --install
conda sigstore --help
```

`conda init --install` is a one-time setup for the source environment. It
replaces the pip bootstrap entry point inside `.pixi/envs/test` with conda's
normal command wrappers. It does not initialize your shell profile.

The locked environment builds a pinned revision from `jezdez/conda`'s
`feature/package-verifiers` branch, the branch behind the unreleased hook pull
request, as a conda package.

Exit the preview shell when finished:

```console
exit
```

Read [Configure verification](configure-verification.md) before enabling
install enforcement.
