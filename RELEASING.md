# Releasing

Releases are built from bare version tags by the `Release` GitHub Actions
workflow. The workflow builds the wheel and source distribution once, checks
their metadata, records GitHub build provenance, and attaches those files to a
draft GitHub release. It publishes the same files to PyPI through Trusted
Publishing and makes the GitHub release public only after PyPI succeeds.

## Repository configuration

The PyPI Trusted Publisher uses these values:

- Owner: `conda-incubator`
- Repository: `conda-sigstore`
- Workflow: `release.yml`
- Environment: `pypi`

The repository Actions secret `ANACONDA_API_KEY` must allow uploads to the
personal `jezdez` channel. The conda publishing job receives it only for the
upload step.

The GitHub Actions environment `pypi` permits deployments only from version
tags and requires maintainer approval. Immutable releases are enabled, so a
published release tag and its assets cannot be changed.

## Prepare 0.1.5

1. Update `CHANGELOG.md`, `CITATION.cff`, and installation documentation with
   the version and release date.
2. Merge the release preparation into `main`.
3. Update the local branch and record the exact commit:

   ```console
   git switch main
   git pull --ff-only
   git rev-parse HEAD
   ```

4. Confirm the required hosted checks passed for that commit.

Preparation ends after those checks. Publishing requires explicit maintainer
approval, followed by the tag below.

## Publish 0.1.5

Create and push an annotated bare version tag:

```console
git tag -a 0.1.5 -m "conda-sigstore 0.1.5"
git push origin 0.1.5
```

The tag starts this sequence:

1. build the wheel and source distribution once and record the source SHA-256
2. check the distribution metadata
3. record GitHub build provenance
4. create a draft GitHub release and attach the distributions
5. wait for approval of the `pypi` environment
6. publish the distributions to PyPI through Trusted Publishing
7. make the GitHub release public
8. pass the version and source SHA-256 to the conda workflow, which downloads
   the source distribution from PyPI and checks its digest
9. build, test, attest, and publish the conda package to `jezdez` on Anaconda.org

## Verify the release

Download both formats from GitHub and PyPI, compare their bytes, then verify
GitHub's build provenance and PyPI's publish attestations:

```console
set -euo pipefail
release_check="$(mktemp -d)"
gh release download 0.1.5 --repo conda-incubator/conda-sigstore \
  --dir "$release_check/github"
mkdir "$release_check/pypi"
curl --fail --location --silent --show-error \
  https://pypi.org/pypi/conda-sigstore/0.1.5/json \
  --output "$release_check/pypi.json"
wheel_url="$(jq -er \
  '.urls[] | select(.filename == "conda_sigstore-0.1.5-py3-none-any.whl") | .url' \
  "$release_check/pypi.json")"
sdist_url="$(jq -er \
  '.urls[] | select(.filename == "conda_sigstore-0.1.5.tar.gz") | .url' \
  "$release_check/pypi.json")"
if [[ "$wheel_url" != https://files.pythonhosted.org/* ]]; then
  echo "Unexpected PyPI wheel URL." >&2
  exit 1
fi
if [[ "$sdist_url" != https://files.pythonhosted.org/* ]]; then
  echo "Unexpected PyPI source archive URL." >&2
  exit 1
fi
curl --fail --location --silent --show-error "$wheel_url" \
  --output "$release_check/pypi/conda_sigstore-0.1.5-py3-none-any.whl"
curl --fail --location --silent --show-error "$sdist_url" \
  --output "$release_check/pypi/conda_sigstore-0.1.5.tar.gz"
cmp "$release_check/github/conda_sigstore-0.1.5-py3-none-any.whl" \
  "$release_check/pypi/conda_sigstore-0.1.5-py3-none-any.whl"
cmp "$release_check/github/conda_sigstore-0.1.5.tar.gz" \
  "$release_check/pypi/conda_sigstore-0.1.5.tar.gz"
for release_artifact in "$release_check"/github/*
do
  gh attestation verify "$release_artifact" \
    --repo conda-incubator/conda-sigstore \
    --cert-identity https://github.com/conda-incubator/conda-sigstore/.github/workflows/release.yml@refs/tags/0.1.5
done
pipx run --spec "pypi-attestations==0.0.30" pypi-attestations verify pypi \
  --repository https://github.com/conda-incubator/conda-sigstore \
  "$wheel_url"
pipx run --spec "pypi-attestations==0.0.30" pypi-attestations verify pypi \
  --repository https://github.com/conda-incubator/conda-sigstore \
  "$sdist_url"
```

Install the published wheel in a clean conda 26.7.1 environment and check
plugin discovery:

