# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012,2013  Chris Lalancette <clalancette@gmail.com>

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
OpenSUSE installation
"""

import re
import shutil
import os
import lxml.etree

import oz.Linux
import oz.ozutil
import oz.OzException

class OpenSUSEGuest(oz.Linux.LinuxCDGuest):
    """
    Class for OpenSUSE installation.
    """
    def __init__(self, tdl, config, auto, output_disk, nicmodel, diskbus,
                 macaddress):
        oz.Linux.LinuxCDGuest.__init__(self, tdl, config, auto, output_disk,
                                       nicmodel, diskbus, True, False,
                                       macaddress)

        self.crond_was_active = False
        self.sshd_was_active = False
        self.reboots = 1
        if self.tdl.update in ["10.3"]:
            # for 10.3 we don't have a 2-stage install process so don't reboot
            self.reboots = 0

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Putting the autoyast in place")

        outname = os.path.join(self.iso_contents, "autoinst.xml")

        if self.default_auto_file():
            doc = lxml.etree.parse(self.auto)

            pw = doc.xpath('/suse:profile/suse:users/suse:user/suse:user_password',
                           namespaces={'suse':'http://www.suse.com/1.0/yast2ns'})
            if len(pw) != 1:
                raise oz.OzException.OzException("Invalid SUSE autoyast file; expected single user_password, saw %d" % (len(pw)))
            pw[0].text = self.rootpw

            f = open(outname, 'w')
            f.write(lxml.etree.tostring(doc, pretty_print=True))
            f.close()
        else:
            shutil.copy(self.auto, outname)

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

        with open(isolinux_cfg, 'w') as f:
            f.writelines(lines)

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                           "-J", "-no-emul-boot",
                                           "-b", "boot/" + self.tdl.arch + "/loader/isolinux.bin",
                                           "-c", "boot/" + self.tdl.arch + "/loader/boot.cat",
                                           "-boot-load-size", "4",
                                           "-boot-info-table", "-graft-points",
                                           "-iso-level", "4", "-pad",
                                           "-allow-leading-dots", "-l",
                                           "-o", self.output_iso,
                                           self.iso_contents])

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        return self._do_install(timeout, force, self.reboots)

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
            self._guestfs_path_restore(g_handle, '/etc/init.d/after.local')

    def _image_ssh_teardown_step_3(self, g_handle):
        """
        Third step to undo _image_ssh_setup (remove guest announcement).
        """
        self.log.debug("Teardown step 3")
        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        self._guestfs_remove_if_exists(g_handle,
                                       '/etc/NetworkManager/dispatcher.d/99-reportip')
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

    def do_icicle(self, guestaddr):
        """
        Method to collect the package information and generate the ICICLE
        XML.
        """
        self.log.debug("Generating ICICLE")
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             'rpm -qa',
                                                             timeout=30)

        return self._output_icicle_xml(stdout.split("\n"),
                                       self.tdl.description)

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
        if not g_handle.exists('/etc/init.d/sshd') or not g_handle.exists('/usr/sbin/sshd'):
            raise oz.OzException.OzException("ssh not installed on the image, cannot continue")

        if g_handle.exists('/usr/lib/systemd/system/sshd.service'):
            if g_handle.exists('/etc/systemd/system/multi-user.target.wants/sshd.service'):
                self.sshd_was_active = True
            else:
                g_handle.ln_sf('/usr/lib/systemd/system/sshd.service',
                               '/etc/systemd/system/multi-user.target.wants/sshd.service')
        else:
            self._guestfs_path_backup(g_handle, "/etc/init.d/after.local")
            local = os.path.join(self.icicle_tmp, "after.local")
            with open(local, "w") as f:
                f.write("/sbin/service sshd start\n")
            try:
                g_handle.upload(local, "/etc/init.d/after.local")
            finally:
                os.unlink(local)

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

        if g_handle.exists("/etc/NetworkManager/dispatcher.d"):
            with open(scriptfile, 'w') as f:
                f.write("""\
#!/bin/bash

if [ "$1" = "eth0" -a "$2" = "up" ]; then
    echo -n "!$DHCP4_IP_ADDRESS,%s!" > /dev/ttyS1
fi
""" % (self.uuid))

            try:
                g_handle.upload(scriptfile,
                                '/etc/NetworkManager/dispatcher.d/99-reportip')
                g_handle.chmod(0755,
                               '/etc/NetworkManager/dispatcher.d/99-reportip')
            finally:
                os.unlink(scriptfile)

        if not g_handle.exists('/etc/init.d/cron') or not g_handle.exists('/usr/sbin/cron'):
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

    def _customize_repos(self, guestaddr):
        """
        Method to add user-provided repositories to the guest.
        """
        self.log.debug("Installing additional repository files")
        for repo in list(self.tdl.repositories.values()):
            self.guest_execute_command(guestaddr,
                                       "zypper addrepo %s %s" % (repo.url,
                                                                 repo.name))

    def _install_packages(self, guestaddr, packstr):
        # due to a bug in OpenSUSE 11.1, we want to remove the default
        # CD repo first
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             'zypper repos -d')
        removerepos = []
        for line in stdout.split('\n'):
            if re.match("^[0-9]+", line):
                split = line.split('|')

                if re.match("^cd://", split[7].strip()):
                    removerepos.append(split[0].strip())
        for repo in removerepos:
            self.guest_execute_command(guestaddr,
                                       'zypper removerepo %s' % (repo))

        self.guest_execute_command(guestaddr,
                                   'zypper -n install %s' % (packstr))

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for OpenSUSE installs.
    """
    if tdl.update in ["10.3"]:
        return OpenSUSEGuest(tdl, config, auto, output_disk, netdev, diskbus,
                             macaddress)
    if tdl.update in ["11.0", "11.1", "11.2", "11.3", "11.4", "12.1", "12.2", "12.3"]:
        if diskbus is None:
            diskbus = 'virtio'
        if netdev is None:
            netdev = 'virtio'
        return OpenSUSEGuest(tdl, config, auto, output_disk, netdev, diskbus,
                             macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "OpenSUSE: 10.3, 11.0, 11.1, 11.2, 11.3, 11.4, 12.1, 12.2, 12.3"
