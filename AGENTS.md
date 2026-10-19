# AGENTS.md — conda-sigstore coding guidelines

## Project structure

- The package provides one `conda sigstore` subcommand and one opt-in
  pre-extraction package verifier through one conda plugin entry point. The
  verifier is disabled by default.

- Source lives under `src/conda_sigstore/`. Keep each module responsible for
  one concern:
  - `plugin.py` registers conda hooks and remains a startup-safe import boundary.
  - `cli/main.py` owns parser configuration and lazy command dispatch.
  - `cli/attest.py`, `cli/verify.py`, and `cli/audit.py` own their command
    handlers. `cli/output.py` owns shared Rich rendering, while
    `cli/__init__.py` is a thin re-export shim.
  - `settings.py` owns operational limits, optional Sigstore trust
    configuration, and the flat install-enforcement setting. It does not define
    publisher authorization.
  - `evidence.py` owns shared immutable evidence and result models.
  - `exceptions.py` owns publish-statement, provenance, transport, bundle
    verification, and trust-material errors.
  - `statements.py` owns generic in-toto parsing and strict CEP 27 publication
    statements.
  - `attestation.py` owns keyless signing and raw bundle output.
  - `transport.py` owns `SidecarTransport`, including bounded local,
    repodata-advertised immutable `.sigs.<sha256>`, and deterministic adjacent
    Prefix.dev sidecar loading.
  - `verification.py` owns Sigstore cryptographic verification followed by CEP
    27 and artifact-binding checks.
  - `install.py` owns the opt-in adapter for conda's pre-extraction
    package-verifier hook. It validates evidence and does not authorize signers.
  - `cache.py` owns content-addressed sidecars and artifact-digest references
    used only to rediscover adjacent evidence for fresh verification.
  - `audit.py` owns installed-environment and source-evidence audit orchestration.
  - `source_archive.py` owns bounded inspection of digest-checked package
    snapshots and copies only regular recipe and embedded-bundle files.
  - `source_attestations.py` owns draft recipe declarations, embedded paths,
    bundle verification, and publisher matching.
  - `provenance.py` owns factual parsing of separate provenance evidence.

- Tests live under `tests/` and mirror the source module or behavior under test.
  CLI tests live under `tests/cli/`, statement behavior belongs in
  `tests/test_statements.py`, transport behavior in `tests/test_transport.py`, and
  install-verifier behavior in `tests/test_install.py`. Hook startup behavior
  belongs in `tests/test_plugin.py`. Cross-cutting fixtures belong in
  `tests/conftest.py`.

- Live external-service checks belong in `tests/test_interop.py`, use the
  `live_interop` marker, require explicit environment-variable gates, and stay
  excluded from normal pull request tests.

- Performance checks belong in `tests/test_benchmarks.py`, use the `benchmark`
  marker, and stay excluded from normal tests. Keep cryptographic benchmarks
  hermetic and preserve machine-readable results without making noisy hosted
  runner timing a correctness threshold. Live install comparisons also use the
  `live_interop` marker and an explicit environment-variable gate.

## Imports and plugin startup

- Use relative imports for all intra-package references. Absolute
  `conda_sigstore.*` imports belong only in tests and installed entry-point
  checks.

- Use `from __future__ import annotations` in every Python module. Put imports
  used only for annotations under `TYPE_CHECKING` when doing so avoids runtime
  dependency loading.

- Inline imports are reserved for genuine plugin, dispatch, optional, or heavy
  boundaries:
  - conda hook implementations in `plugin.py`
  - the selected command path in `cli/main.py`
  - Sigstore, cryptography, and trust-root loading that is not needed for every
    conda invocation
  - conda APIs that are only needed for a selected command or audit path

- Everywhere else, imports belong at module top. Do not use local imports as a
  general circular-import workaround. Fix the ownership or module boundary.

- Importing the conda entry point must not load Sigstore trust material, perform
  network access, create cache directories, inspect package archives, or import
  Rich or command implementations eagerly. Ordinary conda commands must remain
  a cheap no-op for this plugin.

- Keep `plugin.py` declarative. Hook registration may import lightweight conda
  hook types, but trust-root loading, sidecar access, and verification stay
  behind the invoked command.

## Dependencies

