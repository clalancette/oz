# Copyright (C) 2013  Chris Lalancette <clalancette@gmail.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation;
# version 2.1 of the License.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

"""
Mageia installation
"""

import shutil
import os
import re

import oz.Guest
import oz.ozutil
import oz.OzException
try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse


class MageiaGuest(oz.Guest.CDGuest):
    """
    Class for Mageia 4 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        if netdev is None:
            netdev = "virtio"
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk, netdev,
                                  None, None, diskbus, True, False, macaddress)

        self.mageia_arch = self.tdl.arch
        if self.mageia_arch == "i386":
            self.mageia_arch = "i586"
        self.output_floppy = os.path.join(self.output_dir,
                                          self.tdl.name + "-" + self.tdl.installtype + "-oz.img")


    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying cfg file to floppy image")

        pathdir = os.path.join(self.iso_contents, self.mageia_arch)

        if not os.path.exists(pathdir):
            pathdir = self.iso_contents

        outname = "/tmp/auto_inst.cfg"

        if self.default_auto_file():

            def _cfg_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Mageia.
                """
                if re.search("'password' =>", line):
                    return "			'password' => '" + self.rootpw + "',\n"
                else:
                    return line

            oz.ozutil.copy_modify_file(self.auto, outname, _cfg_sub)
        else:
            shutil.copy(self.auto, outname)
        try:
            os.unlink(self.output_floppy)
        except:
            pass
        oz.ozutil.subprocess_check_output(["/sbin/mkfs.msdos", "-C", 
                                           self.output_floppy, "1440"])
        oz.ozutil.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                           self.output_floppy, outname,
                                           "::AUTO_INST.CFG"])
        try:
            os.unlink(outname)
        except:
            pass
        if not os.path.exists(os.path.join(pathdir,
                                           "media")):
            url = urlparse.urlparse(self.tdl.repositories['install'].url)
            install_flags=  "automatic=method:%s,ser:%s,dir:%s,int:eth0,netw:dhcp" % (url.scheme, url.hostname, url.path)
        else:
            install_flags = "automatic=method:cdrom"
        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(pathdir, "isolinux", "isolinux.cfg")
        with open(isolinuxcfg, 'w') as f:
            f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel alt0/vmlinuz
  append initrd=alt0/all.rdz ramdisk_size=128000 root=/dev/ram3 acpi=ht vga=788 automatic=method:cdrom kickstart=floppy %s
""" % install_flags)

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")

        if os.path.exists(os.path.join(self.iso_contents, self.mageia_arch)):
            isolinuxdir = self.mageia_arch
        else:
            isolinuxdir = ""

        isolinuxbin = os.path.join(isolinuxdir, "isolinux/isolinux.bin")
        isolinuxboot = os.path.join(isolinuxdir, "isolinux/boot.cat")

        oz.ozutil.subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                           "-J", "-l", "-no-emul-boot",
                                           "-b", isolinuxbin,
                                           "-c", isolinuxboot,
                                           "-boot-load-size", "4",
                                           "-cache-inodes", "-boot-info-table",
                                           "-v", "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)
    def _do_install(self, timeout=None, force=False, reboots=0,
                    kernelfname=None, ramdiskfname=None, cmdline=None):
        fddev = self._InstallDev("floppy", self.output_floppy, "fda")
        return oz.Guest.CDGuest._do_install(self, timeout, force, reboots,
                                            kernelfname, ramdiskfname, cmdline,
                                            [fddev])
    def cleanup_install(self):
        try:
            os.unlink(self.output_floppy)
        except:
            pass
        return oz.Guest.CDGuest.cleanup_install(self)

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Mageia installs.
    """
    if tdl.update in ["4"]:
        return MageiaGuest(tdl, config, auto, output_disk, netdev, diskbus,
                           macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Mageia: 4"
