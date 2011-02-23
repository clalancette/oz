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

import subprocess
import re
import os
import shutil

import Guest
import ozutil
import OzException

class RedHatCDGuest(Guest.CDGuest):
    def __init__(self, name, distro, update, arch, installtype, nicmodel,
                 clockoffset, mousetype, diskbus, config):
        Guest.CDGuest.__init__(self, name, distro, update, arch, installtype,
                               nicmodel, clockoffset, mousetype, diskbus,
                               config)
        self.sshprivkey = os.path.join(self.icicle_tmp, 'id_rsa-icicle-gen')
        self.sshd_config = \
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

    def generate_iso(self):
        self.log.debug("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-T", "-J", "-V",
                                       "Custom", "-b", "isolinux/isolinux.bin",
                                       "-c", "isolinux/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-boot-info-table", "-v", "-v",
                                       "-o", self.output_iso,
                                       self.iso_contents])

    def get_default_runlevel(self, g_handle):
        runlevel = "3"
        if g_handle.exists('/etc/inittab'):
            lines = g_handle.cat('/etc/inittab').split("\n")
            for line in lines:
                if re.match('id:', line):
                    try:
                        runlevel = line.split(':')[1]
                    except:
                        pass
                    break

        return runlevel

    def get_service_runlevel_link(self, g_handle, service):
        runlevel = self.get_default_runlevel(g_handle)

        lines = g_handle.cat('/etc/init.d/' + service).split("\n")
        startlevel = "99"
        for line in lines:
            if re.match('# chkconfig:', line):
                try:
                    startlevel = line.split(':')[1].split()[1]
                except:
                    pass
                break

        return "/etc/rc.d/rc" + runlevel + ".d/S" + startlevel + service

    def image_ssh_teardown_step_1(self, g_handle):
        self.log.debug("Teardown step 1")
        # reset the authorized keys
        self.log.debug("Resetting authorized_keys")
        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.rm('/root/.ssh/authorized_keys')
        if g_handle.exists('/root/.ssh/authorized_keys.icicle'):
            g_handle.mv('/root/.ssh/authorized_keys.icicle',
                        '/root/.ssh/authorized_keys')

    def image_ssh_teardown_step_2(self, g_handle):
        self.log.debug("Teardown step 2")
        # remove custom sshd_config
        self.log.debug("Resetting sshd_config")
        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.rm('/etc/ssh/sshd_config')
        if g_handle.exists('/etc/ssh/sshd_config.icicle'):
            g_handle.mv('/etc/ssh/sshd_config.icicle', '/etc/ssh/sshd_config')

        # reset the service link
        self.log.debug("Resetting sshd service")
        startuplink = self.get_service_runlevel_link(g_handle, 'sshd')
        if g_handle.exists(startuplink):
            g_handle.rm(startuplink)
        if g_handle.exists(startuplink + ".icicle"):
            g_handle.mv(startuplink + ".icicle", startuplink)

    def image_ssh_teardown_step_3(self, g_handle):
        self.log.debug("Teardown step 3")
        # reset iptables
        self.log.debug("Resetting iptables rules")
        if g_handle.exists('/etc/sysconfig/iptables'):
            g_handle.rm('/etc/sysconfig/iptables')
        if g_handle.exists('/etc/sysconfig/iptables.icicle'):
            g_handle.mv('/etc/sysconfig/iptables.icicle',
                        '/etc/sysconfig/iptables')

    def image_ssh_teardown_step_4(self, g_handle):
        self.log.debug("Teardown step 4")
        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        if g_handle.exists('/etc/cron.d/announce'):
            g_handle.rm('/etc/cron.d/announce')

        # remove icicle-nc binary
        self.log.debug("Removing icicle-nc binary")
        if g_handle.exists('/root/icicle-nc'):
            g_handle.rm('/root/icicle-nc')

        # reset the service link
        self.log.debug("Resetting crond service")
        startuplink = self.get_service_runlevel_link(g_handle, 'crond')
        if g_handle.exists(startuplink):
            g_handle.rm(startuplink)
        if g_handle.exists(startuplink + ".icicle"):
            g_handle.mv(startuplink + ".icicle", startuplink)

    def image_ssh_teardown_step_5(self, g_handle):
        self.log.debug("Teardown step 5")
        if g_handle.exists('/etc/selinux/config'):
            g_handle.rm('/etc/selinux/config')

        if g_handle.exists('/etc/selinux/config.icicle'):
            g_handle.mv('/etc/selinux/config.icicle', '/etc/selinux/config')

    def collect_teardown(self, libvirt_xml):
        self.log.info("Collection Teardown")

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        try:
            self.image_ssh_teardown_step_1(g_handle)

            self.image_ssh_teardown_step_2(g_handle)

            self.image_ssh_teardown_step_3(g_handle)

            self.image_ssh_teardown_step_4(g_handle)

            self.image_ssh_teardown_step_5(g_handle)
        finally:
            self.guestfs_handle_cleanup(g_handle)
            shutil.rmtree(self.icicle_tmp)

    def image_ssh_setup_step_1(self, g_handle):
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if not g_handle.exists('/root/.ssh'):
            g_handle.mkdir('/root/.ssh')

        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.mv('/root/.ssh/authorized_keys',
                        '/root/.ssh/authorized_keys.icicle')

        pubname = self.sshprivkey + ".pub"
        if os.access(self.sshprivkey, os.F_OK):
            os.remove(self.sshprivkey)
        if os.access(pubname, os.F_OK):
            os.remove(pubname)
        subprocess.call(['ssh-keygen', '-q', '-t', 'rsa', '-b', '2048',
                         '-N', '', '-f', self.sshprivkey])

        g_handle.upload(pubname, '/root/.ssh/authorized_keys')

    def image_ssh_setup_step_2(self, g_handle):
        # part 2; check and setup sshd
        self.log.debug("Step 2: setup sshd")
        if not g_handle.exists('/etc/init.d/sshd') or not g_handle.exists('/usr/sbin/sshd'):
            raise OzException.OzException("ssh not installed on the image, cannot continue")

        startuplink = self.get_service_runlevel_link(g_handle, 'sshd')
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".icicle")
        g_handle.ln_sf('/etc/init.d/sshd', startuplink)

        sshd_config_file = self.icicle_tmp + "/sshd_config"
        f = open(sshd_config_file, 'w')
        f.write(self.sshd_config)
        f.close()

        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.mv('/etc/ssh/sshd_config', '/etc/ssh/sshd_config.icicle')
        g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
        os.unlink(sshd_config_file)

    def image_ssh_setup_step_3(self, g_handle):
        # part 3; open up iptables
        self.log.debug("Step 3: Open up the firewall")
        if g_handle.exists('/etc/sysconfig/iptables'):
            g_handle.mv('/etc/sysconfig/iptables', '/etc/sysconfig/iptables.icicle')
        # implicit else; if there is no iptables file, the firewall is open

    def image_ssh_setup_step_4(self, g_handle):
        # part 4; make sure the guest announces itself
        self.log.debug("Step 4: Guest announcement")
        if not g_handle.exists('/etc/init.d/crond') or not g_handle.exists('/usr/sbin/crond'):
            raise OzException.OzException("cron not installed on the image, cannot continue")

        iciclepath = ozutil.generate_full_guesttools_path('icicle-nc')
        g_handle.upload(iciclepath, '/root/icicle-nc')
        g_handle.chmod(0755, '/root/icicle-nc')

        announcefile = self.icicle_tmp + "/announce"
        f = open(announcefile, 'w')
        f.write('*/1 * * * * root /bin/bash -c "/root/icicle-nc ' + self.host_bridge_ip + ' ' + str(self.listen_port) + '"\n')
        f.close()

        g_handle.upload(announcefile, '/etc/cron.d/announce')

        startuplink = self.get_service_runlevel_link(g_handle, 'crond')
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".icicle")
        g_handle.ln_sf('/etc/init.d/crond', startuplink)

        os.unlink(announcefile)

    def image_ssh_setup_step_5(self, g_handle):
        # part 5; set SELinux to permissive mode so we don't have to deal with
        # incorrect contexts
        self.log.debug("Step 5: Set SELinux to permissive mode")
        if g_handle.exists('/etc/selinux/config'):
            g_handle.mv('/etc/selinux/config', '/etc/selinux/config.icicle')

        selinuxfile = self.icicle_tmp + "/selinux"
        f = open(selinuxfile, 'w')
        f.write("SELINUX=permissive\n")
        f.write("SELINUXTYPE=targeted\n")
        f.close()

        g_handle.upload(selinuxfile, "/etc/selinux/config")

        os.unlink(selinuxfile)

    def collect_setup(self, libvirt_xml):
        self.log.info("Collection Setup")

        self.mkdir_p(self.icicle_tmp)

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        # we have to do 5 things to make sure we can ssh into RHEL/Fedora:
        # 1)  Upload our ssh key
        # 2)  Make sure sshd is running on boot
        # 3)  Make sure that port 22 is open in the firewall
        # 4)  Make the guest announce itself to the host
        # 5)  Set SELinux to permissive mode

        try:
            try:
                self.image_ssh_setup_step_1(g_handle)

                try:
                    self.image_ssh_setup_step_2(g_handle)

                    try:
                        self.image_ssh_setup_step_3(g_handle)

                        try:
                            self.image_ssh_setup_step_4(g_handle)

                            try:
                                self.image_ssh_setup_step_5(g_handle)
                            except:
                                self.image_ssh_teardown_step_5(g_handle)
                                raise
                        except:
                            self.image_ssh_teardown_step_4(g_handle)
                            raise
                    except:
                        self.image_ssh_teardown_step_3(g_handle)
                        raise
                except:
                    self.image_ssh_teardown_step_2(g_handle)
                    raise
            except:
                self.image_ssh_teardown_step_1(g_handle)
                raise

        finally:
            self.guestfs_handle_cleanup(g_handle)

    def guest_execute_command(self, guestaddr, command):
        dummyknownhosts = os.path.join(self.icicle_tmp, "ssh_known_hosts")
        if os.access(dummyknownhosts, os.F_OK):
            os.unlink(dummyknownhosts)
        return Guest.subprocess_check_output(["ssh", "-i", self.sshprivkey,
                                              "-o", "StrictHostKeyChecking=no",
                                              "-o", "ConnectTimeout=5",
                                              "-o", "UserKnownHostsFile=" + dummyknownhosts,
                                              "root@" + guestaddr, command])

    def do_icicle(self, guestaddr):
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             'rpm -qa')

        return self.output_icicle_xml(stdout.split("\n"))

    def generate_icicle(self, libvirt_xml):
        self.log.info("Generating ICICLE")

        self.collect_setup(libvirt_xml)

        icicle_output = ''
        libvirt_dom = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            try:
                guestaddr = None
                guestaddr = self.wait_for_guest_boot()
                icicle_output = self.do_icicle(guestaddr)
            finally:
                self.shutdown_guest(guestaddr, libvirt_dom)

        finally:
            self.collect_teardown(libvirt_xml)

        return icicle_output

    def guest_live_upload(self, guestaddr, file_to_upload, destination):
        self.guest_execute_command(guestaddr, "mkdir -p " + os.path.dirname(destination))

        dummyknownhosts = os.path.join(self.icicle_tmp, "ssh_known_hosts")
        if os.access(dummyknownhosts, os.F_OK):
            os.unlink(dummyknownhosts)
        return Guest.subprocess_check_output(["scp", "-i", self.sshprivkey,
                                              "-o", "StrictHostKeyChecking=no",
                                              "-o", "ConnectTimeout=5",
                                              "-o", "UserKnownHostsFile=" + dummyknownhosts,
                                              file_to_upload,
                                              "root@" + guestaddr + ":" + destination])

    def customize_files(self, guestaddr):
        self.log.info("Uploading custom files")
        for name,content in self.tdl.files.items():
            localname = os.path.join(self.icicle_tmp, "file")
            f = open(localname, 'w')
            f.write(content)
            f.close()
            self.guest_live_upload(guestaddr, localname, name)
            os.unlink(localname)

    def shutdown_guest(self, guestaddr, libvirt_dom):
        if guestaddr is not None:
            try:
                self.guest_execute_command(guestaddr, 'shutdown -h now')
                if not self.wait_for_guest_shutdown(libvirt_dom):
                    self.log.warn("Guest did not shutdown in time, going to kill")
                else:
                    libvirt_dom = None
            except:
                self.log.warn("Failed shutting down guest, forcibly killing")

        if libvirt_dom is not None:
            libvirt_dom.destroy()

    def generate_install_media(self, force_download=False):
        self.log.info("Generating install media")

        if not force_download and os.access(self.modified_iso_cache, os.F_OK):
            self.log.info("Using cached modified media")
            shutil.copyfile(self.modified_iso_cache, self.output_iso)
            return

        fetchurl = self.url
        if self.tdl.installtype == 'url':
            fetchurl += "/images/boot.iso"

        self.get_original_iso(fetchurl, force_download)
        self.copy_iso()
        try:
            if hasattr(self, 'check_dvd') and self.tdl.installtype == 'iso':
                self.check_dvd()
            self.modify_iso()
            self.generate_iso()
            if self.cache_modified_media:
                self.log.info("Caching modified media for future use")
                shutil.copyfile(self.output_iso, self.modified_iso_cache)
        finally:
            self.cleanup_iso()

