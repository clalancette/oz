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
import libvirt

class FedoraGuest(Guest.CDGuest):
    def __init__(self, update, arch, url, ks, nicmodel, haverepo, diskbus):
        Guest.CDGuest.__init__(self, "Fedora", update, arch, nicmodel, None, None, diskbus)
        self.ks_file = ks
        self.url = url
        self.haverepo = haverepo

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
        if self.haverepo:
            lines.append("  append initrd=initrd.img ks=cdrom:/ks.cfg repo=" + self.url + "\n")
        else:
            lines.append("  append initrd=initrd.img ks=cdrom:/ks.cfg method=" + self.url + "\n")

        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "w")
        f.writelines(lines)
        f.close()

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-T", "-J", "-V",
                                       "Custom", "-b", "isolinux/isolinux.bin",
                                       "-c", "isolinux/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-boot-info-table", "-v", "-v",
                                       "-o", self.output_iso, self.iso_contents])

    def generate_install_media(self):
        self.log.info("Generating install media")
        self.get_original_iso(self.url + "/images/boot.iso")
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

    def get_default_runlevel(self):
        runlevel = "3"
        if self.g.exists('/etc/inittab'):
            lines = self.g.cat('/etc/inittab').split("\n")
            for line in lines:
                if re.match('id:', line):
                    # FIXME: this parsing is a bit iffy
                    runlevel = line.split(':')[1]
                    break

        return runlevel

    def get_service_runlevel_link(self, runlevel, service):
        lines = self.g.cat('/etc/init.d/' + service).split("\n")
        startlevel = "99"
        for line in lines:
            if re.match('# chkconfig:', line):
                # FIXME: this parsing could get ugly fast
                startlevel = line.split(':')[1].split()[1]
                break

        return "/etc/rc.d/rc" + runlevel + ".d/S" + startlevel + service

    def collect_setup(self, diskimage):
        self.log.info("CDL Collection Setup")

        self.guestfs_handle_setup(diskimage)

        # we have to do 3 things to make sure we can ssh into Fedora 13:
        # 1)  Upload our ssh key
        # 2)  Make sure sshd is running on boot
        # 3)  Make sure that port 22 is open in the firewall
        # 4)  Make the guest announce itself to the host

        runlevel = self.get_default_runlevel()

        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if not self.g.exists('/root/.ssh'):
            self.g.mkdir('/root/.ssh')

        if self.g.exists('/root/.ssh/authorized_keys'):
            self.g.mv('/root/.ssh/authorized_keys',
                      '/root/.ssh/authorized_keys.cdl')

        if not os.access(self.cdl_tmp, os.F_OK):
            os.makedirs(self.cdl_tmp)

        # FIXME: if we have two oz processes running at the same time, on
        # the same named guest, they will collide here
        privname = self.cdl_tmp + '/id_rsa-cdl-gen'
        pubname = self.cdl_tmp + '/id_rsa-cdl-gen.pub'
        if os.access(privname, os.F_OK):
            os.remove(privname)
        if os.access(pubname, os.F_OK):
            os.remove(pubname)
        subprocess.call(['ssh-keygen', '-q', '-t', 'rsa', '-b', '2048', '-N', '', '-f', privname])

        self.g.upload(pubname, '/root/.ssh/authorized_keys')

        # part 2; check and setup sshd
        self.log.debug("Step 2: setup sshd")
        if not self.g.exists('/etc/init.d/sshd') or not self.g.exists('/usr/sbin/sshd'):
            raise Exception, "ssh not installed on the image, cannot continue"

        startuplink = self.get_service_runlevel_link(runlevel, 'sshd')
        if self.g.exists(startuplink):
            self.g.mv(startuplink, startuplink + ".cdl")
        self.g.ln_sf('/etc/init.d/sshd', startuplink)

        # part 3; open up iptables
        self.log.debug("Step 3: Open up the firewall")
        if self.g.exists('/etc/sysconfig/iptables'):
            self.g.mv('/etc/sysconfig/iptables', '/etc/sysconfig/iptables.cdl')
        # implicit else; if there is no iptables file, the firewall is open

        # part 4; make sure the guest announces itself
        self.log.debug("Step 4: Guest announcement")
        if not self.g.exists('/etc/init.d/crond') or not self.g.exists('/usr/sbin/crond'):
            raise Exception, "cron not installed on the image, cannot continue"

        cdlpath = ozutil.generate_full_guesttools_path('cdl-nc')
        self.g.upload(cdlpath, '/root/cdl-nc')
        self.g.chmod(0755, '/root/cdl-nc')

        announcefile = self.cdl_tmp + "/announce"
        f = open(announcefile, 'w')
        f.write('*/1 * * * * root /bin/bash -c "/root/cdl-nc ' + self.host_bridge_ip + ' ' + str(self.listen_port) + '"\n')
        f.close()

        self.g.upload(announcefile, '/etc/cron.d/announce')

        startuplink = self.get_service_runlevel_link(runlevel, 'crond')
        if self.g.exists(startuplink):
            self.g.mv(startuplink, startuplink + ".cdl")
        self.g.ln_sf('/etc/init.d/crond', startuplink)

        os.unlink(announcefile)
        self.guestfs_handle_cleanup()

    def collect_teardown(self, diskimage):
        self.log.info("CDL Collection Teardown")

        self.guestfs_handle_setup(diskimage)

        # reset the authorized keys
        if self.g.exists('/root/.ssh/authorized_keys'):
            self.g.rm('/root/.ssh/authorized_keys')
        if self.g.exists('/root/.ssh/authorized_keys.cdl'):
            self.g.mv('/root/.ssh/authorized_keys.cdl',
                      '/root/.ssh/authorized_keys')

        # reset iptables
        if self.g.exists('/etc/sysconfig/iptables'):
            self.g.rm('/etc/sysconfig/iptables')
        if self.g.exists('/etc/sysconfig/iptables.cdl'):
            self.g.mv('/etc/sysconfig/iptables')

        # remove announce cronjob
        if self.g.exists('/etc/cron.d/announce'):
            self.g.rm('/etc/cron.d/announce')

        # remove cdl-nc binary
        if self.g.exists('/root/cdl-nc'):
            self.g.rm('/root/cdl-nc')

        # reset the service links
        runlevel = self.get_default_runlevel()

        for service in ["sshd", "crond"]:
            startuplink = self.get_service_runlevel_link(runlevel, service)
            if self.g.exists(startuplink):
                self.g.rm(startuplink)
            if self.g.exists(startuplink + ".cdl"):
                self.g.mv(startuplink + ".cdl", startuplink)

        self.guestfs_handle_cleanup()

    def generate_cdl(self, diskimage):
        self.log.info("Generating CDL")

        # we undefine up-front because we are going to generate our own
        # libvirt XML below.  It should be safe to undefine here
        # FIXME: this is almost an exact copy of Guest.cleanup_old_guest
        def handler(ctxt, err):
            pass
        libvirt.registerErrorHandler(handler, 'context')
        self.log.info("Cleaning up old guest named %s" % (self.name))
        try:
            dom = self.libvirt_conn.lookupByName(self.name)
            try:
                dom.destroy()
            except:
                pass
            dom.undefine()
        except:
            pass
        libvirt.registerErrorHandler(None, None)

        self.collect_setup(diskimage)

        self.generate_define_xml("hd")
        self.libvirt_dom.create()

        guestaddr = self.wait_for_guest_boot()

        data = subprocess.Popen(["ssh", "-i", self.cdl_tmp + '/id_rsa-cdl-gen',
                                 "-o", "StrictHostKeyChecking=no",
                                 "-o", "ConnectTimeout=5", guestaddr,
                                 'rpm -qa'], stdout=subprocess.PIPE).communicate()

        # FIXME: what if the output is blank?

        output = self.output_cdl_xml(data[0].split("\n"))

        # FIXME: should we try to do a graceful shutdown here?
        self.libvirt_dom.destroy()

        self.collect_teardown(diskimage)

        return output

def get_class(idl):
    update = idl.update()
    arch = idl.arch()
    ks = ozutil.generate_full_auto_path("fedora-" + update + "-jeos.ks")

    if idl.installtype() != 'url':
        raise Exception, "Fedora installs must be done via url"

    url = ozutil.check_url(idl.url())

    if update == "10" or update == "11" or update == "12" or update == "13":
        return FedoraGuest(update, arch, url, ks, "virtio", True, "virtio")
    if update == "9" or update == "8" or update == "7":
        return FedoraGuest(update, arch, url, ks, "rtl8139", False, None)
    raise Exception, "Unsupported Fedora update " + update
