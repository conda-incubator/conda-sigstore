# Audit an installed environment

`conda sigstore audit` verifies evidence available for packages already
installed in one conda prefix. It does not prove that evidence was checked
before installation.

## Select the environment

Audit conda's current target prefix:

```console
conda sigstore audit
```

Select an environment by name or path when needed:

```console
conda sigstore audit -n runtime
conda sigstore audit -p /srv/conda/envs/runtime
```

The original package archives must still be present in a conda package cache.
An installed prefix record contains a digest claim, not the original bytes.
Packages without a retained archive report `record-digest-only`.

## Audit repodata-advertised evidence

The default mode requires the installed package record to preserve the
`attestations_sha256` field defined by accepted
[CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md):

```console
conda sigstore audit -n runtime --json
```

The field must be exactly 64 lowercase hexadecimal characters and selects
`<artifact>.sigs.<attestations_sha256>`. The audit enforces the configured
streaming limit, verifies the exact sidecar digest, and only then parses the
bundle array. A record without the field reports `missing`. The default mode
does not probe either the mutable `.sigs` URL or an adjacent `.v0.sigs` file.

Current conda `PackageRecord` objects and solver conversion paths do not
preserve `attestations_sha256`. Real installed-environment audits need a conda
change before they can select the CEP 50 transport, even when a channel already
publishes the immutable sidecar.

## Audit Prefix.dev evidence

Select Prefix.dev's current adjacent convention explicitly:

```console
conda sigstore audit -n runtime --prefix-sidecars
```

This derives `<artifact>.v0.sigs` from each installed package URL. Reports mark
that transport with `prefix_sidecar: true` because current Prefix.dev repodata
does not bind the sidecar bytes.

## Include source evidence

Add `--sources` when retained package archives contain draft source-attestation
declarations:

```console
conda sigstore audit -n runtime --prefix-sidecars --sources --json
```

Source inspection runs only after the package has verified publication evidence
and a retained archive. See
[Source-attestation declarations](../reference/source-attestations.md) for the
recipe syntax, supported publisher forms, path rules, and result fields.

The auditor reads Rattler-Build 0.77.0 declarations in `recipe.source`, including
its serialized publisher mappings. Supported declarations produce a `missing`
source result because the builder does not retain the bundles needed for an
independent audit. Audits do not fetch the declared `bundle_url`. A verified
source result requires the experimental embedded-evidence format described in
the reference.

The auditor checks a temporary archive snapshot against the verified package
digest and reads only regular recipe and embedded-bundle files. It does not
perform general package extraction. Packages that exceed the
{ref}`source-audit-limits` produce an `invalid` or `evidence-unavailable` source
result, depending on the input limit.

Source and provenance evidence remain separate from package publication. They
do not authorize the package signer.

## Interpret the report

Human output shows one row per installed package. Use `--json` for automation.
Common statuses are:

| Status | Action |
| --- | --- |
| `verified` | Inspect the reported signer and predicates for the evidence you expected |
| `missing` | Confirm the selected transport and whether the channel publishes a sidecar |
| `retrieval-failed` | Check channel access, the streaming limit, and the advertised digest |
| `invalid` | Treat the sidecar or required statement as unusable |
| `untrusted-identity` | Check the independently supplied signer requirement |
| `record-digest-only` | Restore or redownload the exact package archive before auditing again |
| `evidence-unavailable` | Restore offline evidence or trust material before auditing again |

Audit exits with status 0 after producing a report even when package statuses
are not `verified`. Command setup and configuration errors still fail the conda
command. See [JSON output and exit status](../reference/json-output.md) for the
machine-readable contract.