- Minimize the dependency graph. Prefer the standard library, conda's public
  APIs, Sigstore's public APIs, or an already-required package before adding a
  dependency.

- Do not add a second HTTP, URL, cache, locking, configuration, or cryptography
  stack when conda or Sigstore already provides the required behavior.

- Declare minimum supported versions in `pyproject.toml`. Add an upper bound
  only for a documented compatibility boundary, such as the current Sigstore
  major-version constraint.

## Code structure

- Put cohesive behavior on the dataclass or adapter that owns its inputs and
  invariants. Examples include validation and serialization on evidence models,
  statement checks on CEP 27 models, cache operations on `DigestCache`, and
  trust-root behavior on `SigstoreVerifier`.

- Prefer a method such as `decision.allows_target_channel(value)` or
  `cache.load_sidecar(digest)` over a module helper that accepts the owning
  object's fields as loose arguments.

- Before adding a private module-level helper, check in this order:
  1. Does conda, Sigstore, or another existing dependency already expose the
     behavior?
  2. Does an existing dataclass or adapter own the data and invariant? Add a
     cohesive method there.
  3. Is the behavior genuinely generic and reused across modules? Make it a
     public function with a clear name, type annotations, and a useful
     docstring.
  4. Is it used once? Inline it at the call site.

- Do not add tiny private wrappers that merely forward arguments, rename one
  call, return one attribute, or hide a single expression. They add indirection
  without ownership or reuse.

- Do not use section-divider comments such as `# --- Helpers ---` or
  `# === Public API ===`. Use ordering and module boundaries. If a file needs
  section dividers, split it by concern or move behavior to the owning class.

- Comments explain security intent, non-obvious constraints, or trade-offs that
  the code cannot express. Do not narrate obvious operations. Keep docstrings
  concise and do not repeat types already present in annotations.

## Typing, linting, and formatting

- Type all production code with modern annotations such as `str | None`,
  `list[str]`, and `Mapping[str, object]`. Use `ClassVar` for class-level state.

- Use Ruff for linting and formatting and `ty` for type checking. Their
  configuration in `pyproject.toml` is authoritative.

- Do not silence type or lint failures broadly. Narrow any required suppression
  to the smallest expression and explain a non-obvious upstream limitation.

## Testing

- Write plain module-level pytest functions with behavior-focused names. Do not
  use `unittest.TestCase` or group tests in classes.

- Do not use `unittest.mock`, `Mock`, `MagicMock`, or `patch`. Use pytest
  fixtures such as `tmp_path`, `monkeypatch`, and `capsys`, small real fakes,
  or recording closures.

- Use `pytest.mark.parametrize` when multiple inputs exercise the same
  behavior. Check whether a new case fits an existing parameterized test before
  adding another function. Use readable IDs for non-obvious cases.

- Put repeated setup in fixtures. Fixtures that return recording closures or
  call logs are preferred when a test needs to observe calls.

- Security tests must cover the rejection path, not only successful
  verification. Include malformed containers, oversized input, digest and size
  mismatches, malformed signer evidence, target-channel replay, offline cache
  failures, and credential redaction where relevant.

- Keep normal tests hermetic. Network and workload-identity tests require the
  `live_interop` marker and explicit opt-in gates.

- After production or test changes, run the full normal test suite and static
  checks through the locked Pixi environments:

  ```console
  pixi run --locked -e dev check
  pixi run --locked -e test test
  ```

- Run `pixi run --locked -e docs docs` after documentation, public interface,
  or behavior changes.

## Conda integration

- Reuse conda's APIs and plugin contracts before writing custom equivalents.
  In particular, use conda's context for offline and plugin configuration,
  `get_session(url)` for authenticated channel requests, package-cache APIs for
  retained archives, URL helpers for credential removal, disk locking for
  shared cache writes, and `CondaError` for user-facing plugin failures.

- Route sidecar input through `SidecarTransport.load_input()`,
  `SidecarTransport.load_repodata()`, or `SidecarTransport.load_prefix()`.
  Do not add flat transport helpers around these methods. Preserve
  `TransportError.code` when converting transport failures at a conda command
  or verifier boundary.

- Do not reimplement channel parsing, path-token masking, environment prefix
  resolution, package record lookup, package-cache selection, or command
  lifecycle behavior that conda already owns.