```console
release_prefix="$(mktemp -d)"
conda create --yes --prefix "$release_prefix" "conda=26.7.1" pip
conda run --prefix "$release_prefix" python -m pip install --no-cache-dir \
  "$release_check/pypi/conda_sigstore-0.1.5-py3-none-any.whl"
conda run --prefix "$release_prefix" python -m conda sigstore --help
```

The normal commands work with released conda. Pre-extraction verification
requires the draft conda branch used by the locked test suite.

If `Publish to PyPI` fails, inspect the live PyPI files before rerunning
anything. Rerun the failed jobs only when neither distribution was published.
If PyPI contains only one distribution, a missing attestation, an unexpected
filename, or different bytes, leave the draft release private and prepare a
new version. If both exact distributions and their attestations reached PyPI,
compare them with the draft assets using the commands above, then publish the
verified draft with `gh release edit 0.1.5 --repo conda-incubator/conda-sigstore --draft=false`
instead of rerunning the upload.

If `Publish GitHub Release` alone fails after the PyPI job succeeds, rerun only
that job.

Never move a release tag or replace files for a published version. Prepare a
new version and tag when an artifact must change after publication.

### Historical 0.1.3 verification

The 0.1.3 attestations retain the original `jezdez/conda-sigstore` identity.
Use that repository for PyPI verification. GitHub repository lookups do not
retrieve its bundles after the transfer, so download through the original
owner and verify locally:

```console
gh attestation download ARTIFACT --owner jezdez
gh attestation verify ARTIFACT --bundle BUNDLE.jsonl \
  --repo jezdez/conda-sigstore \
  --cert-identity https://github.com/jezdez/conda-sigstore/.github/workflows/release.yml@refs/tags/0.1.3
```

Replace `ARTIFACT` with the downloaded wheel or source archive and
`BUNDLE.jsonl` with the filename printed by the download command.

## Publish to the personal conda channel

The `Conda package` workflow builds a noarch Python package from the published PyPI
source archive. The release workflow passes the version and SHA-256 of the
source distribution it built. Rattler-Build checks that the downloaded archive
matches this digest before building the conda package. Reset the build number
to zero for a new version, or increment it when correcting the packaging of an
existing version.

The release workflow calls it after the GitHub release is public. To publish
an existing release, dispatch it with that release's version and verified
source SHA-256:

```console
gh workflow run conda.yml --ref main -f version=0.1.5 \
  -f source-sha256="$SOURCE_SHA256" -f publish=true
```

Set `SOURCE_SHA256` from the source distribution checked in
[Verify the release](#verify-the-release). Without a `source-sha256` override,
the workflow builds the recipe's pinned source, currently 0.1.5. Publication
then requires a requested version matching that pin. Update both recipe pins
after a release to make it the default for local and CI builds.

Pull requests, main-branch pushes, and manual runs with `publish=false` only
build and test the package. Publication checks that the built package matches
the requested version and creates separate SLSA build provenance and a CEP 27
publication attestation. Before upload, it verifies the CEP 27 bundle against
the exact filename, SHA-256, target channel, and expected workflow certificate
identity and OIDC issuer. It uploads the same package to Anaconda.org and keeps
the bundle in GitHub's attestation store and as a workflow artifact.

Build and test the recipe's pinned package with Rattler-Build:

```console
pixi run --locked -e release build-conda
```

The recipe checks imports on Python 3.11 and 3.14, Python dependency metadata,
and command discovery with released conda. These checks do not enable the
unreleased package-verifier integration. The recipe excludes pip's local
source URL, and `--no-include-recipe` omits rendered build-directory metadata
from the published archive. Keep the source recipe in Git.

For a manual 0.1.5 upload, first update the recipe pins and rebuild the
package. After explicit maintainer approval, upload the tested package using
an Anaconda API key supplied through `ANACONDA_API_KEY` or Rattler's credential
store. This command does not create or verify an attestation. Use the workflow
above to publish with CEP 27 evidence.

```console
pixi run --locked -e release rattler-build upload anaconda --owner jezdez --channel main \
  dist/conda/noarch/conda-sigstore-0.1.5-*.conda
```

Do not use `--force` to replace a published package. Confirm the uploaded
filename and SHA-256 in the channel's repodata, then install it in a fresh
environment:

```console
conda create --name conda-sigstore-check --override-channels \
  --channel jezdez --channel conda-forge "conda-sigstore=0.1.5"
conda run --name conda-sigstore-check conda sigstore --help
```

Follow [Verify a conda-sigstore publication](docs/how-to/verify-project-package.md)
to retrieve and check the CEP 27 bundle for the downloaded package. Require
the expected workflow identity and GitHub OIDC issuer from the release
metadata. This confirms the package and signer evidence without establishing
channel authorization. Anaconda.org sidecars are not required for this check,
and installing the package does not run it automatically.
