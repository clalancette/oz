# Copyright (C) 2013-2016  Chris Lalancette <clalancette@gmail.com>

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

import oz.Linux
import oz.ozutil
import oz.OzException

class MageiaGuest(oz.Linux.LinuxCDGuest):
    """
    Class for Mageia 2, 3, 4, 4.1, and 5 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.Linux.LinuxCDGuest.__init__(self, tdl, config, auto, output_disk,
                                       netdev, diskbus, True, False,
                                       macaddress)

        self.mageia_arch = self.tdl.arch
        if self.mageia_arch == "i386":
            self.mageia_arch = "i586"

        self.sshd_was_active = False
        self.crond_was_active = False

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying cfg file to floppy image")

        outname = os.path.join(self.iso_contents, "auto_inst.cfg")

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

        oz.ozutil.subprocess_check_output(["/sbin/mkfs.msdos", "-C",
                                           self.output_floppy, "1440"])
        oz.ozutil.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                           self.output_floppy, outname,
                                           "::AUTO_INST.CFG"])

        self.log.debug("Modifying isolinux.cfg")
        if self.tdl.update in ["2", "3"]:
            isolinuxcfg = os.path.join(self.iso_contents, self.mageia_arch, "isolinux", "isolinux.cfg")
        else:
            isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")

        if self.tdl.update in ["2", "3", "4"]:
            with open(isolinuxcfg, 'w') as f:
                f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel alt0/vmlinuz
  append initrd=alt0/all.rdz ramdisk_size=128000 root=/dev/ram3 acpi=ht vga=788 automatic=method:cdrom kickstart=floppy
""")
        elif self.tdl.update in ["4.1", "5"]:
            with open(isolinuxcfg, 'w') as f:
                f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel %s/vmlinuz
  append initrd=%s/all.rdz automatic=method:cdrom kickstart=floppy
