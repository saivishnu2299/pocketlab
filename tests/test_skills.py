"""Keep the agent skills and documented commands consistent with the CLI and docs.

The skills in skills/ are copied or linked into users' agents and updated with
the checkout. These checks fail when a command, flag, file or AGENTS.md section
that a skill (or a guide) relies on is renamed or removed.
"""
from pathlib import Path
import re
import shlex
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import pocketlab
import release

SKILLS = sorted(p for p in (ROOT/'skills').iterdir() if p.is_dir())
GUIDES = ['AGENTS.md', 'README.md', 'SDK.md', 'CONTRIBUTING.md', 'miniapps/README.md',
          'templates/native-app/AGENTS.md', *sorted(str(p.relative_to(ROOT)) for p in (ROOT/'docs').glob('*.md'))]
COMMAND = re.compile(r'(?:\./pocketlab|tools/pocketlab\.py)((?: +[^`\n#|]*)?)')


def frontmatter(path):
    text = path.read_text()
    match = re.match(r'---\n(.*?)\n---\n', text, re.S)
    if not match:
        raise AssertionError(f'{path} has no frontmatter')
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(':')
        fields[key.strip()] = value.strip()
    return fields, text[match.end():]


def subcommands():
    parser = pocketlab.build_parser()
    action = next(a for a in parser._actions if a.__class__.__name__ == '_SubParsersAction')
    return {name: {flag for a in sub._actions for flag in a.option_strings}
            for name, sub in action.choices.items()}


def commands_in(text):
    for match in COMMAND.finditer(text):
        try:
            words = shlex.split(match.group(1))
        except ValueError:
            words = match.group(1).split()
        if words and not words[0].startswith('-'):
            yield words[0], [w.split('=')[0] for w in words[1:] if w.startswith('--')]


class SkillTests(unittest.TestCase):
    def test_expected_skills_exist(self):
        self.assertEqual([p.name for p in SKILLS], ['pocketlab-device', 'pocketlab-miniapp'])

    def test_frontmatter_is_valid(self):
        for skill in SKILLS:
            fields, body = frontmatter(skill/'SKILL.md')
            self.assertEqual(set(fields), {'name', 'description'}, skill.name)
            self.assertEqual(fields['name'], skill.name)
            self.assertRegex(fields['name'], r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
            self.assertTrue(0 < len(fields['description']) <= 1024, skill.name)
            self.assertNotRegex(fields['description'], r'[<>]')
            self.assertTrue(body.strip())

    def test_skills_are_public_release_files(self):
        files = release.source_files()
        for skill in SKILLS:
            for path in skill.rglob('*'):
                if path.is_file():
                    self.assertIn(path.relative_to(ROOT).as_posix(), files)

    def test_documented_commands_and_flags_exist(self):
        known = subcommands()
        sources = [skill/'SKILL.md' for skill in SKILLS] + [ROOT/name for name in GUIDES]
        for path in sources:
            for name, flags in commands_in(path.read_text()):
                where = f'{path.relative_to(ROOT)}: ./pocketlab {name}'
                self.assertIn(name, known, where)
                for flag in flags:
                    self.assertIn(flag, known[name], f'{where} {flag}')

    def test_referenced_files_exist(self):
        for skill in SKILLS:
            _, body = frontmatter(skill/'SKILL.md')
            for name in re.findall(r'`([\w./-]+\.(?:md|py|json))`', body):
                if '/' in name or name in ('AGENTS.md', 'SDK.md'):
                    self.assertTrue((ROOT/name).is_file(), f'{skill.name}: {name}')

    def test_referenced_agents_sections_exist(self):
        headings = set(re.findall(r'^#+ (.+)$', (ROOT/'AGENTS.md').read_text(), re.M))
        for skill in SKILLS:
            _, body = frontmatter(skill/'SKILL.md')
            for first, second in re.findall(r'"([^"]+)"(?: and "([^"]+)")? sections? of', body):
                for heading in filter(None, (first, second)):
                    self.assertIn(heading, headings, f'{skill.name}: AGENTS.md section "{heading}"')

    def test_skills_name_each_other_correctly(self):
        names = {p.name for p in SKILLS}
        for skill in SKILLS:
            _, body = frontmatter(skill/'SKILL.md')
            for name in re.findall(r'\bpocketlab-[a-z]+\b', body):
                self.assertIn(name, names, skill.name)


if __name__ == '__main__':
    unittest.main()
