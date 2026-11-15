import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import release
import pocketlab


class ReleaseTests(unittest.TestCase):
    def test_tracked_private_files_block_release(self):
        # Source ZIPs do not contain .git; simulate a checkout without changing it.
        real_exists=Path.exists
        def exists(path):
            return True if path==ROOT/'.git' else real_exists(path)
        with patch.object(Path,'exists',exists),patch('release.subprocess.check_output',return_value=b'private-project/notes.txt\0'):
            with self.assertRaisesRegex(ValueError,'outside the public release allowlist'):
                release.check()

    def test_frozen_ui_and_only_two_defaults(self):
        self.assertEqual(release.core_hashes(),json.loads((ROOT/'tests/baseline/ui-source.json').read_text()))
        info=release.verify_runtime()
        self.assertEqual(info['default_apps'],['esp32','starfall'])
        self.assertEqual(info['binary']['glibc'],['GLIBC_2.17'])
        self.assertEqual(set(info['binary']['needed']),{'libSDL2-2.0.so.0','libm.so.6','libpthread.so.0','libc.so.6'})

    def test_payload_rejects_unexpected_apps_or_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'runtime';shutil.copytree(release.RUNTIME,target)
            (target/'apps/private').mkdir(parents=True);(target/'apps/private/app.json').write_text('{}')
            with self.assertRaises(ValueError):release.verify_runtime(target)
            shutil.rmtree(target/'apps')
            (target/'pocketlab').write_bytes(b'broken')
            with self.assertRaises(ValueError):release.verify_runtime(target)

    def test_manifest_cannot_escape_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'runtime';shutil.copytree(release.RUNTIME,target)
            p=target/'manifest.sha256.json';data=json.loads(p.read_text());data['../outside']='0'*64;p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):release.verify_runtime(target)

    def test_launcher_icon_is_drawn_once(self):
        self.assertEqual(json.loads((release.RUNTIME/'config.json').read_text())['icon'],'')
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'runtime';shutil.copytree(release.RUNTIME,target)
            config=target/'config.json';data=json.loads(config.read_text());data['icon']='icon.png'
            config.write_text(json.dumps(data))
            manifest=target/'manifest.sha256.json';hashes=json.loads(manifest.read_text())
            hashes['config.json']=release.digest(config);manifest.write_text(json.dumps(hashes))
            with self.assertRaisesRegex(ValueError,'icontop'):release.verify_runtime(target)

    def test_neutral_template_contract(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            app=pocketlab.new_app(Path(tmp)/'test-instrument','Test instrument')
            self.assertEqual(json.loads((app/'app.json').read_text())['ready'],'file')
            self.assertIn('Test instrument',(app/'app.c').read_text())
            self.assertTrue((app/'cover.bmp').exists())
            self.assertFalse((app/'app').exists())

    def test_allowlist_excludes_user_and_generated_directories(self):
        for name in release.source_files():
            if name == 'miniapps/README.md':
                continue
            self.assertNotIn(Path(name).parts[0],{'miniapps','projects','build','dist','data','examples','.git'})
        self.assertIn('templates/native-app/app.c',release.source_files())
        self.assertIn('miniapps/README.md',release.source_files())

    def test_archives_have_fixed_names_timestamps_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);f=root/'file';f.write_text('fixture');f.chmod(0o755)
            one=root/'one.zip';two=root/'two.zip'
            release.archive(one,[('folder/file',f)]);release.archive(two,[('folder/file',f)])
            self.assertEqual(one.read_bytes(),two.read_bytes())
            with zipfile.ZipFile(one) as archive:
                self.assertEqual(archive.namelist(),['folder/file'])
                self.assertEqual(archive.getinfo('folder/file').external_attr>>16 & 0o777,0o755)


if __name__=='__main__':unittest.main()