""" % (self.mageia_arch, self.mageia_arch))

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")

        isolinuxdir = ""
        if self.tdl.update in ["2", "3", "4"]:
            isolinuxdir = self.mageia_arch
        elif self.tdl.update in ["4.1", "5"]:
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

    def _image_ssh_teardown_step_1(self, g_handle):
        """
        First step to undo _image_ssh_setup (remove authorized keys).
        """
        self.log.debug("Teardown step 1")
        # reset the authorized keys
        self.log.debug("Resetting authorized_keys")
        self._guestfs_path_restore(g_handle, '/root/.ssh/authorized_keys')

    def _image_ssh_teardown_step_2(self, g_handle):
        """
        Second step to undo _image_ssh_setup (remove custom sshd_config).
        """
        self.log.debug("Teardown step 2")
        # remove custom sshd_config
        self.log.debug("Resetting sshd_config")
        self._guestfs_path_restore(g_handle, '/etc/ssh/sshd_config')

        # reset the service link
        self.log.debug("Resetting sshd service")
        if g_handle.exists('/usr/lib/systemd/system/sshd.service'):
            if not self.sshd_was_active:
                g_handle.rm('/etc/systemd/system/multi-user.target.wants/sshd.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'sshd')
            self._guestfs_path_restore(g_handle, startuplink)

    def _image_ssh_teardown_step_3(self, g_handle):
        """
        Third step to undo _image_ssh_setup (remove guest announcement).
        """
        self.log.debug("Teardown step 3")
        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        self._guestfs_remove_if_exists(g_handle, '/etc/cron.d/announce')

        # remove reportip
        self.log.debug("Removing reportip")
        self._guestfs_remove_if_exists(g_handle, '/root/reportip')

        # reset the service link
        self.log.debug("Resetting cron service")
        if g_handle.exists('/usr/lib/systemd/system/cron.service'):
            if not self.crond_was_active:
                g_handle.rm('/etc/systemd/system/multi-user.target.wants/cron.service')
        else:
            runlevel = self.get_default_runlevel(g_handle)
            startuplink = '/etc/rc.d/rc' + runlevel + ".d/S06cron"
            self._guestfs_path_restore(g_handle, startuplink)

    def _image_ssh_teardown_step_4(self, g_handle):
        """
        Fourth step to undo changes by the operating system.  For instance,
        during first boot openssh generates ssh host keys and stores them
        in /etc/ssh.  Since this image might be cached later on, this method
        removes those keys.
        """
        for f in ["/etc/ssh/ssh_host_dsa_key", "/etc/ssh/ssh_host_dsa_key.pub",
                  "/etc/ssh/ssh_host_rsa_key", "/etc/ssh/ssh_host_rsa_key.pub",
                  "/etc/ssh/ssh_host_ecdsa_key", "/etc/ssh/ssh_host_ecdsa_key.pub",
                  "/etc/ssh/ssh_host_key", "/etc/ssh/ssh_host_key.pub"]:
            self._guestfs_remove_if_exists(g_handle, f)

        # Remove any lease files; this is so that subsequent boots don't try
        # to connect to a DHCP server that is on a totally different network
        for lease in g_handle.glob_expand("/var/lib/dhcp/*.leases"):
            g_handle.rm_f(lease)

        for lease in g_handle.glob_expand("/var/lib/dhcp6/*.leases"):
            g_handle.rm_f(lease)

        for lease in g_handle.glob_expand("/var/lib/dhcp6/*.lease"):
            g_handle.rm_f(lease)

    def _collect_teardown(self, libvirt_xml):
        """
        Method to reverse the changes done in _collect_setup.
        """
        self.log.info("Collection Teardown")

        g_handle = self._guestfs_handle_setup(libvirt_xml)

        try:
            self._image_ssh_teardown_step_1(g_handle)

            self._image_ssh_teardown_step_2(g_handle)

            self._image_ssh_teardown_step_3(g_handle)

            self._image_ssh_teardown_step_4(g_handle)
        finally:
            self._guestfs_handle_cleanup(g_handle)
            shutil.rmtree(self.icicle_tmp)

    def _image_ssh_setup_step_1(self, g_handle):
        """
        First step for allowing remote access (generate and upload ssh keys).
        """
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if not g_handle.exists('/root/.ssh'):
            g_handle.mkdir('/root/.ssh')

        self._guestfs_path_backup(g_handle, '/root/.ssh/authorized_keys')

        self._generate_openssh_key(self.sshprivkey)

        g_handle.upload(self.sshprivkey + ".pub", '/root/.ssh/authorized_keys')

    def _image_ssh_setup_step_2(self, g_handle):
        """
        Second step for allowing remote access (ensure sshd is running).
        """
        # part 2; check and setup sshd
        self.log.debug("Step 2: setup sshd")
        if not g_handle.exists('/usr/sbin/sshd'):
            raise oz.OzException.OzException("ssh not installed on the image, cannot continue")

        if g_handle.exists('/usr/lib/systemd/system/sshd.service'):
            if g_handle.exists('/etc/systemd/system/multi-user.target.wants/sshd.service'):
                self.sshd_was_active = True
            else:
                g_handle.ln_sf('/usr/lib/systemd/system/sshd.service',
                               '/etc/systemd/system/multi-user.target.wants/sshd.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'sshd')
            self._guestfs_path_backup(g_handle, startuplink)
            g_handle.ln_sf('/etc/init.d/sshd', startuplink)

        sshd_config_file = self.icicle_tmp + "/sshd_config"
        with open(sshd_config_file, 'w') as f:
            f.write("""PasswordAuthentication no
UsePAM yes

X11Forwarding yes

Subsystem      sftp    /usr/lib64/ssh/sftp-server

AcceptEnv LANG LC_CTYPE LC_NUMERIC LC_TIME LC_COLLATE LC_MONETARY LC_MESSAGES
AcceptEnv LC_PAPER LC_NAME LC_ADDRESS LC_TELEPHONE LC_MEASUREMENT
AcceptEnv LC_IDENTIFICATION LC_ALL
""")

        try:
            self._guestfs_path_backup(g_handle, "/etc/ssh/sshd_config")
            g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
        finally:
            os.unlink(sshd_config_file)

    def _image_ssh_setup_step_3(self, g_handle):
        """
        Third step for allowing remote access (make the guest announce itself
        on bootup).
        """
        # part 3; make sure the guest announces itself
        self.log.debug("Step 3: Guest announcement")

        scriptfile = os.path.join(self.icicle_tmp, "script")

        if not g_handle.exists('/usr/sbin/crond'):
            raise oz.OzException.OzException("cron not installed on the image, cannot continue")

        with open(scriptfile, 'w') as f:
            f.write("""\
