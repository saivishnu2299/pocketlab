import contextlib
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import onboarding
import repo_update


def git(cwd, *args):
    subprocess.run(['git', *args], cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@unittest.skipUnless(shutil.which('git'), 'git is required')
class RepoUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.upstream, self.clone = base/'upstream', base/'clone'
        self.upstream.mkdir()
        git(self.upstream, 'init', '-q', '-b', 'main')
        for key, value in (('user.name', 'Test'), ('user.email', 'test@example.invalid'), ('commit.gpgsign', 'false')):
            git(self.upstream, 'config', key, value)
        (self.upstream/'.gitignore').write_text('/miniapps/*\n!/miniapps/README.md\n')
        (self.upstream/'shell.c').write_text('v1\n')
        git(self.upstream, 'add', '.'); git(self.upstream, 'commit', '-q', '-m', 'v1')
        git(base, 'clone', '-q', str(self.upstream), str(self.clone))
        app = self.clone/'miniapps/my-app'
        app.mkdir(parents=True); (app/'app.c').write_text('mine\n')
        self.root = patch('repo_update.ROOT', self.clone); self.root.start()

    def tearDown(self):
        self.root.stop(); self.tmp.cleanup()

    def publish(self, text):
        (self.upstream/'shell.c').write_text(text)
        git(self.upstream, 'commit', '-q', '-am', text.strip())

    def test_pull_fast_forwards_and_keeps_mini_apps(self):
        self.publish('v2\n')
        old, new = repo_update.pull()
        self.assertNotEqual(old, new)
        self.assertEqual((self.clone/'shell.c').read_text(), 'v2\n')
        self.assertEqual((self.clone/'miniapps/my-app/app.c').read_text(), 'mine\n')

    def test_pull_refuses_local_edits_to_tracked_files(self):
        self.publish('v2\n')
        (self.clone/'shell.c').write_text('edited\n')
        with self.assertRaisesRegex(ValueError, 'shell.c'):
            repo_update.pull()
        self.assertEqual((self.clone/'shell.c').read_text(), 'edited\n')

    def test_untracked_mini_apps_are_not_reported_as_edits(self):
        self.assertEqual(repo_update.changed_tracked_files(), [])

    def test_update_without_target_only_prints_next_steps(self):
        with patch('repo_update.subprocess.call') as call, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(repo_update.update(), 0)
        call.assert_not_called()
        self.assertIn('install --usb --confirm-model TG4040', out.getvalue())

    def test_update_runs_card_setup_with_fresh_code(self):
        with patch('repo_update.subprocess.call', return_value=0) as call, contextlib.redirect_stdout(io.StringIO()):
            repo_update.update(sd='/Volumes/CARD', eject=True)
        command = call.call_args[0][0]
        self.assertEqual(command[1:], [str(self.clone/'tools/pocketlab.py'), 'setup', '--sd', '/Volumes/CARD', '--eject'])

    def test_doctor_warns_without_failing(self):
        (self.clone/'shell.c').write_text('edited\n')
        with patch('release.verify_runtime'):
            report = onboarding.diagnostics()
        source = [c for c in report['checks'] if c['name'] == 'source']
        self.assertTrue(source and source[0]['ok'] and source[0]['warn'])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            onboarding.show_diagnostics(report)
        self.assertIn('WARN source:', out.getvalue())


if __name__ == '__main__':
    unittest.main()
