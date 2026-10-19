# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A noarch conda recipe and workflow that builds, tests, attests, and publishes
  released source archives to the personal `jezdez` channel on Anaconda.org.

- CEP 27 publication bundles for the project's conda packages, verified before
  upload and retained through GitHub workflow artifacts and attestations.
  Added a guide for retrieving and verifying this evidence.

- Offline interoperability tests with a captured Rattler-Build publication and
  the released `py-rattler` verifier, plus Python-to-Rust verification in the
  existing opt-in Sigstore staging check.

### Changed

- Updated CI to Pixi 0.82.0 and conda package builds to Rattler-Build 0.77.0.

## [0.1.2] - 2026-09-10

### Fixed

- Inspect source-audit evidence through bounded reads of regular recipe and
  bundle files from a digest-checked archive snapshot, without general package
  extraction. Select the exact `.conda` info component using the original
  package filename.
- Reject unsafe archive paths, links or special files at evidence paths,
  duplicate evidence files, malformed package streams, and archive expansion
  beyond source-audit limits.
- Bound rendered YAML parsing and source-attestation declaration counts before
  constructing requirements.

## [0.1.1] - 2026-09-09

### Changed

- Updated the draft repodata transport documentation for the ordering and
  concurrent publication requirements in conda/ceps#142. Clarified that bundle
  positions identify evidence without affecting verification or signer matching.
- Updated the locked conda development package to
  `b5dab4a46a650c6f0f82b2486993ee6891415deb` from conda/conda#16518.

## [0.1.0] - 2026-08-31

### Added

- `conda sigstore attest`, `verify`, and `audit` commands backed by
  sigstore-python.
- Strict CEP 27 statement construction and validation for conda package
  publication attestations.
- Support for the current draft repodata transport proposed in
  <https://github.com/conda/ceps/pull/142>: a strict `attestations_sha256`
  package-record field and immutable `.sigs.<sha256>` retrieval. Prefix.dev
  `.v0.sigs` discovery remains a separate compatibility transport.
- Offline verification and installed-environment, SLSA provenance, and recipe
  source-evidence auditing.
- Scheduled live interoperability checks for the fixed Prefix.dev example and
  Sigstore staging.
- Hermetic cold and warm verification, retained-package hashing, and extraction
  benchmarks with a separate workflow that preserves results without imposing
  hosted-runner timing thresholds.
- A scheduled informational benchmark alternating cached Prefix.dev installs
  with strict verification disabled and enabled.
- Sphinx documentation using MyST, `conda-sphinx-theme`, `sphinx-design`, and a
  Diátaxis structure.
- Installation, locked-environment verification, environment-audit, standard
  sigstore-python verification, and Prefix.dev publishing guides.
- Optional exact signer identity and OIDC issuer verification for
  `conda sigstore verify`.
- Versioned JSON output with artifact and observed sidecar SHA-256 digests, plus
  an exact output and exit-status reference.
- A direct, opt-in pre-extraction verifier for the package-verifier API in
  <https://github.com/conda/conda/pull/16518>, controlled by
  `plugins.conda_sigstore_enforce` and disabled by default. It accepts a
  repodata-hash-pinned `.sigs.<sha256>` sidecar when advertised and otherwise
  requires the deterministic adjacent `.v0.sigs` sidecar.
- Rich terminal rendering for human-readable command output.
- A tag-driven release workflow that builds once, records GitHub provenance,
  stages an immutable GitHub release, and publishes the same distributions to
  PyPI with Trusted Publishing and attestations.
- A generic in-toto library API for signing a parsed statement and returning
  its authenticated signer and timestamp evidence after verification.

### Changed

- Use the released conda-spawn 0.2.0 package from conda-forge in the locked
  test environments instead of building a pinned Git revision.
- Resolve the locked Sigstore runtime dependencies, conda-package-handling,
  conda-lockfiles, and conda-workspaces from conda-forge instead of PyPI. Keep
  the package-verifier Git revision as a source-built conda dependency, and
  keep conda-sigstore as an editable path dependency.
- Test every supported Python version on Windows ARM64 hosts using the locked
  win-64 environments through Prism while native win-arm64 dependencies remain
  unavailable on conda-forge.
- Raised the minimum supported Python version from 3.10 to 3.11 to match the
  sigstore-python 4.5 dependency set available on conda-forge.
- Replaced the superseded nested `attestations` mapping, advertised-size
  checks, and mutable `.sigs` client retrieval with the current
  `attestations_sha256` and immutable endpoint defined by conda/ceps#142 at
  commit `bcfcf42990fb4e5446f33424353ba0b7c0e869f0`.
- Reorganized the documentation around runnable beginner workflows and exact
  operator and machine-readable reference contracts.
- Made conda's standard `--console json` option select the same unstyled JSON
  result output as `--json` for verification and audit commands.
- Removed the permanently unavailable `source` field from SLSA evidence output.
- Expanded the live Prefix interoperability check into a real strict
  pre-extraction installation followed by an environment audit.

[Unreleased]: https://github.com/jezdez/conda-sigstore/compare/0.1.2...HEAD
[0.1.2]: https://github.com/jezdez/conda-sigstore/compare/0.1.1...0.1.2
[0.1.1]: https://github.com/jezdez/conda-sigstore/compare/0.1.0...0.1.1
[0.1.0]: https://github.com/jezdez/conda-sigstore/releases/tag/0.1.0
