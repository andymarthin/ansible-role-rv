"""Exercise the release workflow's real extraction script without GitHub writes.

Run from the repository root: python -m unittest discover -s tests/unit -v
"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
with (ROOT / ".github/workflows/release.yml").open() as workflow_file:
    WORKFLOW = yaml.safe_load(workflow_file)
EXTRACT_NOTES = next(
    step["run"]
    for step in WORKFLOW["jobs"]["release"]["steps"]
    if step.get("id") == "changelog"
)


class ReleaseNotesTest(unittest.TestCase):
    def extract(self, changelog, tag="v0.2.0"):
        with tempfile.TemporaryDirectory(prefix="rv-release-test-") as directory:
            if changelog is not None:
                (Path(directory) / "CHANGELOG.md").write_text(changelog)
            result = subprocess.run(
                ["/bin/bash", "--noprofile", "--norc", "-c", EXTRACT_NOTES],
                cwd=directory,
                env={**os.environ, "GITHUB_REF_NAME": tag},
                capture_output=True,
                text=True,
                timeout=5,
            )
            notes = Path(directory) / "release-notes.md"
            return result, notes.read_text() if notes.exists() else None

    def test_extracts_only_matching_section_and_preserves_markdown(self):
        result, notes = self.extract(
            "# Changelog\n\n## [Unreleased]\n\n- Pending\n\n"
            "## [0.2.0] - 2026-10-22\n\n\n### Fixed\n\n"
            "- Upgrade rv.\n- Keep `code` and [links](https://example.com).\n\n\n"
            "## [0.1.0] - 2025-01-01\n\n- Older changes.\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            notes,
            "### Fixed\n\n- Upgrade rv.\n"
            "- Keep `code` and [links](https://example.com).\n",
        )

    def test_last_section_excludes_link_references(self):
        result, notes = self.extract(
            "## [0.2.0]\n\n- Fix.\n\n"
            "[Unreleased]: https://example.com/compare\n"
            "[0.2.0]: https://example.com/release\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(notes, "- Fix.\n")

    def test_section_at_end_of_file_without_final_newline(self):
        result, notes = self.extract("## [0.2.0]\n\n- Final change.")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(notes, "- Final change.\n")

    def test_missing_changelog_fails(self):
        result, notes = self.extract(None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CHANGELOG.md not found", result.stdout)
        self.assertIsNone(notes)

    def test_missing_or_near_match_version_fails(self):
        for heading in ["0.1.0", "0x2y0", "0.2.01", "10.2.0"]:
            with self.subTest(heading=heading):
                result, notes = self.extract(f"## [{heading}]\n\n- Wrong version.\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("has no '## [0.2.0]' section", result.stdout)
                self.assertIsNone(notes)

    def test_empty_section_fails_at_each_termination_boundary(self):
        for tail in [
            "",
            "\n\n",
            "\n## [0.1.0]\n\n- Previous.\n",
            "\n[0.2.0]: https://example.com/release\n",
        ]:
            with self.subTest(tail=tail):
                result, notes = self.extract("## [0.2.0]\n" + tail)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("section for 0.2.0 is empty", result.stdout)
                self.assertEqual(notes, "")


if __name__ == "__main__":
    unittest.main()
