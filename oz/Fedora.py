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

class FedoraGuest(Guest.CDGuest):
    def __init__(self, tdl, config, nicmodel, haverepo, diskbus, brokenisomethod):
        update = tdl.update()
        arch = tdl.arch()
        self.ks_file = ozutil.generate_full_auto_path("fedora-" + update + "-jeos.ks")
        self.haverepo = haverepo
        self.brokenisomethod = brokenisomethod
        self.installtype = tdl.installtype()

        if self.installtype == 'url':
            self.url = tdl.url()
        elif self.installtype == 'iso':
            self.url = tdl.iso()
        else:
            raise Exception, "Fedora installs must be done via url or iso"

        if self.installtype == 'url':
            ozutil.deny_localhost(self.url)
        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

        self.output_services = tdl.services()
        self.packages = tdl.packages()

        Guest.CDGuest.__init__(self, "Fedora", update, arch, nicmodel, None,
                               None, diskbus, config)

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
        if self.installtype == "url":
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

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        RedHat.generate_iso(self.output_iso, self.iso_contents)

    def generate_install_media(self, force_download):
        self.log.info("Generating install media")
        fetchurl = self.url
        if self.installtype == 'url':
            fetchurl += "/images/boot.iso"
        self.get_original_iso(fetchurl, force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

    def collect_setup(self, libvirt_xml):
        self.log.info("CDL Collection Setup")

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        try:
            RedHat.image_ssh_setup(self.log, g_handle, self.cdl_tmp,
                                   self.host_bridge_ip, self.listen_port,
                                   libvirt_xml)
        finally:
            self.guestfs_handle_cleanup(g_handle)

    def collect_teardown(self, libvirt_xml):
        self.log.info("CDL Collection Teardown")

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        try:
            RedHat.image_ssh_teardown(self.log, g_handle)
        finally:
            self.guestfs_handle_cleanup(g_handle)

    def generate_cdl(self, libvirt_xml):
        self.log.info("Generating CDL")

        self.collect_setup(libvirt_xml)

        output = ''
        try:
            self.libvirt_dom = self.libvirt_conn.defineXML(libvirt_xml)
            self.libvirt_dom.create()

            guestaddr = self.wait_for_guest_boot()

            data = RedHat.guest_execute_command(guestaddr,
                                                self.cdl_tmp + '/id_rsa-cdl-gen',
                                                'rpm -qa')

            # FIXME: what if the output is blank?

            output = self.output_cdl_xml(data[0].split("\n"), self.output_services)

            # FIXME: should we try to do a graceful shutdown here?  At the very
            # least we should do a sync
        finally:
            if self.libvirt_dom is not None:
                self.libvirt_dom.destroy()
            self.collect_teardown(libvirt_xml)

        return output

    def customize(self, libvirt_xml):
        self.log.info("Customizing image")
        self.collect_setup(libvirt_xml)

        try:
            self.libvirt_dom = self.libvirt_conn.defineXML(libvirt_xml)
            self.libvirt_dom.create()

            guestaddr = self.wait_for_guest_boot()

            for package in self.packages:
                data = RedHat.guest_execute_command(guestaddr,
                                                    self.cdl_tmp + '/id_rsa-cdl-gen',
                                                    'yum -y install %s' % (package))
                # FIXME: what if the output is blank?

            data = RedHat.guest_execute_command(guestaddr,
                                                self.cdl_tmp + '/id_rsa-cdl-gen',
                                                'rpm -qa')

            # FIXME: what if the output is blank?

            output = self.output_cdl_xml(data[0].split("\n"), self.output_services)
            # FIXME: should we try to do a graceful shutdown here?  At the very
            # least we should do a sync
        finally:
            if self.libvirt_dom is not None:
                self.libvirt_dom.destroy()
            self.collect_teardown(libvirt_xml)

        return output

def get_class(tdl, config):
    update = tdl.update()
    if update == "10" or update == "11" or update == "12" or update == "13" or update == "14":
        return FedoraGuest(tdl, config, "virtio", True, "virtio", True)
    if update == "7" or update == "8" or update == "9":
        return FedoraGuest(tdl, config, "rtl8139", False, None, False)
    raise Exception, "Unsupported Fedora update " + update
