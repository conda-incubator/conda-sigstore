# Security policy

## Supported versions

Before the first stable release, only the latest published version receives
security fixes. After 1.0, this table will list the supported release lines.

| Version | Supported |
| --- | --- |
| Latest release | Yes |
| Older releases | No |

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use a
[private GitHub security advisory](https://github.com/conda-incubator/conda-sigstore/security/advisories/new)
and include the affected version, trust configuration, artifact and sidecar
shape, expected behavior, observed behavior, and a minimal reproducer when it is
safe to share.

Treat bypasses of artifact or sidecar binding, target-channel checks, signer
reporting, offline trust-root validation, input bounds, and cache invalidation
as security-sensitive. Reports about a malicious package should also go to the
operator of the affected channel.

We will acknowledge a report as soon as practical, coordinate a fix and release
with the reporter, and credit the reporter unless they request otherwise.
