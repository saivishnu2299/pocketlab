"""USB filesystem and ROM protocol tests using an isolated sysfs and a PTY."""
import os
import pathlib
import pty
import select
import shutil
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / 'build/usb-test'

class USBTests(unittest.TestCase):
    def test_inventory_hotplug_and_missing_driver(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            devices = root / 'bus/usb/devices'
            devices.mkdir(parents=True)
            tty = root / 'class/tty/ttyUSB0'
            tty.mkdir(parents=True)
            def device(name, vid, pid, product, klass='00', instance='12'):
                p = devices / name
                p.mkdir()
                for k,v in dict(idVendor=vid,idProduct=pid,product=product,bDeviceClass=klass,devnum=instance).items():
                    (p / k).write_text(v)
                return p
            shared = device('1-1','10c4','ea60','CP2102 USB bridge')
            longprefix = device('1-10','303a','1001','ESP32-S3')
            device('usb1','1d6b','0002','Linux USB root hub','09')
            device('1-2','046d','1234','USB Keyboard')
            nested = longprefix / '1-10:1.0/ttyUSB0'
            nested.mkdir(parents=True)
            (tty / 'device').symlink_to(nested)
            def scan():
                return subprocess.check_output([CLI,'scan',root],text=True).splitlines()
            rows=scan()
            self.assertEqual(rows[0], '1\t2\t3')
            self.assertEqual(rows[1].split('\t')[3:5],['1',''])
            self.assertEqual(rows[2].split('\t')[3:5],['3','/dev/ttyUSB0'])
            shutil.rmtree(longprefix)
            self.assertEqual(scan()[0],'1\t1\t2')
            shutil.rmtree(shared)
            self.assertEqual(scan()[0],'1\t0\t1')
            shutil.rmtree(devices)
            self.assertEqual(scan()[0],'0\t0\t0')

    def emulate(self, chipid=None, magic=None, malformed=False, silence=False, two_status=False):
        master,slave=pty.openpty()
        process=subprocess.Popen([CLI,'probe',os.ttyname(slave)],stdout=subprocess.PIPE,text=True)
        commands=[];frame=bytearray();active=False;escaped=False
        end=time.monotonic()+9
        def respond(command, data=b'\0\0\0\0', value=0):
            packet=struct.pack('<BBHI',1,command,len(data),value)+data
            if malformed: packet=packet[:2]+b'\xff\xff'+packet[4:]
            packet=packet.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')
            os.write(master,b'\xc0'+packet+b'\xc0')
        try:
            while process.poll() is None and time.monotonic()<end:
                if not select.select([master],[],[],.05)[0]:continue
                for b in os.read(master,4096):
                    if b==0xc0:
                        if active and len(frame)>=8:
                            command=frame[1];commands.append(command)
                            self.assertIn(command,(8,0x14,0x0a), 'Probe must never send flash/write commands')
                            if not silence:
                                if command==8:respond(command,b'\0\0' if two_status else b'\0'*4)
                                elif command==0x14:
                                    respond(command, b'\0'*12+struct.pack('<I',chipid)+b'\0'*8) if chipid is not None else respond(command,b'\x01\x05\0\0')
                                elif command==0x0a:
                                    self.assertEqual(bytes(frame[8:12]),struct.pack('<I',0x40001000))
                                    respond(command,b'\0\0' if two_status else b'\0'*4,magic or 0)
                        active=True;escaped=False;frame.clear();continue
                    if not active:continue
                    if b==0xdb:escaped=True;continue
                    if escaped:b={0xdc:0xc0,0xdd:0xdb}.get(b,b);escaped=False
                    frame.append(b)
            out,_=process.communicate(timeout=2)
            return process.returncode,out.strip(),commands
        finally:
            if process.poll() is None:process.kill();process.wait()
            os.close(master);os.close(slave)

    def test_esp32s3_security_info(self):
        rc,out,commands=self.emulate(chipid=9)
        self.assertEqual((rc,out),(0,'ESP32-S3'))
        self.assertEqual(commands,[8,0x14])
    def test_esp32_legacy_register(self):
        rc,out,commands=self.emulate(magic=0x00f01d83)
        self.assertEqual((rc,out),(0,'ESP32'))
        self.assertEqual(commands,[8,0x14,0x0a])
    def test_esp8266_is_not_mislabeled(self):
        rc,out,_=self.emulate(magic=0xfff0c101,two_status=True)
        self.assertEqual((rc,out),(0,'ESP8266 (not ESP32)'))
    def test_unknown_espressif(self):
        rc,out,_=self.emulate(chipid=0xc0db)
        self.assertEqual((rc,out),(0,'Espressif chip (ID 49371)'))
    def test_malformed_response_rejected(self):
        rc,out,_=self.emulate(malformed=True)
        self.assertEqual(rc,2);self.assertIn('No chip identity',out)
    def test_silent_device_timeout(self):
        rc,out,_=self.emulate(silence=True)
        self.assertEqual(rc,2);self.assertIn('No chip identity',out)
    def test_unavailable_port(self):
        r=subprocess.run([CLI,'probe','/dev/pocketlab-does-not-exist'],text=True,capture_output=True)
        self.assertEqual(r.returncode,2);self.assertIn('Cannot open',r.stdout)

if __name__=='__main__':unittest.main(verbosity=2)
