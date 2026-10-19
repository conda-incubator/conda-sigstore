# Verify a conda-sigstore publication

The conda publishing workflow signs a CEP 27 publication statement for the exact
package uploaded to `https://conda.anaconda.org/jezdez`. It verifies the bundle
before upload and retains it in GitHub, alongside separate SLSA build
provenance.

This applies to publications made with the updated workflow. The existing
0.1.2 conda package has SLSA provenance only and cannot pass the CEP 27
publication check below.

## Download the package and bundle

Install [conda-sigstore](install.md), [GitHub CLI](https://cli.github.com/),
and `curl`. Authenticate GitHub CLI with `gh auth login` if needed. The commands
below use a POSIX shell.

Choose the exact package filename from the
[`jezdez` channel's files](https://anaconda.org/jezdez/conda-sigstore/files) and
find the corresponding successful publication run in the
[repository's workflows](https://github.com/jezdez/conda-sigstore/actions).
Replace `VERSION`, `BUILD`, and `PUBLISH_RUN_ID` below. Use the release workflow
run when it called the conda publishing workflow.

```console
package='conda-sigstore-VERSION-BUILD.conda'
run_id='PUBLISH_RUN_ID'

curl --fail --location --output "$package" \
  "https://conda.anaconda.org/jezdez/noarch/$package"
gh run download "$run_id" --repo jezdez/conda-sigstore \
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

A verified result checks the Sigstore evidence, exact package filename and
SHA-256, CEP 27 statement, and target channel. It reports the authenticated
certificate identity and OIDC issuer. It does not establish channel permission
or package safety. SLSA provenance describes the build and does not substitute
for the CEP 27 statement.

To require a particular signer, obtain the expected workflow path and Git ref
from trusted release metadata, then set `EXPECTED_CERTIFICATE_IDENTITY` to
`https://github.com/jezdez/conda-sigstore/.github/workflows/WORKFLOW_FILE@GIT_REF`.
Do not derive the expected identity solely from the bundle being checked.
Supply both signer options together:

```console
conda sigstore verify "$package" \
  --bundle "evidence/$package.sigstore.json" \
  --channel https://conda.anaconda.org/jezdez \
  --cert-identity "$EXPECTED_CERTIFICATE_IDENTITY" \
  --cert-oidc-issuer https://token.actions.githubusercontent.com
```

## Retrieve the bundle from GitHub's attestation store

The workflow also records the publication bundle in GitHub's attestation store.
Retrieve it by the downloaded package's digest, filtering for the CEP 27
predicate:

```console
gh attestation download "$package" --repo jezdez/conda-sigstore \
  --predicate-type https://schemas.conda.org/attestations-publish-1.schema.json
```

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

These commands retrieve evidence explicitly from GitHub. They do not require
or assume that Anaconda.org serves attestation sidecars. Installing the package
does not automatically perform this check. See
[Install verification](../explanation/install-verification.md) for the separate
opt-in installation behavior and its transport requirements.