- Register behavior only through the `[project.entry-points.conda]` entry point
  and supported pluggy hooks. Keep one `conda sigstore` subcommand, one
  structured `plugins.conda_sigstore` setting for operational inputs, and the
  flat boolean `plugins.conda_sigstore_enforce` setting for opt-in verification.

- Register the package-verifier hook directly and without an optional hook,
  pre-command compatibility guard, or transaction-hook substitute. Keep
  enforcement false by default. The locked developer environments use
  `jezdez/conda` branch `feature/package-verifiers` from conda/conda#16518.

- The accepted CEP 50 repodata transport requires conda to preserve
  `attestations_sha256` on the selected package record. Current conda
  `PackageRecord` and solver conversion paths do not preserve that field, so a
  conda change is required before real solver, install, or installed-audit
  flows can consume it. The selected package URL and conda-supplied artifact
  SHA-256 remain sufficient only for the separate adjacent Prefix.dev
  compatibility transport.

- Treat JSON as an output contract. Machine-readable output must contain one
  stable, unstyled JSON value on stdout and must not be mixed with human status
  lines or ANSI escapes.

- Treat signer identities, issuers, URLs, filenames, and failure messages as
  untrusted Rich input. Render them as `Text` or escape them before using
  markup.

- Describe install enforcement as evidence-validity enforcement only. Do not
  claim that a successful install check authorizes the bundle signer until a
  standard defines how channels delegate publisher identities.

## Security boundaries

- Treat cryptographic validity, statement validity, and authorization as
  separate concepts. A valid Sigstore signature authenticates the reported
  signer but does not authorize that signer for a channel.

- Do not invent consumer-maintained identity policy, infer authorization from
  certificate fields, or trust undocumented repository admission behavior.
  Report the certificate identity and issuer as evidence until a standard
  channel delegation mechanism exists.

- Accept a verification result only when a cryptographically valid CEP 27
  statement binds the exact artifact filename and SHA-256. When the statement
  contains `targetChannel`, validate it against the channel supplied for the
  verification operation.

- Verify Sigstore transparency-log inclusion and checkpoint material. Do not
  automatically disable those checks for converted PEP 740 or PyPI bundles
  without authenticated conversion provenance.

