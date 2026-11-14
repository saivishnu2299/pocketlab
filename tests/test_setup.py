import contextlib
import io
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import onboarding
import pocketlab
import release
from stock_card import stock_from_directory


class SetupTests(unittest.TestCase):
    def test_prebuilt_install_preserves_user_files_without_building(self):
        with tempfile.TemporaryDirectory() as tmp:
            card=Path(tmp);(card/'Apps/PocketLab/data').mkdir(parents=True)
            (card/'Apps/PocketLab/apps/user-app').mkdir(parents=True)
            (card/'Roms').mkdir();(card/'Roms/keep.bin').write_bytes(b'unchanged')
            (card/'Apps/PocketLab/data/score').write_bytes(b'42')
            (card/'Apps/PocketLab/apps/user-app/app.json').write_text('{}')
            with patch('pocketlab.compile_arm',side_effect=AssertionError('Installation invoked compiler')):
                with contextlib.redirect_stdout(io.StringIO()):
                    pocketlab.install_tree(pocketlab.package(),card/'Apps/PocketLab',('data','apps'))
            self.assertEqual((card/'Roms/keep.bin').read_bytes(),b'unchanged')
            self.assertEqual((card/'Apps/PocketLab/data/score').read_bytes(),b'42')
            self.assertTrue((card/'Apps/PocketLab/apps/user-app/app.json').exists())
            self.assertTrue(onboarding.diagnostics(sd=str(card))['ok'])

    def test_new_card_copy_and_populated_card_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)/'base';card=Path(tmp)/'card';base.mkdir();card.mkdir()
            (base/'Apps').mkdir();(base/'Roms').mkdir();(base/'stock.txt').write_text('stock')
            stock = stock_from_directory(base)
            with contextlib.redirect_stdout(io.StringIO()), patch('stock_card.flush_writes'):
                work = onboarding.prepare_tree(stock, card, identity='fixture', check_mount=lambda: None)
            self.assertEqual((card/'stock.txt').read_text(), 'stock')
            shutil.rmtree(work)
            (card/'keep.txt').write_text('user data')
            with self.assertRaisesRegex(ValueError,'empty card'):
                onboarding.prepare_tree(stock, card, identity='fixture', check_mount=lambda: None)
            self.assertEqual((card/'keep.txt').read_text(),'user data')

    def test_new_card_requires_explicit_choice_and_refuses_links(self):
        with self.assertRaises(ValueError):onboarding.prepare_card('/not-a-card')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'source').mkdir();(root/'source/escape').symlink_to(root)
            (root/'card').mkdir()
            with self.assertRaises(ValueError):stock_from_directory(root/'source')
            self.assertEqual(list((root/'card').iterdir()),[])

    def test_low_space_does_not_change_installed_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'old';new=root/'new';old.mkdir();new.mkdir()
            (old/'app').write_text('old');(new/'app').write_text('new')
            with patch('pocketlab.shutil.disk_usage',return_value=shutil._ntuple_diskusage(100,99,1)):
                with self.assertRaises(ValueError):pocketlab.install_tree(new,old)
            self.assertEqual((old/'app').read_text(),'old')

    def test_format_plan_is_read_only_and_confirmation_is_required(self):
        identity={'device':'/dev/disk99','confirmation':'ERASE-fixture','TotalSize':1234}
        with patch('onboarding.disk_info',return_value=identity), patch('onboarding.subprocess.run') as run:
            self.assertEqual(onboarding.format_card('/dev/disk99')['action'],'format-plan')
            with self.assertRaises(ValueError):onboarding.format_card('/dev/disk99','wrong')
            run.assert_not_called()

    def test_format_rechecks_device_after_preparation(self):
        identity={'device':'/dev/disk99','confirmation':'ERASE-fixture'}
        with patch('onboarding.disk_info',side_effect=[identity,dict(identity,device='changed')]), \
             patch('release.verify_runtime'),patch('onboarding.stock_base'),patch('onboarding.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError,'identity changed'):
                onboarding.format_card('/dev/disk99','ERASE-fixture')
            run.assert_not_called()

    def test_only_confirmed_external_disk_can_reach_formatter(self):
        identity={'device':'/dev/disk99','confirmation':'ERASE-fixture'}
        with patch('onboarding.disk_info',return_value=identity),patch('release.verify_runtime'), \
             patch('onboarding.stock_base'),patch('onboarding.subprocess.run') as run:
            result=onboarding.format_card('/dev/disk99','ERASE-fixture')
            run.assert_called_once_with(['diskutil','eraseDisk','FAT32','POCKETLAB','MBRFormat','/dev/disk99'],check=True)
            self.assertEqual(result['action'],'formatted')

    def test_disk_inventory_rejects_internal_or_nonphysical_targets(self):
        info={'DeviceIdentifier':'disk99','WholeDisk':True,'Internal':True,'Writable':True,'TotalSize':123}
        listing={'AllDisksAndPartitions':[{'DeviceIdentifier':'disk99'}]}
        with patch('onboarding.platform.system',return_value='Darwin'), \
             patch('onboarding.subprocess.check_output',side_effect=[plistlib.dumps(info),plistlib.dumps(listing)]):
            with self.assertRaises(ValueError):onboarding.disk_info('/dev/disk99')
        with patch('onboarding.platform.system',return_value='Darwin'):
            with self.assertRaises(ValueError):onboarding.disk_info('/dev/disk99s1')

    def test_format_plan_accepts_macos_whole_disk_property(self):
        info={'DeviceIdentifier':'disk99','WholeDisk':True,'Internal':False,
              'Writable':True,'TotalSize':7744782336,'MediaName':'SD fixture','BusProtocol':'USB'}
        listing={'AllDisksAndPartitions':[{'DeviceIdentifier':'disk99'}]}
        with patch('onboarding.platform.system',return_value='Darwin'), \
             patch('onboarding.subprocess.check_output',side_effect=[plistlib.dumps(info),plistlib.dumps(listing)]), \
             patch('onboarding.subprocess.run') as run:
            plan=onboarding.format_card('/dev/disk99')
            self.assertEqual(plan['action'],'format-plan')
            self.assertEqual(plan['disk']['device'],'/dev/disk99')
            self.assertTrue(plan['disk']['confirmation'].startswith('ERASE-'))
            run.assert_not_called()

    def test_disk_inventory_refuses_non_whole_disk(self):
        info={'DeviceIdentifier':'disk99','WholeDisk':False,'Internal':False,
              'Writable':True,'TotalSize':123}
        listing={'AllDisksAndPartitions':[{'DeviceIdentifier':'disk99'}]}
        with patch('onboarding.platform.system',return_value='Darwin'), \
             patch('onboarding.subprocess.check_output',side_effect=[plistlib.dumps(info),plistlib.dumps(listing)]):
            with self.assertRaises(ValueError):onboarding.disk_info('/dev/disk99')

    def test_diagnostics_are_machine_readable_and_nonzero_on_failure(self):
        with patch('release.verify_runtime',side_effect=ValueError('missing runtime')):
            report=onboarding.diagnostics()
        out=io.StringIO()
        with contextlib.redirect_stdout(out):code=onboarding.show_diagnostics(report,True)
        self.assertEqual(code,1);self.assertFalse(json.loads(out.getvalue())['ok'])

    def test_no_interactive_setup_in_an_agent_pipe(self):
        with patch('sys.stdin.isatty',return_value=False):
            with self.assertRaisesRegex(ValueError,'explicit|Choose setup'):
                onboarding.guided_setup()


if __name__=='__main__':unittest.main()
