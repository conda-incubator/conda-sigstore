# Verify a conda-sigstore publication

The conda publishing workflow signs a CEP 27 publication statement for the exact
package uploaded to `https://conda.anaconda.org/jezdez`. It verifies the bundle
before upload and retains it in GitHub, alongside separate SLSA build
provenance.

The existing 0.1.2 conda package has SLSA provenance only and cannot pass the
CEP 27 publication check below. Use a package published after CEP 27 signing
was added to the workflow.

## Download the package and bundle

Install [conda-sigstore](install.md), [GitHub CLI](https://cli.github.com/),
and `curl`. Authenticate GitHub CLI with `gh auth login` if needed. The commands
below use a POSIX shell.

Choose the exact package filename from the
[`jezdez` channel's files](https://anaconda.org/jezdez/conda-sigstore/files) and
find the corresponding successful publication run in the
[repository's workflows](https://github.com/conda-incubator/conda-sigstore/actions).
Replace `VERSION`, `BUILD`, and `PUBLISH_RUN_ID` below. If the release workflow
called the conda publishing workflow, use that release run.

```console
package='conda-sigstore-VERSION-BUILD.conda'
run_id='PUBLISH_RUN_ID'

curl --fail --location --output "$package" \
  "https://conda.anaconda.org/jezdez/noarch/$package"
gh run download "$run_id" --repo conda-incubator/conda-sigstore \
  --name conda-publication-attestation --dir evidence
```

The workflow artifact contains one raw Sigstore bundle named
`$package.sigstore.json`. GitHub Actions artifacts expire according to the
repository's retention settings. If it is no longer available, use the
attestation download method below.

## Verify the publication

```console
conda sigstore verify "$package" \
  --bundle "evidence/$package.sigstore.json" \
  --channel https://conda.anaconda.org/jezdez
```

Verification checks the Sigstore evidence, exact package filename and SHA-256,
CEP 27 statement, and target channel. The result reports the authenticated
certificate identity and OIDC issuer. It does not establish channel permission
or package safety. SLSA provenance describes the build and does not substitute
for the CEP 27 statement.

To require a particular signer, obtain the expected workflow path and Git ref
from trusted release metadata, then set `EXPECTED_CERTIFICATE_IDENTITY` to
`https://github.com/conda-incubator/conda-sigstore/.github/workflows/WORKFLOW_FILE@GIT_REF`
for a publication made after the repository transfer. Earlier publications,
including the original 0.1.3 package, retain
`https://github.com/jezdez/conda-sigstore/.github/workflows/WORKFLOW_FILE@GIT_REF`.
The transfer does not rewrite existing certificates. Select the exact identity
for the publication being checked from trusted release metadata, and do not
derive it solely from the bundle. Supply both signer options together:

```console
conda sigstore verify "$package" \
  --bundle "evidence/$package.sigstore.json" \
  --channel https://conda.anaconda.org/jezdez \
  --cert-identity "$EXPECTED_CERTIFICATE_IDENTITY" \
  --cert-oidc-issuer https://token.actions.githubusercontent.com
```

## Retrieve the bundle from GitHub's attestation store

The workflow also records the publication bundle in GitHub's attestation store.
For publications made after the transfer, retrieve it by the downloaded
package's digest, filtering for the CEP 27 predicate:

```console
gh attestation download "$package" --repo conda-incubator/conda-sigstore \
  --predicate-type https://schemas.conda.org/attestations-publish-1.schema.json
```

For a publication made before the transfer, replace
`--repo conda-incubator/conda-sigstore` with `--owner jezdez`. Historical bundles
remain available through the original owner. The repository lookup does not
retrieve them after the transfer.

[GitHub CLI](https://cli.github.com/manual/gh_attestation_download) writes raw
bundles as JSON Lines to `sha256:DIGEST.jsonl` on Linux and macOS or
`sha256-DIGEST.jsonl` on Windows. Use the filename printed by the command.
With `jq` installed, convert those lines into the bundle array accepted by
`conda sigstore verify`:

```console
jq -s . 'sha256:DIGEST.jsonl' > publication-bundles.json
conda sigstore verify "$package" --bundle publication-bundles.json \
  --channel https://conda.anaconda.org/jezdez
```

You can add the paired signer options here too. A missing CEP 27 bundle is a
verification failure, even if SLSA evidence is available.

These commands retrieve evidence from GitHub and do not require attestation
sidecars on Anaconda.org. Installing the package does not automatically run
this check. See
[Install verification](../explanation/install-verification.md) for the separate
opt-in installation behavior and its transport requirements.
