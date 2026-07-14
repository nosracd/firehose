# ASPN-LCM

This Python module contains the Python variant of ASPN-LCM.

# Release Versioning

This project implements a versioning scheme similar to semantic versioning
[SemVer](https://semver.org/), but much lighter. **This project does not define an API and therefore
has no concrete definition of what constitutes a breaking change.**

Nonetheless, if a new release would require significant changes downstream we will attempt to
communicate that by incrementing the major version. If there are new features or newly deprecated
features, we will attempt to communicate that by incrementing the minor version. If the changes are
primarily bug fixes, we will attempt to communicate that by incrementing the patch version.

However, we make no concrete promises about whether or not a given release will be compatible with
your project downstream. You may experience breaking changes on minor or patch releases. If this is
an issue for your project, we recommend you pin to a specific version of this project rather than a
range.

## Fingerprints

Each message defined by this project has a unique fingerprint, a hash calculated from all of the
fields of the message, recursively. If any fingerprints change this indicates a hard
incompatibility with previous versions of this project. In this case, we will increment the major
version if any fingerprint changes. Additionally, we maintain a table of fingerprint changes so you
can know which messages' compatibility changed.
