# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

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

import re
import shutil
import os

import Guest
import ozutil
import OzException

class OpenSUSEGuest(Guest.CDGuest):
    def __init__(self, tdl, config, auto):
        Guest.CDGuest.__init__(self, tdl.name, tdl.distro, tdl.update, tdl.arch,
                               tdl.installtype, "virtio", None, None, "virtio",
                               config)

        self.tdl = tdl

        self.autoyast = auto
        if self.autoyast is None:
            self.autoyast = ozutil.generate_full_auto_path("opensuse-" + self.tdl.update + "-jeos.xml")

        self.url = self.check_url(self.tdl, iso=True, url=False)

        self.sshprivkey = os.path.join('/etc', 'oz', 'id_rsa-icicle-gen')

    def modify_iso(self):
        self.log.debug("Putting the autoyast in place")
        shutil.copy(self.autoyast, os.path.join(self.iso_contents,
                                                "autoinst.xml"))

        self.log.debug("Modifying the boot options")
        isolinux_cfg = os.path.join(self.iso_contents, "boot", self.tdl.arch,
                                    "loader", "isolinux.cfg")
        f = open(isolinux_cfg, "r")
        lines = f.readlines()
        f.close()
        for index, line in enumerate(lines):
            if re.match("timeout", line):
                lines[index] = "timeout 1\n"
            elif re.match("default", line):
                lines[index] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel linux\n")
        lines.append("  append initrd=initrd splash=silent instmode=cd autoyast=default")

        f = open(isolinux_cfg, "w")
        f.writelines(lines)
        f.close()

    def generate_new_iso(self):
        self.log.info("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-J", "-V", "Custom",
                                       "-l", "-b",
                                       "boot/" + self.tdl.arch + "/loader/isolinux.bin",
                                       "-c", "boot/" + self.tdl.arch + "/loader/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-boot-info-table", "-graft-points",
                                       "-iso-level", "4", "-pad",
                                       "-allow-leading-dots",
                                       "-o", self.output_iso,
                                       self.iso_contents])

    def generate_install_media(self, force_download=False):
        self.log.info("Generating install media")

        if not force_download and os.access(self.modified_iso_cache, os.F_OK):
            self.log.info("Using cached modified media")
            shutil.copyfile(self.modified_iso_cache, self.output_iso)
            return

        self.get_original_iso(self.url, force_download)
        self.copy_iso()
        try:
            self.modify_iso()
            self.generate_new_iso()
            if self.cache_modified_media:
                self.log.info("Caching modified media for future use")
                shutil.copyfile(self.output_iso, self.modified_iso_cache)
        finally:
            self.cleanup_iso()

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

    def guest_execute_command(self, guestaddr, command):
        # ServerAliveInterval protects against NAT firewall timeouts
        # on long-running commands with no output
        return Guest.subprocess_check_output(["ssh", "-i", self.sshprivkey,
                                              "-o", "ServerAliveInterval=30",
                                              "-o", "StrictHostKeyChecking=no",
                                              "-o", "ConnectTimeout=5",
                                              "-o", "UserKnownHostsFile=/dev/null",
                                              "root@" + guestaddr, command])

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
        runlevel = self.get_default_runlevel(g_handle)
        startuplink = '/etc/rc.d/rc' + runlevel + '.d/S04sshd'
        if g_handle.exists(startuplink):
            g_handle.rm(startuplink)
        if g_handle.exists(startuplink + ".icicle"):
            g_handle.mv(startuplink + ".icicle", startuplink)

    def image_ssh_teardown_step_3(self, g_handle):
        self.log.debug("Teardown step 3")
        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        if g_handle.exists('/etc/cron.d/announce'):
            g_handle.rm('/etc/cron.d/announce')

        # remove icicle-nc binary
        self.log.debug("Removing icicle-nc binary")
        if g_handle.exists('/root/icicle-nc'):
            g_handle.rm('/root/icicle-nc')

        # reset the service link
        self.log.debug("Resetting cron service")
        runlevel = self.get_default_runlevel(g_handle)
        startuplink = '/etc/rc.d/rc' + runlevel + ".d/S06cron"
        if g_handle.exists(startuplink):
            g_handle.rm(startuplink)
        if g_handle.exists(startuplink + ".icicle"):
            g_handle.mv(startuplink + ".icicle", startuplink)

    def collect_teardown(self, libvirt_xml):
        self.log.info("Collection Teardown")

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        try:
            self.image_ssh_teardown_step_1(g_handle)

            self.image_ssh_teardown_step_2(g_handle)

            self.image_ssh_teardown_step_3(g_handle)
        finally:
            self.guestfs_handle_cleanup(g_handle)
            shutil.rmtree(self.icicle_tmp)

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
                stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                                     'rpm -qa')

                icicle_output = self.output_icicle_xml(stdout.split("\n"),
                                                       self.tdl.description)
            finally:
                self.shutdown_guest(guestaddr, libvirt_dom)

        finally:
            self.collect_teardown(libvirt_xml)

        return icicle_output

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

    def image_ssh_setup_step_1(self, g_handle):
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if not g_handle.exists('/root/.ssh'):
            g_handle.mkdir('/root/.ssh')

        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.mv('/root/.ssh/authorized_keys',
                        '/root/.ssh/authorized_keys.icicle')

        self.generate_openssh_key(self.sshprivkey)

        g_handle.upload(self.sshprivkey + ".pub", '/root/.ssh/authorized_keys')

    def image_ssh_setup_step_2(self, g_handle):
        # part 2; check and setup sshd
        self.log.debug("Step 2: setup sshd")
        if not g_handle.exists('/etc/init.d/sshd') or not g_handle.exists('/usr/sbin/sshd'):
            raise OzException.OzException("ssh not installed on the image, cannot continue")

        runlevel = self.get_default_runlevel(g_handle)
        startuplink = '/etc/rc.d/rc' + runlevel + '.d/S04sshd'
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".icicle")
        g_handle.ln_sf('/etc/init.d/sshd', startuplink)

        sshd_config = \