#!/bin/bash
DEV=$(/bin/awk '{if ($2 == 0) print $1}' /proc/net/route) &&
[ -z "$DEV" ] && exit 0
ADDR=$(/sbin/ip -4 -o addr show dev $DEV | /bin/awk '{print $4}' | /usr/bin/cut -d/ -f1) &&
[ -z "$ADDR" ] && exit 0
echo -n "!$ADDR,%s!" > /dev/ttyS1
""" % (self.uuid))

        try:
            g_handle.upload(scriptfile, '/root/reportip')
            g_handle.chmod(0o755, '/root/reportip')
        finally:
            os.unlink(scriptfile)

        announcefile = os.path.join(self.icicle_tmp, "announce")
        with open(announcefile, 'w') as f:
            f.write('*/1 * * * * root /bin/bash -c "/root/reportip"\n')

        try:
            g_handle.upload(announcefile, '/etc/cron.d/announce')
        finally:
            os.unlink(announcefile)

        if g_handle.exists('/usr/lib/systemd/system/cron.service'):
            if g_handle.exists('/etc/systemd/system/multi-user.target.wants/cron.service'):
                self.crond_was_active = True
            else:
                g_handle.ln_sf('/lib/systemd/system/cron.service',
                               '/etc/systemd/system/multi-user.target.wants/cron.service')
        else:
            runlevel = self.get_default_runlevel(g_handle)
            startuplink = '/etc/rc.d/rc' + runlevel + ".d/S06cron"
            self._guestfs_path_backup(g_handle, startuplink)
            g_handle.ln_sf('/etc/init.d/cron', startuplink)

    def _collect_setup(self, libvirt_xml):
        """
        Setup the guest for remote access.
        """
        self.log.info("Collection Setup")

        g_handle = self._guestfs_handle_setup(libvirt_xml)

        # we have to do 3 things to make sure we can ssh into OpenSUSE:
        # 1)  Upload our ssh key
        # 2)  Make sure sshd is running on boot
        # 3)  Make the guest announce itself to the host

        try:
            try:
                self._image_ssh_setup_step_1(g_handle)

                try:
                    self._image_ssh_setup_step_2(g_handle)

                    try:
                        self._image_ssh_setup_step_3(g_handle)
                    except:
                        self._image_ssh_teardown_step_3(g_handle)
                        raise
                except:
                    self._image_ssh_teardown_step_2(g_handle)
                    raise
            except:
                self._image_ssh_teardown_step_1(g_handle)
                raise

        finally:
            self._guestfs_handle_cleanup(g_handle)

    def do_icicle(self, guestaddr):
        """
        Method to collect the package information and generate the ICICLE
        XML.
        """
        self.log.debug("Generating ICICLE")
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             'rpm -qa',
                                                             timeout=30)

        package_split = stdout.split("\n")

        extrasplit = None
        if self.tdl.icicle_extra_cmd:
            extrastdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                                      self.tdl.icicle_extra_cmd,
                                                                      timeout=30)
            extrasplit = extrastdout.split("\n")

            if len(package_split) != len(extrasplit):
                raise oz.OzException.OzException("Invalid extra package command; it must return the same set of packages as 'rpm -qa'")

        return self._output_icicle_xml(package_split, self.tdl.description,
                                       extrasplit)

    def install(self, timeout=None, force=False):
        fddev = self._InstallDev("floppy", self.output_floppy, "fda")
        return self._do_install(timeout, force, 0, None, None, None,
                                [fddev])

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Mageia installs.
    """
    if tdl.update in ["2", "3", "4", "4.1", "5"]:
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return MageiaGuest(tdl, config, auto, output_disk, netdev, diskbus,
                           macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Mageia: 2, 3, 4, 4.1, 5"
