# Rattler-Build rendered source fixture

`rendered_recipe.yaml` contains an output captured from Rattler-Build 0.77.0 with the repository's locked release environment:

```console
pixi run --locked -e release rattler-build build \
  --experimental --render-only \
  --recipe tests/fixtures/rattler-build-source/recipe.yaml
```

The command returns a JSON array. The fixture retains its sole output object in JSON syntax, which is also valid YAML. Rattler-Build writes this output object to `info/recipe/rendered_recipe.yaml` when including a recipe in a package. See [the 0.77.0 package writer](https://github.com/prefix-dev/rattler-build/blob/v0.77.0/crates/rattler_build_core/src/packaging.rs#L424-L438) and [the serialized output fields](https://github.com/prefix-dev/rattler-build/blob/v0.77.0/crates/rattler_build_core/src/types/build_output.rs#L29-L44).

The capture preserves `recipe.source`, `attestation.bundle_url`, and the serialized publisher mapping with `provider`, `owner`, `repo`, and `ref_constraint: null`. It also preserves empty mappings, null finalized fields, build settings, and the recorded tool version. These fields distinguish native rendered output from a hand-written source declaration.

Machine-specific build metadata was replaced with deterministic placeholders:

- Both `build_configuration.host_platform` and `build_configuration.build_platform` use `linux-64` with `__unix=0=0`, `__linux=0=0`, and `__archspec=1=x86_64` virtual packages.
- Each `build_configuration.directories` value is `/fixture/build/<field-name>`.
- `build_configuration.timestamp` is `2026-01-01T00:00:00Z`.
- `build_configuration.channels` contains only `https://conda.anaconda.org/conda-forge/`.

These placeholders do not describe the capture machine or an actual build. Other field values are unchanged. The source and bundle URLs use the reserved `example.invalid` domain, and the source digest is a placeholder supplied by the input recipe.

This is a render-only fixture. No source was downloaded, no package was built, and no source attestation was verified or exported. In particular, the missing `attestation.verified` field reflects the captured output, not successful evidence retention.
