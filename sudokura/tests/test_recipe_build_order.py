"""Enforce the scanner-before-dependency-restoration contract in local metadata.

The pinned fdroidserver 2.4.5 processes build commands after its source scan.
These offline structural tests do not claim a real F-Droid build or Gradle clean.
"""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
RECIPE = ROOT / 'metadata' / 'org.cajapersonal.sudokura.yml'
SOURCE_SHA = 'c1b3eb31e82bcc06a078bc10e10f342aa8329e25'
RESTORE = ('python3 /work/fdroid/tools/offline-android-inputs.py restore '
           f'. /work/verified-inputs {SOURCE_SHA}')
ASSETS = 'cd .. && make assets'


def validate_recipe(text):
    """Fail if native binaries can be staged before source scanning."""
    if text.count('\nBuilds:\n') != 1 or text.count('\nCurrentVersion:') != 1:
        raise ValueError('Expected one app recipe')
    build = text.split('\nBuilds:\n', 1)[1].split('\nCurrentVersion:', 1)[0]
    if re.search(r'(?m)^    (?:prebuild|init|patch|scanignore|scandelete|sudo):', build):
        raise ValueError('Pre-scanner changes or scanner exceptions are not allowed')
    if re.search(r'(?im)\b(?:skip[-_]?scan|force|scanignore|scandelete)\b', build):
        raise ValueError('Source scanner must not be bypassed')
    fields = re.findall(r'(?m)^    build:\s*$', build)
    if len(fields) != 1:
        raise ValueError('Build commands must occur in the post-scan build field')
    commands = re.findall(r'(?m)^      - (.*)$', build.split('    build:\n', 1)[1]
                          .split('    output:', 1)[0])
    if commands != [RESTORE, ASSETS]:
        raise ValueError('Expected exact verified restore followed by asset generation')
    if f'    commit: {SOURCE_SHA}\n' not in build:
        raise ValueError('Immutable published commit changed')
    if ('    gradle:\n      - production\n' not in build
            or '  - versionName: 1.4.0\n' not in build
            or '    versionCode: 1\n' not in build):
        raise ValueError('Wrong build variant or version')
    if text.count('Repo: https://github.com/santirodriguez/Sudokura.git') != 1:
        raise ValueError('Template upstream source identity changed')
    if 'Binaries:' in text or 'AllowedAPKSigningKeys:' in text:
        raise ValueError('No upstream binaries or signing authority are allowed')


class RecipeBuildOrderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipe = RECIPE.read_text(encoding='utf-8')

    def test_current_recipe_uses_postscan_build_field(self):
        validate_recipe(self.recipe)

    def test_prebuild_restoration_is_rejected(self):
        mutated = self.recipe.replace('    build:\n', '    prebuild:\n', 1)
        with self.assertRaises(ValueError):
            validate_recipe(mutated)

    def test_scanner_bypass_is_rejected(self):
        for field in ('scanignore', 'scandelete', 'sudo'):
            mutated = self.recipe.replace('    output:', f'    {field}:\n      - android/.cache\n    output:', 1)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_recipe(mutated)

    def test_commands_must_run_in_verified_order(self):
        mutations = (
            self.recipe.replace(f'      - {RESTORE}\n      - {ASSETS}',
                                f'      - {ASSETS}\n      - {RESTORE}', 1),
            self.recipe.replace(f'      - {RESTORE}\n', '', 1),
            self.recipe.replace(f'      - {ASSETS}\n', '', 1),
            self.recipe.replace(f'      - {RESTORE}\n',
                                f'      - {RESTORE}\n      - echo additional-command\n', 1),
        )
        for candidate in mutations:
            with self.subTest(candidate=candidate[-240:]), self.assertRaises(ValueError):
                validate_recipe(candidate)

    def test_source_revision_and_version_are_locked(self):
        for old, new in ((SOURCE_SHA, '0' * 40),
                         ('versionCode: 1', 'versionCode: 2'),
                         ('versionName: 1.4.0', 'versionName: 1.4.1'),
                         ('- production', '- prototype')):
            with self.subTest(field=old), self.assertRaises(ValueError):
                validate_recipe(self.recipe.replace(old, new))

    def test_no_remote_submission_or_signing_fields(self):
        validate_recipe(self.recipe)
        self.assertNotIn('fdroid publish', self.recipe)
        self.assertNotIn('fdroid deploy', self.recipe)
        self.assertNotIn('AllowedAPKSigningKeys', self.recipe)


if __name__ == '__main__':
    unittest.main()
