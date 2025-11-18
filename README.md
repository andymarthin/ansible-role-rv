# Ansible Role: rv

Install [rv](https://github.com/spinel-coop/rv), the Rust-powered Ruby version manager, and provision a pinned Ruby version on Linux (Ubuntu) and macOS.

## Requirements

- **Linux:** Ubuntu 22.04+ with glibc >= 2.35
- **macOS:** 14.0+
- **Architectures:** x86_64 / arm64
- `curl` available on the target (installed automatically on Ubuntu)

## Role Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `rv_user` | `{{ ansible_user_id }}` | Account that owns the installation, PATH updates, and Ruby toolchain. |
| `rv_ruby_version` | `3.4.2` | Ruby version to install and pin globally via `rv`. |
| `rv_version` | `v0.2.0` | rv release tag to install. |
| `rv_installer_url` | `https://github.com/spinel-coop/rv/releases/download/{{ rv_version }}/rv-installer.sh` | Override to use a private mirror or a different release. |

## What the role does

- Validates architecture, OS version, and glibc (Ubuntu).
- Installs rv for the target user and configures shell RC files (bash, zsh, fish, nu) with init and completions.
- Installs and pins the requested Ruby version.

## Example Playbook

```yaml
- hosts: all
  roles:
    - role: andymarthin.rv
      vars:
        rv_ruby_version: "3.4.2"
        rv_version: "v0.2.0"
        rv_user: deploy
```

## Testing locally

Minimal sanity check:

```bash
ansible-playbook -i "127.0.0.1," -c local playbook.yml
```
