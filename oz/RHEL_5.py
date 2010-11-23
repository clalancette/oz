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
import subprocess
import re
import ozutil
import os
import RedHat

class RHEL5Guest(Guest.CDGuest):
    def __init__(self, tdl, config, nicmodel, diskbus):
        update = tdl.update()
        arch = tdl.arch()
        key = tdl.key()
        self.ks_file = ozutil.generate_full_auto_path("rhel-5-jeos.ks")
        self.installtype = tdl.installtype()

        if self.installtype == 'url':
            self.url = tdl.url()
        elif self.installtype == 'iso':
            self.url = tdl.iso()
        else:
            raise Exception, "RHEL-5 installs must be done via url or iso"

        self.url = ozutil.check_url(self.url)

        if self.installtype == 'url':
            ozutil.deny_localhost(self.url)
        # FIXME: if doing an ISO install, we have to check that the ISO passed
        # in is the DVD, not the CD (since we can't change disks midway)

        self.output_services = tdl.services()

        Guest.CDGuest.__init__(self, "RHEL-5", update, arch, nicmodel, None,
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
        initrdline = "  append initrd=initrd.img ks=cdrom:/ks.cfg method="
        if self.installtype == "url":
            initrdline += self.url + "\n"
        else:
            initrdline += "cdrom:/dev/cdrom\n"
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

        # we have to do 3 things to make sure we can ssh into Fedora 13:
        # 1)  Upload our ssh key
        # 2)  Make sure sshd is running on boot
        # 3)  Make sure that port 22 is open in the firewall
        # 4)  Make the guest announce itself to the host

        runlevel = RedHat.get_default_runlevel(g_handle)

        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if not g_handle.exists('/root/.ssh'):
            g_handle.mkdir('/root/.ssh')

        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.mv('/root/.ssh/authorized_keys',
                      '/root/.ssh/authorized_keys.cdl')

        if not os.access(self.cdl_tmp, os.F_OK):
            os.makedirs(self.cdl_tmp)

        privname = self.cdl_tmp + '/id_rsa-cdl-gen'
        pubname = self.cdl_tmp + '/id_rsa-cdl-gen.pub'
        if os.access(privname, os.F_OK):
            os.remove(privname)
        if os.access(pubname, os.F_OK):
            os.remove(pubname)
        subprocess.call(['ssh-keygen', '-q', '-t', 'rsa', '-b', '2048',
                         '-N', '', '-f', privname])

        g_handle.upload(pubname, '/root/.ssh/authorized_keys')

        # part 2; check and setup sshd
        self.log.debug("Step 2: setup sshd")
        if not g_handle.exists('/etc/init.d/sshd') or not g_handle.exists('/usr/sbin/sshd'):
            raise Exception, "ssh not installed on the image, cannot continue"

        startuplink = RedHat.get_service_runlevel_link(g_handle, runlevel,
                                                       'sshd')
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".cdl")
        g_handle.ln_sf('/etc/init.d/sshd', startuplink)

        sshd_config = \
"""SyslogFacility AUTHPRIV
PasswordAuthentication yes
ChallengeResponseAuthentication no
GSSAPIAuthentication yes
GSSAPICleanupCredentials yes
UsePAM yes
AcceptEnv LANG LC_CTYPE LC_NUMERIC LC_TIME LC_COLLATE LC_MONETARY LC_MESSAGES
AcceptEnv LC_PAPER LC_NAME LC_ADDRESS LC_TELEPHONE LC_MEASUREMENT
AcceptEnv LC_IDENTIFICATION LC_ALL LANGUAGE
AcceptEnv XMODIFIERS
X11Forwarding yes
Subsystem	sftp	/usr/libexec/openssh/sftp-server
"""

        sshd_config_file = self.cdl_tmp + "/sshd_config"
        f = open(sshd_config_file, 'w')
        f.write(sshd_config)
        f.close()

        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.mv('/etc/ssh/sshd_config', '/etc/ssh/sshd_config.cdl')
        g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
        os.unlink(sshd_config_file)

        # part 3; open up iptables
        self.log.debug("Step 3: Open up the firewall")
        if g_handle.exists('/etc/sysconfig/iptables'):
            g_handle.mv('/etc/sysconfig/iptables', '/etc/sysconfig/iptables.cdl')
        # implicit else; if there is no iptables file, the firewall is open

        # part 4; make sure the guest announces itself
        self.log.debug("Step 4: Guest announcement")
        if not g_handle.exists('/etc/init.d/crond') or not g_handle.exists('/usr/sbin/crond'):
            raise Exception, "cron not installed on the image, cannot continue"

        cdlpath = ozutil.generate_full_guesttools_path('cdl-nc')
        g_handle.upload(cdlpath, '/root/cdl-nc')
        g_handle.chmod(0755, '/root/cdl-nc')

        announcefile = self.cdl_tmp + "/announce"
        f = open(announcefile, 'w')
        f.write('*/1 * * * * root /bin/bash -c "/root/cdl-nc ' + self.host_bridge_ip + ' ' + str(self.listen_port) + '"\n')
        f.close()

        g_handle.upload(announcefile, '/etc/cron.d/announce')

        startuplink = RedHat.get_service_runlevel_link(g_handle, runlevel,
                                                       'crond')
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".cdl")
        g_handle.ln_sf('/etc/init.d/crond', startuplink)

        os.unlink(announcefile)
        self.guestfs_handle_cleanup(g_handle)

    def collect_teardown(self, libvirt_xml):
        self.log.info("CDL Collection Teardown")

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        # reset the authorized keys
        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.rm('/root/.ssh/authorized_keys')
        if g_handle.exists('/root/.ssh/authorized_keys.cdl'):
            g_handle.mv('/root/.ssh/authorized_keys.cdl',
                      '/root/.ssh/authorized_keys')

        # reset iptables
        if g_handle.exists('/etc/sysconfig/iptables'):
            g_handle.rm('/etc/sysconfig/iptables')
        if g_handle.exists('/etc/sysconfig/iptables.cdl'):
            g_handle.mv('/etc/sysconfig/iptables')

        # remove announce cronjob
        if g_handle.exists('/etc/cron.d/announce'):
            g_handle.rm('/etc/cron.d/announce')

        # remove cdl-nc binary
        if g_handle.exists('/root/cdl-nc'):
            g_handle.rm('/root/cdl-nc')

        # remove custom sshd_config
        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.rm('/etc/ssh/sshd_config')
        if g_handle.exists('/etc/ssh/sshd_config.cdl'):
            g_handle.mv('/etc/ssh/sshd_config.cdl', '/etc/ssh/sshd_config')

        # reset the service links
        runlevel = RedHat.get_default_runlevel(g_handle)

        for service in ["sshd", "crond"]:
            startuplink = RedHat.get_service_runlevel_link(g_handle, runlevel,
                                                           service)
            if g_handle.exists(startuplink):
                g_handle.rm(startuplink)
            if g_handle.exists(startuplink + ".cdl"):
                g_handle.mv(startuplink + ".cdl", startuplink)

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

def get_class(tdl, config):
    update = tdl.update()
    if update == "GOLD" or update == "U1" or update == "U2" or update == "U3":
        return RHEL5Guest(tdl, config, "rtl8139", None)
    if update == "U4" or update == "U5":
        return RHEL5Guest(tdl, config, "virtio", "virtio")
    raise Exception, "Unsupported RHEL-5 update " + update