class RedHatCDYumGuest(RedHatCDGuest):
    def customize_repos(self, guestaddr):
        self.log.debug("Installing additional repository files")
        for repo in self.tdl.repositories.values():
            filename = repo.name + ".repo"
            localname = os.path.join(self.icicle_tmp, filename)
            f = open(localname, 'w')
            f.write("[%s]\n" % repo.name)
            f.write("name=%s\n" % repo.name)
            f.write("baseurl=%s\n" % repo.url)
            f.write("enabled=1\n")
            if repo.signed:
                f.write("gpgcheck=1\n")
            else:
                f.write("gpgcheck=0\n")
            f.close()

            self.guest_live_upload(guestaddr, localname,
                                   "/etc/yum.repos.d/" + filename)

            os.unlink(localname)

    def do_customize(self, guestaddr):
        self.customize_repos(guestaddr)

        self.log.debug("Installing custom packages")
        packstr = ''
        for package in self.tdl.packages:
            packstr += package.name + ' '

        if packstr != '':
            self.guest_execute_command(guestaddr,
                                       'yum -y install %s' % (packstr))

        self.customize_files(guestaddr)

        self.log.debug("Syncing")
        self.guest_execute_command(guestaddr, 'sync')

    def customize(self, libvirt_xml):
        self.log.info("Customizing image")

        if not self.tdl.packages and not self.tdl.files:
            self.log.info("No additional packages or files to install, skipping customization")
            return

        self.collect_setup(libvirt_xml)

        libvirt_dom = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            try:
                guestaddr = None
                guestaddr = self.wait_for_guest_boot()

                self.do_customize(guestaddr)
            finally:
                self.shutdown_guest(guestaddr, libvirt_dom)
        finally:
            self.collect_teardown(libvirt_xml)

    def customize_and_generate_icicle(self, libvirt_xml):
        self.log.info("Customizing and generating ICICLE")

        self.collect_setup(libvirt_xml)

        libvirt_dom = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            try:
                guestaddr = self.wait_for_guest_boot()

                if self.tdl.packages or self.tdl.files:
                    self.do_customize(guestaddr)

                icicle = self.do_icicle(guestaddr)
            finally:
                self.shutdown_guest(guestaddr, libvirt_dom)
        finally:
            self.collect_teardown(libvirt_xml)

        return icicle