- In the CEP 50 `repodata` transport, fetch the immutable
  `.sigs.<attestations_sha256>` URL only when repodata provides a valid
  `attestations_sha256` field. Require exactly 64 lowercase hexadecimal
  characters before constructing the URL, enforce the configured streaming
  limit, and verify the advertised SHA-256 before parsing. Never probe for an
  undeclared sidecar. The mutable `.sigs` URL is for servers and generic
  tooling, not conda-client retrieval. Refer to the accepted standard as
  [CEP 50](https://github.com/conda/ceps/blob/main/cep-0050.md).

- The opt-in install verifier must require one cryptographically valid, exact
  artifact-bound CEP 27 statement. When repodata advertises
  `attestations_sha256`, fetch `.sigs.<attestations_sha256>`, enforce the
  streaming limit and advertised SHA-256, and never fall back after an error.
  Otherwise require the deterministic adjacent `.v0.sigs` sidecar. Missing,
  unavailable, malformed, invalid, or nonmatching evidence must fail the
  package. This does not authorize the signer.

- Keep Prefix.dev `.v0.sigs` audit support explicit through a direct bundle URL
  or the `--prefix-sidecars` flag. Strict install enforcement may require this
  deterministic adjacent sidecar when `attestations_sha256` is absent. A
  present but invalid `attestations_sha256` value is a hard failure, not a
  fallback trigger.

- Bound bytes before JSON, certificate, archive, or bundle parsing. Require a
  nonempty sidecar array of bundle objects and reject duplicate JSON keys where
  the format requires an unambiguous statement.

- One cryptographically valid, artifact-bound CEP 27 bundle is sufficient for a
  verified result. Preserve invalid, unsupported, and nonmatching siblings as
  evidence without allowing them to overturn valid evidence.

- Cache adjacent sidecars only after successful verification, bind their
  content digest to the artifact SHA-256, credential-free channel, and
  filename, and rehash and cryptographically reverify the bytes on every read.
  This cache is not a verification receipt.

- A local trust configuration that parses successfully is not proof of
  authenticated distribution, freshness, or rollback protection. Keep those
  operator responsibilities explicit in code comments, errors, and docs.

- Offline mode may use integrity-checked local sidecars and configured trust
  material. It must not silently make network requests.

- Redact credentials, channel tokens, URL queries, and local secrets from
  errors, logs, cache labels, and JSON output.

- Source and build evidence are separate audit evidence. Source auditing
  requires a verified package publication result and a retained package
  archive. Validate actual bundle certificates, recipe publisher claims,
  predicate types, source paths, and source digests. Never trust embedded
  `verified`, identity, or issuer claims and never promote source evidence into
  package authorization.

- Use atomic writes for cache and attestation state. Reject unsafe archive
  paths, symlink escapes, oversized embedded evidence, and files that change
  outside their verified digest binding.

- Changes that weaken any trust boundary require an explicit standards or
  compatibility justification, focused regression tests, and corresponding
  security-model documentation.

## Documentation

- Documentation uses Sphinx with MyST Markdown, `conda-sphinx-theme`, and
  `sphinx-design`. Generated `docs/_build/` output is not source.

- Follow Diataxis:
  - tutorials teach complete workflows
  - how-to guides solve specific operator tasks
  - reference pages state exact commands, configuration, formats, and contracts
  - explanation pages describe design, threat models, and trade-offs

- Keep standards status precise. CEP 27 publication statements and CEP 50
  repodata sidecar distribution are accepted standards. The source-attestation
  proposal in `conda/ceps#168` remains a draft. Standard acceptance does not
  provide conda's unreleased package-verifier hook or metadata propagation.
  CEP 50 does not define trusted identities, lockfile policy, or enforcement.
  Label Prefix.dev transport behavior as current service-specific compatibility
  and distinguish public client behavior from unknown server behavior.

- Update command, standards, security, migration, offline, and interoperability
  pages whenever their corresponding contract changes. Do not let examples
  promise configuration, authorization, flags, or enforcement that the
  implementation lacks.

- Keep prose direct. Avoid excessive bold or italic emphasis. Use MyST
  directives and Sphinx Design components consistently, with short tab and card
  labels.

- `CHANGELOG.md` is the canonical changelog. `docs/changelog.md` includes it
  rather than duplicating release notes. Add user-visible unreleased changes
  under `[Unreleased]`, never under an already released version.

## Lockfile maintenance

- After any change to Pixi metadata in `pyproject.toml`, including dependencies,
  features, environments, tasks, platforms, or workspace settings, run
  `pixi lock` and commit the updated `pixi.lock` with the metadata change.

- Do not hand-edit `pixi.lock`. Use `pixi lock --check` to verify that metadata
  and the lock file agree.

## Release safety

- Never create or push a tag, create or publish a GitHub release, or publish to
  PyPI without explicit user approval. Preparing a release means updating the
  changelog, validating metadata and workflows, and reporting the remaining
  release action.

- Preserve the tag-gated build-once release design. Distribution artifacts are
  built once, attested by GitHub, uploaded to a draft release, published to PyPI
  through trusted publishing, and only then exposed in the GitHub release.

- Do not replace immutable release assets or reuse a released tag. Create a new
  version and tag for corrections.

- Pin third-party GitHub Actions to full commit SHAs, use least-privilege job
  permissions, and keep credentials unavailable to jobs that do not need them.

## Pull requests and issues

- Use the repository's native title and body style. Never prefix a pull request
  title with `[codex]` or another tool label.

- Follow repository issue and pull request templates when present.

- Do not add validation steps, test commands, or verification output to pull
  request descriptions.

- Do not use semicolons in prose, including documentation, changelog entries,
  review comments, issue bodies, pull request bodies, and chat responses.

- GitHub renders GFM. Write each pull request or issue paragraph and each bullet
  on one physical line and let the browser wrap it. Reserve hard wrapping for
  code fences, tables, and CLI help.

- When using `gh pr create` or `gh issue create`, pass multiline bodies through
  a quoted heredoc and keep each paragraph or bullet on one line.

- Inspect the exact failing GitHub Actions job log before changing code. Do not
  confuse a downstream cleanup or upload failure with the root cause.
