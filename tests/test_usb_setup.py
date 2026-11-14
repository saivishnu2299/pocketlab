import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from usb_deploy import Brick,USBError


class DiscoveryTests(unittest.TestCase):
    def connect(self, config=None, arch='aarch64', **kwargs):
        def remote(_self, script, **_kw):
            if script=='uname -m':return arch
            if script.startswith('cat ') and script.endswith('/config.json'):
                if config is None:raise USBError('absent')
                return json.dumps(config)
            return ''
        result=subprocess.CompletedProcess([],0,stdout='List of devices attached\nfixture\tdevice\n')
        with patch('usb_deploy.shutil.which',return_value='/fixture/adb'), \
             patch('usb_deploy.subprocess.run',return_value=result),patch.object(Brick,'remote',remote):
            return Brick(**kwargs)

    def test_absent_install_can_be_discovered_with_model_confirmation(self):
        self.assertFalse(self.connect(require_install=False,confirm_model='TG4040').installed)
    def test_absent_install_requires_model_confirmation(self):
        with self.assertRaises(USBError):self.connect(require_install=False)
    def test_normal_operations_require_installation(self):
        with self.assertRaises(USBError):self.connect()
    def test_wrong_architecture_and_wrong_package_are_rejected(self):
        with self.assertRaises(USBError):self.connect(arch='x86_64',require_install=False,confirm_model='TG4040')
        for config in ({'package':'wrong'}, ['unexpected']):
            with self.assertRaises(USBError):self.connect(config=config)
    def test_existing_install_uses_package_identity(self):
        self.assertTrue(self.connect(config={'package':'org.pocketlab.shell'}).installed)


if __name__=='__main__':unittest.main()
