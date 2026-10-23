# Changelog

All notable changes to this role are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The release workflow publishes a GitHub Release using the section that matches
the pushed tag. Keep the `## [x.y.z]` headings in sync with the git tags.

## [Unreleased]

## [0.2.1] - 2026-10-24

### Fixed

- The `Molecule` CI job failed with `exit code 4` because the `community.docker`
  collection was never installed; `molecule test` could not load the docker
  driver. CI now installs `requirements.yml` before running the scenario.
- The `Lint` job now installs the same collections, so `ansible-lint` and the
  unit tests resolve modules against the collections Molecule actually uses
  instead of trusting whatever happens to be preinstalled on the runner.

## [0.2.0] - 2026-10-23

Update the role for rv 0.7.2. rv 0.2.0 no longer works: rv moved its install
directory, so the role's `creates` guard and `PATH` handling both pointed at a
binary that no longer existed.

### Changed

- Bump `rv_version` from `v0.2.0` to `v0.7.2`.
- Bump `rv_ruby_version` from `3.4.2` to `3.4.11`.
- Install and reference rv from `~/.local/bin` instead of `~/.cargo/bin`, matching
  [rv #797](https://github.com/spinel-coop/rv/pull/797).
- Source the PATH guard in `.bashrc`/`.zshrc`/`config.fish` against `~/.local/bin`
  instead of the removed `~/.cargo/env`.
- Replace the Ruby version compliance check with an allowlist driven by the new
  `rv_supported_ruby_series` variable (`3.2`, `3.3`, `3.4`, `4.0`).

### Added

- `rv_supported_ruby_series` variable listing the Ruby series the role accepts.
- `rv_installer_path` variable for the downloaded installer scratch file.
- `CHANGELOG.md`.
- Molecule test scenario running against Ubuntu 24.04, asserting the install
  path, managed rc block, global pin, and that Ruby is managed by rv.
- GitHub Actions `CI` workflow running `ansible-lint` and `molecule test`.
- GitHub Actions `Release` workflow that creates a release from a pushed `v*`
  tag, using the matching changelog section as the release body.

### Fixed

- `rv_home_dir` and the detected shell were read from the wrong `getent` fields.
  Ansible strips the username, so home is index `4` and shell is index `5`; the
  role read `5` and `6`. This set the home directory to the shell path (for
  example `/bin/bash`) on any host where `getent` returned the user.
- The rv install task is idempotent again; its `creates` guard points at the real
  binary path.
- Bumping `rv_version` now upgrades an existing install. The role compares
  `rv --version` against the requested release instead of only checking that the
  binary exists.
- Ruby install detection uses `rv ruby list --installed-only --format json` and only
  counts rv-managed Rubies. The previous `grep` matched `[available]` rows, so a
  Ruby that was listed upstream but not installed was treated as present.
- Pin detection no longer relies on the `*` marker being at the start of the line.
  rv 0.7.x renders `rv ruby list` as a table, so the old `^\*` pattern never matched
  and `rv ruby pin` ran on every play. The pin is now compared against the contents
  of `~/.ruby-version`.
- `rv ruby pin` runs with `chdir` set to the user's home, so it writes a global pin
  rather than a project-scoped one.
- Set `RV_NO_MODIFY_PATH=1` when running the installer so it does not edit
  `.profile`, `.bashrc`, `.bash_profile`, `.bash_login`, `.zshrc`, `.zshenv`, or
  `fish/conf.d` in addition to the role-managed block.
- Remove the stale `~/.cargo/bin` PATH export left behind by older role versions.
- Replace the `ldd`-based glibc probe with `getconf GNU_LIBC_VERSION`, which is
  locale-independent.
- Nushell integration is now rendered with `rv shell init`/`rv shell completions`
  and installed with `copy`, making it idempotent instead of always reporting
  `changed`.
- Use fully qualified module names and add explicit file modes throughout.
- Add `role_name` and `namespace` to `meta/main.yml`; `ansible-lint` could not
  resolve the role name from the `ansible-role-rv` directory. Raise
  `min_ansible_version` to `2.14`.

## [0.1.0] - 2025-10-08

### Added

- Initial release: install rv, wire up bash/zsh/fish/nushell integration, and
  install and pin a Ruby version on Ubuntu and macOS.

[Unreleased]: https://github.com/andymarthin/ansible-role-rv/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/andymarthin/ansible-role-rv/compare/v0.1.0...v0.2.1
[0.2.0]: https://github.com/andymarthin/ansible-role-rv/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/andymarthin/ansible-role-rv/releases/tag/v0.1.0