"""PasswordAuthentication no
UsePAM yes

X11Forwarding yes

Subsystem	sftp	/usr/lib64/ssh/sftp-server

AcceptEnv LANG LC_CTYPE LC_NUMERIC LC_TIME LC_COLLATE LC_MONETARY LC_MESSAGES
AcceptEnv LC_PAPER LC_NAME LC_ADDRESS LC_TELEPHONE LC_MEASUREMENT
AcceptEnv LC_IDENTIFICATION LC_ALL
"""
        sshd_config_file = self.icicle_tmp + "/sshd_config"
        f = open(sshd_config_file, 'w')
        f.write(sshd_config)
        f.close()

        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.mv('/etc/ssh/sshd_config', '/etc/ssh/sshd_config.icicle')
        g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
        os.unlink(sshd_config_file)

    def image_ssh_setup_step_3(self, g_handle):
        # part 3; make sure the guest announces itself
        self.log.debug("Step 3: Guest announcement")
        if not g_handle.exists('/etc/init.d/cron') or not g_handle.exists('/usr/sbin/cron'):
            raise OzException.OzException("cron not installed on the image, cannot continue")

        iciclepath = ozutil.generate_full_guesttools_path('icicle-nc')
        g_handle.upload(iciclepath, '/root/icicle-nc')
        g_handle.chmod(0755, '/root/icicle-nc')

        announcefile = self.icicle_tmp + "/announce"
        f = open(announcefile, 'w')
        f.write('*/1 * * * * root /bin/bash -c "/root/icicle-nc ' + self.host_bridge_ip + ' ' + str(self.listen_port) + '"\n')
        f.close()

        g_handle.upload(announcefile, '/etc/cron.d/announce')

        runlevel = self.get_default_runlevel(g_handle)
        startuplink = '/etc/rc.d/rc' + runlevel + ".d/S06cron"
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".icicle")
        g_handle.ln_sf('/etc/init.d/cron', startuplink)

        os.unlink(announcefile)

    def collect_setup(self, libvirt_xml):
        self.log.info("Collection Setup")

        self.mkdir_p(self.icicle_tmp)

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        # we have to do 3 things to make sure we can ssh into OpenSUSE:
        # 1)  Upload our ssh key
        # 2)  Make sure sshd is running on boot
        # 3)  Make the guest announce itself to the host

        try:
            try:
                self.image_ssh_setup_step_1(g_handle)

                try:
                    self.image_ssh_setup_step_2(g_handle)

                    try:
                        self.image_ssh_setup_step_3(g_handle)
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

def get_class(tdl, config, auto):
    if tdl.update in ["11.0", "11.1", "11.2", "11.3", "11.4"]:
        return OpenSUSEGuest(tdl, config, auto)

    raise OzException.OzException("Unsupported OpenSUSE update " + tdl.update)
