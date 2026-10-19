# Rattler-Build rendered source fixture

`rendered_recipe.yaml` captures the output of Rattler-Build 0.77.0 in the repository's locked release environment:

```console
pixi run --locked -e release rattler-build build \
  --experimental --render-only \
  --recipe tests/fixtures/rattler-build-source/recipe.yaml
```

The fixture contains the sole object from the command's JSON array, kept in JSON syntax, which is also valid YAML. Rattler-Build writes this output object to `info/recipe/rendered_recipe.yaml` when including a recipe in a package. See [the 0.77.0 package writer](https://github.com/prefix-dev/rattler-build/blob/v0.77.0/crates/rattler_build_core/src/packaging.rs#L424-L438) and [the serialized output fields](https://github.com/prefix-dev/rattler-build/blob/v0.77.0/crates/rattler_build_core/src/types/build_output.rs#L29-L44).

The fixture preserves the rendered `recipe.source`, `attestation.bundle_url`, and publisher mapping with `provider`, `owner`, `repo`, and `ref_constraint: null`. It includes the builder's empty mappings, null finalized fields, build settings, and recorded tool version.

The fixture uses fixed placeholders for build metadata from the capture machine:

- Both `build_configuration.host_platform` and `build_configuration.build_platform` use `linux-64` with `__unix=0=0`, `__linux=0=0`, and `__archspec=1=x86_64` virtual packages.
- Each `build_configuration.directories` value is `/fixture/build/<field-name>`.
- `build_configuration.timestamp` is `2026-01-01T00:00:00Z`.
- `build_configuration.channels` contains only `https://conda.anaconda.org/conda-forge/`.

These placeholders do not describe the capture machine or an actual build. Other field values are unchanged. The source and bundle URLs use the reserved `example.invalid` domain, and the source digest is a placeholder supplied by the input recipe.

The command only rendered the recipe. It did not download a source or build a package, and it neither verified nor exported a source attestation. The captured output has no `attestation.verified` field and provides no evidence of successful bundle retention.
