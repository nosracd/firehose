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

# Breaking Changes

Below is a history of breaking changes between the listed version and the previous version.

## 2.0.0

This version includes breaking changes to the following ASPN messages, meaning that they have new
fingerprints:

- `measurement_direction_2d_to_points`
- `measurement_direction_3d_to_points`
- `measurement_image`
- `measurement_satnav_subframe`

This occurred because certain fields were changed from `int16_t` to `byte` in order to better
represent ASPN in LCM. Specifically, this change was made to fields which represented opaque data
streams (e.g. image data). This change has the benefit of reducing the size of these fields by half,
which is important since some of these messages can be very large (e.g. images).
