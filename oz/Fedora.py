# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import shutil
import re

import Guest
import ozutil
import RedHat

class FedoraGuest(RedHat.RedHatCDGuest):
    def __init__(self, tdl, config, nicmodel, haverepo, diskbus, brokenisomethod):
        self.tdl = tdl
        self.ks_file = ozutil.generate_full_auto_path("fedora-" + self.tdl.update + "-jeos.ks")
        self.haverepo = haverepo
        self.brokenisomethod = brokenisomethod

        if self.tdl.installtype == 'url':
            self.url = self.tdl.url
            ozutil.deny_localhost(self.url)
        elif self.tdl.installtype == 'iso':
            self.url = self.tdl.iso
        else:
            raise Exception, "Fedora installs must be done via url or iso"

        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

        RedHat.RedHatCDGuest.__init__(self, "Fedora", self.tdl.update,
                                      self.tdl.arch, self.tdl.installtype,
                                      nicmodel, None, None, diskbus, config)

    def modify_iso(self):
        self.log.debug("Putting the kickstart in place")

        shutil.copy(self.ks_file, self.iso_contents + "/ks.cfg")

        self.log.debug("Modifying the boot options")
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            elif re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel vmlinuz\n")
        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg"
        if self.tdl.installtype == "url":
            if self.haverepo:
                initrdline += " repo="
            else:
                initrdline += " method="
            initrdline += self.url + "\n"
        else:
            # if the installtype is iso, then due to a bug in anaconda we leave
            # out the method completely
            if not self.brokenisomethod:
                initrdline += " method=cdrom:/dev/cdrom"
            initrdline += "\n"
        lines.append(initrdline)

        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "w")
        f.writelines(lines)
        f.close()

    def generate_install_media(self, force_download):
        self.log.info("Generating install media")
        fetchurl = self.url
        if self.tdl.installtype == 'url':
            fetchurl += "/images/boot.iso"
        self.get_original_iso(fetchurl, force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_iso()
        self.cleanup_iso()

    def customize(self, libvirt_xml):
        self.log.info("Customizing image")

        keyfile = self.icicle_tmp + '/id_rsa-icicle-gen'

        if not self.tdl.packages:
            self.log.info("No additional packages to install, skipping customization")
            return

        self.collect_setup(libvirt_xml)

        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            guestaddr = self.wait_for_guest_boot()

            try:
                packstr = ''
                for package in self.packages:
                    packstr += package + ' '

                output = RedHat.guest_execute_command(guestaddr, keyfile,
                                                      'yum -y install %s' % (packstr))

                stdout = output[0]
                stderr = output[1]
                returncode = output[2]
                if returncode != 0:
                    raise OzException("Failed to execute guest command 'yum -y install %s': %s" % (packstr, stderr))

            finally:
                RedHat.guest_execute_command(guestaddr, keyfile,
                                             'shutdown -h now')

                if self.wait_for_guest_shutdown(libvirt_dom):
                    libvirt_dom = None
        finally:
            if libvirt_dom is not None:
                libvirt_dom.destroy()
            self.collect_teardown(libvirt_xml)

def get_class(tdl, config):
    if tdl.update in ["10", "11", "12", "13", "14"]:
        return FedoraGuest(tdl, config, "virtio", True, "virtio", True)
    if tdl.update in ["7", "8", "9"]:
        return FedoraGuest(tdl, config, "rtl8139", False, None, False)
    raise Guest.OzException("Unsupported Fedora update " + tdl.update)
