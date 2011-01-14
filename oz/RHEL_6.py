# Copyright (C) 2010  Chris Lalancette <clalance@redhat.com>

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

import Guest
import shutil
import re
import ozutil
import RedHat

class RHEL6Guest(RedHat.RedHatCDGuest):
    def __init__(self, tdl, config):
        self.tdl = tdl
        self.ks_file = ozutil.generate_full_auto_path("rhel-6-jeos.ks")

        if self.tdl.installtype == 'url':
            self.url = self.tdl.url
            ozutil.deny_localhost(self.url)
        elif self.tdl.installtype == 'iso':
            self.url = self.tdl.iso
        else:
            raise Guest.OzException("RHEL-6 installs must be done via url or iso")

        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

        Guest.CDGuest.__init__(self, "RHEL-6", self.tdl.update, self.tdl.arch,
                               self.tdl.installtype, "virtio", None, None,
                               "virtio", config)

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
            initrdline += " repo=" + self.url + "\n"
        else:
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
        self.collect_setup(libvirt_xml)

        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            guestaddr = self.wait_for_guest_boot()

            packstr = ''
            for package in self.tdl.packages:
                packstr += package + ' '

            # FIXME: for this to succeed, we might actually have to upload
            # an /etc/yum.repos.d/*.repo
            output = RedHat.guest_execute_command(guestaddr,
                                                  self.icicle_tmp + '/id_rsa-icicle-gen',
                                                  'yum -y install %s' % (packstr))
            stdout = output[0]
            stderr = output[1]
            returncode = output[2]
            if returncode != 0:
                raise Guest.OzException("Failed to execute guest command 'yum -y install %s': %s" % (packstr, stderr))

            RedHat.guest_execute_command(guestaddr,
                                         self.icicle_tmp + '/id_rsa-icicle-gen',
                                         'shutdown -h now')

            if self.wait_for_guest_shutdown(libvirt_dom):
                libvirt_dom = None
        finally:
            if libvirt_dom is not None:
                libvirt_dom.destroy()
            self.collect_teardown(libvirt_xml)

def get_class(tdl, config):
    if tdl.update in ["0"]:
        return RHEL6Guest(tdl, config)
    raise Guest.OzException("Unsupported RHEL-6 update " + tdl.update)
