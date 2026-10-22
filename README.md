# Ansible Role: rv

Install [rv](https://github.com/spinel-coop/rv), the Rust-powered Ruby version
manager, and provision a pinned Ruby version on Linux (Ubuntu) and macOS.

## Requirements

- **Linux:** Ubuntu 22.04+ with glibc >= 2.35
- **macOS:** 14.0+
- **Architectures:** x86_64 / arm64
- `curl` available on the target (installed automatically on Ubuntu)

## Role Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `rv_user` | `{{ ansible_user_id }}` | Account that owns the installation, PATH updates, and Ruby toolchain. |
| `rv_ruby_version` | `3.4.11` | Ruby version to install and pin globally via `rv`. |
| `rv_version` | `v0.7.2` | rv release tag to install. |
| `rv_installer_url` | `https://github.com/spinel-coop/rv/releases/download/{{ rv_version }}/rv-installer.sh` | Override to use a private mirror or a different release. |
| `rv_installer_path` | `{{ rv_home_dir }}/.cache/rv-installer.sh` | Scratch path for the downloaded installer; removed after install. |
| `rv_supported_ruby_series` | `3.2`, `3.3`, `3.4`, `4.0` | Ruby series the role accepts. Anything else fails the pre-flight check. |
| `rv_system_packages` | `curl` | Packages installed with apt on Linux. |

## What the role does

- Validates architecture, Ruby series, OS version, and glibc (Ubuntu).
- Installs rv into `~/.local/bin` for the target user, with `RV_NO_MODIFY_PATH=1`
  so the installer does not edit shell rc files behind the role's back.
- Configures shell RC files (bash, zsh, fish, nu) with a PATH guard, `rv shell
  init`, and completions inside a single managed block.
- Removes stale `~/.cargo/bin` and `~/.rv/bin` PATH entries left by older installs.
- Installs and globally pins the requested Ruby version.

The role is idempotent: re-running it leaves the host unchanged.

## Example Playbook

```yaml
- hosts: all
  roles:
    - role: andymarthin.rv
      vars:
        rv_ruby_version: "3.4.11"
        rv_version: "v0.7.2"
        rv_user: deploy
```

## Testing locally

The role ships a Molecule scenario that runs against Ubuntu 24.04 in Docker and
asserts the install path, the managed rc block, the global pin, and that the
Ruby is actually managed by rv.

```bash
pip install molecule molecule-plugins[docker] ansible-lint
molecule test
ansible-lint
```

A minimal sanity check against localhost:

```bash
ansible-playbook -i "127.0.0.1," -c local playbook.yml
```

## Releasing

Releases are cut by pushing a `v*` tag. The `Release` workflow reads the
matching `## [x.y.z]` section from [CHANGELOG.md](CHANGELOG.md) and uses it as
the GitHub Release body.

```bash
# 1. Move the Unreleased entries into a new `## [x.y.z] - YYYY-MM-DD` section.
# 2. Commit, then tag and push.
git tag v0.2.0
git push origin v0.2.0
```

The workflow fails if the changelog has no section for the pushed tag, so the
tag and the changelog cannot drift apart.

## License

MIT
