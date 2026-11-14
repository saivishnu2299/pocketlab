import contextlib
import sys
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
spec=importlib.util.spec_from_file_location('deploy',Path(__file__).resolve().parents[1]/'tools/pocketlab.py')
deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)

class DeploymentTests(unittest.TestCase):
    def test_update_preserves_apps_and_scores_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';dest=root/'card/Apps/PocketLab'
            source.mkdir();(source/'pocketlab').write_text('new');(source/'data').mkdir();(source/'apps').mkdir()
            (dest/'data').mkdir(parents=True);(dest/'apps/custom').mkdir(parents=True)
            (dest/'pocketlab').write_text('old');(dest/'data/settings.ini').write_text('score=123')
            (dest/'apps/custom/app.json').write_text('{}')
            with contextlib.redirect_stdout(io.StringIO()):deploy.install_tree(source,dest,('data','apps'))
            self.assertEqual((dest/'pocketlab').read_text(),'new')
            self.assertEqual((dest/'data/settings.ini').read_text(),'score=123')
            self.assertTrue((dest/'apps/custom/app.json').exists())
            backups=list(dest.parent.glob('.PocketLab.backup-*'));self.assertEqual(len(backups),1)
            self.assertEqual((backups[0]/'pocketlab').read_text(),'old')

    def test_swap_failure_restores_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';dest=root/'dest'
            source.mkdir();dest.mkdir();(source/'app').write_text('new');(dest/'app').write_text('old')
            original=Path.rename
            def fail_stage(path,target):
                if '.incoming-' in path.name:raise OSError('simulated rename failure')
                return original(path,target)
            with patch.object(Path,'rename',fail_stage),self.assertRaises(OSError):deploy.install_tree(source,dest)
            self.assertEqual((dest/'app').read_text(),'old')
            self.assertFalse(list(root.glob('*.incoming-*')))

    def test_bad_package_and_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.mkdir()
            (source/'escape').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):deploy.install_tree(source,root/'dest')
            (source/'escape').unlink()
            with self.assertRaises(ValueError):deploy.install_tree(source,source/'nested')

    def test_wrong_card_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):deploy.card_root(tmp)
    def test_new_app_contract_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Path(tmp)/'my-instrument'
            with contextlib.redirect_stdout(io.StringIO()):deploy.new_app(app,'My instrument')
            self.assertEqual(deploy.validate_app(app),app.resolve())
            self.assertFalse((app/'app').exists())
            self.assertIn('pocketlab_ready()', (app/'app.c').read_text())
            self.assertTrue((app/'AGENTS.md').exists())
            (app/'precious.txt').write_text('keep')
            with self.assertRaises(ValueError):deploy.new_app(app)
            self.assertEqual((app/'precious.txt').read_text(),'keep')
            for name in ('starfall','Invalid','1bad','x'*49):
                with self.assertRaises(ValueError):deploy.new_app(Path(tmp)/name)

    def test_usb_upload_rejects_links_before_copying(self):
        from usb_deploy import Brick
        with tempfile.TemporaryDirectory() as tmp:
            app=Path(tmp)/'source';app.mkdir()
            (app/'escape').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):Brick.__new__(Brick).upload(app,'unused','unused')

if __name__=='__main__':unittest.main(verbosity=2)
