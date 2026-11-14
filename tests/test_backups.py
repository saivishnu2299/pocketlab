from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from maintenance import backups,restore_card
from pocketlab import package,install_tree
import contextlib
import io


class BackupTests(unittest.TestCase):
    def test_card_restore_preserves_current_data_and_recovers_missing_folder(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            card=Path(tmp);(card/'Apps').mkdir();(card/'Roms').mkdir();target=card/'Apps/PocketLab'
            install_tree(package(),target)
            (target/'data/score').write_text('old')
            install_tree(package(),target,('data','apps'))
            previous=next((card/'Apps').glob('.PocketLab.backup-*'))
            (target/'data/score').write_text('new')
            (target/'data/pending-shell-update').write_text('0'*32+' ready\n')
            restore_card(card,previous.name)
            self.assertEqual((target/'data/score').read_text(),'new')
            self.assertFalse((target/'data/pending-shell-update').exists())
            missing=card/'Apps/.PocketLab.backup-abcdef1234';target.rename(missing)
            with self.assertRaises(ValueError):install_tree(package(),target)
            restore_card(card,missing.name)
            self.assertEqual((target/'data/score').read_text(),'new')

    def test_only_old_named_backups_removed_and_live_data_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            card=Path(tmp);root=card/'Apps/PocketLab';(root/'apps/current').mkdir(parents=True)
            (root/'data').mkdir();(card/'Roms').mkdir()
            (root/'data/score').write_text('42');(root/'apps/current/app.json').write_text('{}')
            for i in range(3):
                p=root/'apps'/('.backup-current-'+str(i)*32);p.mkdir();(p/'app.json').write_text('{}')
                os.utime(p,(i+1,i+1))
            unknown=root/'apps/.backup-unknown';unknown.mkdir();(unknown/'keep').write_text('keep')
            report=backups(card);self.assertEqual(len(report['backups']),3)
            self.assertEqual(sum(x['eligible'] for x in report['backups']),1)
            self.assertFalse(any(x['removed'] for x in report['backups']))
            report=backups(card,True,2);self.assertEqual(sum(x['removed'] for x in report['backups']),1)
            self.assertEqual((root/'data/score').read_text(),'42')
            self.assertTrue((root/'apps/current/app.json').exists());self.assertTrue((unknown/'keep').exists())

    def test_pending_shell_backup_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            card=Path(tmp);root=card/'Apps/PocketLab';(root/'data/updates').mkdir(parents=True);(card/'Roms').mkdir()
            for i in range(3):
                p=root/'data/updates'/(str(i)*32);p.mkdir();(p/'backup.sha256').write_text('fixture');os.utime(p,(i+1,i+1))
            (root/'data/pending-shell-update').write_text('0'*32+' copying\n')
            backups(card,True,1)
            self.assertTrue((root/'data/updates'/('0'*32)).exists())

    def test_zero_retention_refused(self):
        with self.assertRaises(ValueError):backups('/not-a-card',True,0)


if __name__=='__main__':unittest.main()
