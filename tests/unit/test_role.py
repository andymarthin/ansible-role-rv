"""Isolated tests of the role's actual Ansible expressions and shell block.

Uses ansible-core (already installed by CI), with no Docker or rv downloads.
Run from the repository root: python -m unittest discover -s tests/unit -v
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from ansible.parsing.dataloader import DataLoader
from ansible.plugins.loader import init_plugin_loader
from ansible.template import Templar, trust_as_template


def _trust(value):
    """Tag role strings as trusted templates (ansible-core >= 2.19).

    Since 2.19, ``Templar.template`` returns a plain string verbatim instead of
    rendering it, so expressions loaded from the role must be tagged first.
    """
    if isinstance(value, str):
        return trust_as_template(value)
    if isinstance(value, list):
        return [_trust(v) for v in value]
    if isinstance(value, dict):
        return {k: _trust(v) for k, v in value.items()}
    return value

ROOT = Path(__file__).resolve().parents[2]
init_plugin_loader()
LOADER = DataLoader()
DEFAULTS = LOADER.load_from_file(str(ROOT / "defaults/main.yml"))


def index_tasks(tasks):
    """Find tasks by name, including tasks nested in blocks."""
    result = {}
    for task in tasks:
        result[task["name"]] = task
        result.update(index_tasks(task.get("block", [])))
    return result


TASKS = index_tasks(LOADER.load_from_file(str(ROOT / "tasks/main.yml")))


class RoleTest(unittest.TestCase):
    def setUp(self):
        self.variables = {
            **DEFAULTS,
            "rv_user": "deploy",
            "ansible_system": "Linux",
            "ansible_facts": {},
            "ansible_env": {
                "HOME": "/home/fallback",
                "SHELL": "/bin/bash",
                "PATH": "/usr/bin:/bin",
            },
        }

    def render(self, value, **variables):
        return Templar(
            loader=LOADER, variables={**self.variables, **variables}
        ).template(_trust(value))

    def facts(self, name, **variables):
        return self.render(TASKS[name]["ansible.builtin.set_fact"], **variables)

    def should_run(self, name, **variables):
        conditions = TASKS[name].get("when", [])
        if isinstance(conditions, str):
            conditions = [conditions]
        # Load the wrapper through Ansible so the expression has the same trust
        # provenance as expressions loaded from the role, including on 2.19+.
        results = [
            self.render(LOADER.load(json.dumps("{{ (" + item + ") }}")), **variables)
            for item in conditions
        ]
        for result in results:
            self.assertIsInstance(
                result, bool, "Ansible condition did not render to a boolean"
            )
        return all(results)

    def test_supported_ruby_series_and_rejected_neighbors(self):
        for version, supported in [
            ("3.2.0", True),
            ("3.3.10", True),
            ("3.4.11", True),
            ("4.0.0", True),
            ("3.1.9", False),
            ("3.5.0", False),
            ("4.1.0", False),
            ("5.0.0", False),
            ("3.40.0", False),
        ]:
            with self.subTest(version=version):
                self.assertEqual(
                    self.should_run(
                        "Verify Ruby Version Compliance", rv_ruby_version=version
                    ),
                    not supported,
                )

    def test_supported_series_override_is_respected(self):
        self.assertFalse(
            self.should_run(
                "Verify Ruby Version Compliance",
                rv_ruby_version="5.0.0",
                rv_supported_ruby_series=["5.0"],
            )
        )
        self.assertTrue(
            self.should_run(
                "Verify Ruby Version Compliance",
                rv_ruby_version="3.4.11",
                rv_supported_ruby_series=["5.0"],
            )
        )

    def test_glibc_minimum_boundary(self):
        for version, rejected in [("2.34", True), ("2.35", False), ("2.39", False)]:
            with self.subTest(version=version):
                self.assertEqual(
                    self.should_run(
                        "Verify Glibc >= 2.35",
                        glibc_check={"stdout": "glibc " + version},
                    ),
                    rejected,
                )

    def test_glibc_probe_failure_has_actionable_diagnostic(self):
        for stderr in ["", "  unsupported variable\n"]:
            with self.subTest(stderr=stderr):
                probe = {"rc": 1, "stdout": "", "stderr": stderr}
                self.assertTrue(
                    self.should_run(
                        "Fail if glibc version could not be determined",
                        glibc_check=probe,
                    )
                )
                message = self.render(
                    TASKS["Fail if glibc version could not be determined"][
                        "ansible.builtin.fail"
                    ]["msg"],
                    glibc_check=probe,
                )
                self.assertIn("status 1", message)
                self.assertIn("glibc >= 2.35", message)
                if stderr:
                    self.assertIn("(unsupported variable)", message)
        self.assertFalse(
            self.should_run(
                "Fail if glibc version could not be determined",
                glibc_check={"rc": 0},
            )
        )

    def test_user_facts_use_getent_home_and_shell_fields(self):
        entry = ["x", "1001", "1001", "Deploy User", "/srv/deploy", "/bin/zsh"]
        user = self.facts(
            "Build user info with fallbacks",
            ansible_facts={
                "getent_passwd": {"deploy": entry},
            },
        )
        self.assertEqual(user["rv_user_entry"], entry)
        self.assertEqual(
            self.facts("Set user facts", **user),
            {
                "rv_home_dir": "/srv/deploy",
                "rv_detected_shell_path": "/bin/zsh",
                "rv_shell_name": "zsh",
                "rv_bin_dir": "/srv/deploy/.local/bin",
            },
        )

    def test_missing_user_uses_environment_fallback(self):
        for facts in [{}, {"getent_passwd": {}}, {"getent_passwd": {"other": []}}]:
            with self.subTest(facts=facts):
                user = self.facts("Build user info with fallbacks", ansible_facts=facts)
                actual = self.facts("Set user facts", **user)
                self.assertEqual(actual["rv_home_dir"], "/home/fallback")
                self.assertEqual(actual["rv_shell_name"], "bash")

    def test_macos_user_lookup_accepts_reordered_fields_and_spaces(self):
        user = self.facts(
            "Build user info with fallbacks",
            ansible_system="Darwin",
            rv_dscl_user={
                "rc": 0,
                "stdout": "UserShell: /bin/zsh\nNFSHomeDirectory: /Users/Deploy User\n",
            },
        )
        actual = self.facts("Set user facts", **user)
        self.assertEqual(actual["rv_home_dir"], "/Users/Deploy User")
        self.assertEqual(actual["rv_shell_name"], "zsh")

    def test_macos_lookup_failure_falls_back_to_environment(self):
        user = self.facts(
            "Build user info with fallbacks",
            ansible_system="Darwin",
            rv_dscl_user={"rc": 1, "stdout": ""},
        )
        self.assertEqual(
            self.facts("Set user facts", **user)["rv_home_dir"], "/home/fallback"
        )

    def test_platform_specific_user_lookup(self):
        for system in ["Linux", "Darwin"]:
            with self.subTest(system=system):
                self.assertEqual(
                    self.should_run("Get user shell info", ansible_system=system),
                    system == "Linux",
                )
                self.assertEqual(
                    self.should_run(
                        "Get user shell info (macOS)", ansible_system=system
                    ),
                    system == "Darwin",
                )

    def test_install_decision_handles_missing_current_and_old_versions(self):
        for exists, stdout, version, install in [
            (False, None, "v0.7.2", True),
            (True, "rv 0.7.2", "v0.7.2", False),
            (True, "rv 0.7.2\n", "v0.7.2", False),
            (True, "rv 0.7.2", "0.7.2", False),
            (True, "rv 0.2.0", "v0.7.2", True),
            (True, "rv 0.7.20", "v0.7.2", True),
            (True, "", "v0.7.2", True),
        ]:
            with self.subTest(exists=exists, stdout=stdout, version=version):
                variables = {
                    "rv_binary": {"stat": {"exists": exists}},
                    "rv_version": version,
                }
                if stdout is not None:
                    variables["rv_installed_version"] = {"stdout": stdout}
                self.assertEqual(
                    self.facts("Decide whether rv needs installing", **variables)[
                        "rv_needs_install"
                    ],
                    install,
                )

    def test_installer_lifecycle_runs_only_when_installing(self):
        for install in [False, True]:
            for name in [
                "Create rv installer directory",
                "Fetch rv installer",
                "Install rv via installer script",
                "Remove downloaded rv installer",
            ]:
                with self.subTest(install=install, task=name):
                    self.assertEqual(
                        self.should_run(name, rv_needs_install=install), install
                    )
        installer = TASKS["Install rv via installer script"]
        self.assertEqual(installer["environment"]["RV_NO_MODIFY_PATH"], "1")
        self.assertNotIn("creates", installer.get("args", {}))
        self.assertNotIn("creates", installer["ansible.builtin.command"])

    def test_installer_path_uses_target_home_and_release_override(self):
        self.assertEqual(
            self.render(DEFAULTS["rv_installer_path"], rv_home_dir="/srv/deploy"),
            "/srv/deploy/.cache/rv-installer.sh",
        )
        self.assertEqual(
            self.render(DEFAULTS["rv_installer_path"]),
            "/home/fallback/.cache/rv-installer.sh",
        )
        self.assertEqual(
            self.render(DEFAULTS["rv_installer_url"], rv_version="v0.8.0"),
            "https://github.com/spinel-coop/rv/releases/download/v0.8.0/rv-installer.sh",
        )

    def test_rc_file_permissions_preserve_existing_or_default_private(self):
        for stat, mode in [
            ({}, "0600"),
            ({"mode": "0600"}, "0600"),
            ({"mode": "0640"}, "0640"),
        ]:
            with self.subTest(stat=stat):
                self.assertEqual(
                    self.facts("Set config file mode", rv_rc_file_stat={"stat": stat})[
                        "rv_rc_file_mode"
                    ],
                    mode,
                )

    def test_home_directory_probes_run_as_rv_user(self):
        # A home directory is often mode 0700, so probing it as the connection
        # user fails with "Permission denied" when rv_user is someone else.
        for name in [
            "Stat existing config file",
            "Check for an existing rv installation",
            "Read installed rv version",
        ]:
            with self.subTest(task=name):
                task = TASKS[name]
                self.assertTrue(task.get("become"), f"{name} should become")
                self.assertEqual(
                    task.get("become_user"), "{{ rv_user }}", f"{name} become_user"
                )

    def test_ruby_install_requires_exact_version_managed_by_rv(self):
        managed = {"Installed": {"managed": True, "version": "ruby-3.4.11"}}
        unmanaged = {"Installed": {"managed": False, "version": "ruby-3.4.11"}}
        other = {"Installed": {"managed": True, "version": "ruby-3.4.1"}}
        available = {"Available": {"version": "ruby-3.4.11"}}
        for rubies, install in [
            ([], True),
            ([available], True),
            ([unmanaged], True),
            ([other], True),
            ([managed], False),
            ([unmanaged, other, available], True),
            ([unmanaged, other, available, managed], False),
        ]:
            with self.subTest(rubies=rubies):
                self.assertEqual(
                    self.should_run(
                        "Install Ruby",
                        rv_installed_rubies={
                            "stdout": json.dumps(rubies),
                        },
                    ),
                    install,
                )

    def test_global_pin_compares_file_content_and_runs_from_user_home(self):
        for pin, change in [
            ("", True),
            ("3.4.2\n", True),
            ("3.4.11", False),
            ("3.4.11\n", False),
            (" 3.4.11\n", False),
        ]:
            with self.subTest(pin=pin):
                self.assertEqual(
                    self.should_run(
                        "Pin Ruby globally",
                        rv_global_pin={
                            "stdout": pin,
                        },
                    ),
                    change,
                )
        self.assertEqual(
            self.render(TASKS["Pin Ruby globally"]["args"], rv_home_dir="/srv/deploy"),
            {"chdir": "/srv/deploy"},
        )

    def test_ruby_install_and_pin_honor_nondefault_version(self):
        installed = {
            "stdout": json.dumps(
                [
                    {"Installed": {"managed": True, "version": "ruby-4.0.0"}},
                ]
            )
        }
        self.assertFalse(
            self.should_run(
                "Install Ruby", rv_ruby_version="4.0.0", rv_installed_rubies=installed
            )
        )
        self.assertTrue(
            self.should_run(
                "Install Ruby", rv_ruby_version="3.4.11", rv_installed_rubies=installed
            )
        )
        self.assertFalse(
            self.should_run(
                "Pin Ruby globally",
                rv_ruby_version="4.0.0",
                rv_global_pin={"stdout": "4.0.0\n"},
            )
        )

    def test_nushell_copy_contains_both_rendered_outputs(self):
        actual = self.render(
            TASKS["Install Nushell integration"]["ansible.builtin.copy"],
            rv_nu_init={"stdout": "# init"},
            rv_nu_completions={"stdout": "# completions"},
            rv_nu_data_dir={"stdout": "/home/deploy/.local/share/nushell\n"},
        )
        self.assertEqual(actual["content"], "# init\n# completions")
        self.assertEqual(
            actual["dest"], "/home/deploy/.local/share/nushell/vendor/autoload/rv.nu"
        )

    def test_bash_path_guard_is_idempotent_and_matches_complete_entries(self):
        block = self.render(
            TASKS["Configure config file (Bash/Zsh)"]["ansible.builtin.blockinfile"][
                "block"
            ],
            rv_shell_name="bash",
        )
        # A shell function substitutes only rv; execute the production shell
        # block twice to catch duplicate PATH entries and partial-path matches.
        script = "rv() { :; }\n" + block + block + '\nprintf "%s" "$PATH"'
        with tempfile.TemporaryDirectory(prefix="rv-shell-test-") as home:
            bin_dir = home + "/.local/bin"
            for initial, expected in [
                ("/usr/bin:/bin", bin_dir + ":/usr/bin:/bin"),
                (bin_dir + ":/usr/bin", bin_dir + ":/usr/bin"),
                ("/usr/bin:" + bin_dir, "/usr/bin:" + bin_dir),
                (bin_dir + "-old:/usr/bin", bin_dir + ":" + bin_dir + "-old:/usr/bin"),
            ]:
                with self.subTest(initial=initial):
                    result = subprocess.run(
                        ["/bin/bash", "--noprofile", "--norc", "-c", script],
                        env={**os.environ, "HOME": home, "PATH": initial},
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=True,
                    )
                    self.assertEqual(result.stdout, expected)


if __name__ == "__main__":
    unittest.main()
