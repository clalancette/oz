# Copyright (C) 2013-2018  Chris Lalancette <clalancette@gmail.com>

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

import os
import re
import shutil
try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse

import oz.GuestFSManager
import oz.Linux
import oz.OzException
import oz.ozutil


class MageiaConfiguration(object):
    """
    Configuration class for Mageia installation.
    """
    def __init__(self, isolinux_style, default_netdev, default_diskbus):
        self._isolinux_style = isolinux_style
        self._default_netdev = default_netdev
        self._default_diskbus = default_diskbus

    @property
    def isolinux_style(self):
        """
        Property method for the 'old' or 'new' isolinux style.
        """
        return self._isolinux_style

    @property
    def default_netdev(self):
        """
        Property method for the default netdev for this version of Mageia.
        """
        return self._default_netdev

    @property
    def default_diskbus(self):
        """
        Property method for the default diskbus for this version of Mageia.
        """
        return self._default_diskbus


version_to_config = {
    '5': MageiaConfiguration(isolinux_style="new", default_netdev='virtio',
                             default_diskbus='virtio'),
    '4.1': MageiaConfiguration(isolinux_style="new", default_netdev='virtio',
                               default_diskbus='virtio'),
    '4': MageiaConfiguration(isolinux_style="new", default_netdev='virtio',
                             default_diskbus='virtio'),
    '3': MageiaConfiguration(isolinux_style="old", default_netdev='virtio',
                             default_diskbus='virtio'),
    '2': MageiaConfiguration(isolinux_style="old", default_netdev='virtio',
                             default_diskbus='virtio'),
}


class MageiaGuest(oz.Linux.LinuxCDGuest):
    """
    Class for Mageia 2, 3, 4, 4.1, and 5 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        self.config = version_to_config[tdl.update]
        if netdev is None:
            netdev = self.config.default_netdev
        if diskbus is None:
            diskbus = self.config.default_diskbus
        oz.Linux.LinuxCDGuest.__init__(self, tdl, config, auto, output_disk,
                                       netdev, diskbus, True, True,
                                       macaddress)

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
        if self.config.isolinux_style == "old":
            # Mageia 2 dual   - isolinux/32.cfg
            #                   isolinux/64.cfg
            #                   isolinux/alt0/32/vmlinuz
            #                   isolinux/alt0/32/all.rdz
            #                   isolinux/alt0/64/vmlinuz
            #                   isolinux/alt0/64/all.rdz
            # Mageia 2 x86_64 - x86_64/isolinux/isolinux.cfg
            #                   x86_64/isolinux/alt0/vmlinuz
            #                   x86_64/isolinux/alt0/all.rdz
            # Mageia 2 i586   - i586/isolinux/isolinux.cfg
            #                   i586/isolinux/vmlinuz
            #                   i586/isolinux/all.rdz
            # Mageia 3 dual   - syslinux/32.cfg
            #                   syslinux/64.cfg
            #                   syslinux/alt0/32/vmlinuz
            #                   syslinux/alt0/32/all.rdz
            #                   syslinux/alt0/64/vmlinuz
            #                   syslinux/alt0/64/all.rdz
            # Mageia 3 x86_64 - x86_64/isolinux/isolinux.cfg
            #                   x86_64/isolinux/alt0/vmlinuz
            #                   x86_64/isolinux/alt0/all.rdz
            # Mageia 3 i586   - i586/isolinux/isolinux.cfg
            #                   i586/isolinux/alt0/vmlinuz
            #                   i586/isolinux/alt0/all.rdz
            isolinuxstr = None
            if os.path.exists(os.path.join(self.iso_contents, 'isolinux')):
                isolinuxstr = "isolinux"
            elif os.path.exists(os.path.join(self.iso_contents, 'syslinux')):
                isolinuxstr = "syslinux"

            if isolinuxstr is not None:
                if self.tdl.arch == "i386":
                    mageia_arch = "32"
                else:
                    mageia_arch = "64"

                # This looks like a dual CD, so let's set things up that way.
                isolinuxcfg = os.path.join(self.iso_contents, isolinuxstr, mageia_arch + ".cfg")
                self.isolinuxbin = os.path.join(isolinuxstr, mageia_arch + ".bin")
                kernel = "alt0/" + mageia_arch + "/vmlinuz"
                initrd = "alt0/" + mageia_arch + "/all.rdz"
            else:
                # This looks like an i586 or x86_64 ISO, so set things up that way.
                mageia_arch = self.tdl.arch
                if self.tdl.arch == "i386":
                    mageia_arch = "i586"
                isolinuxcfg = os.path.join(self.iso_contents, mageia_arch, 'isolinux', 'isolinux.cfg')
                self.isolinuxbin = os.path.join(mageia_arch, 'isolinux', 'isolinux.bin')
                kernel = "alt0/vmlinuz"
                initrd = "alt0/all.rdz"
            flags = "ramdisk_size=128000 root=/dev/ram3 acpi=ht vga=788 automatic=method:cdrom"
        else:
            # Mageia 4 dual     - isolinux/i586.cfg
            #                     isolinux/x86_64.cfg
            #                     isolinux/i586/vmlinuz
            #                     isolinux/i586/all.rdz
            #                     isolinux/x86_64/vmlinuz
            #                     isolinux/x86_64/all.rdz
            # Mageia 4 x86_64   - isolinux/isolinux.cfg
            #                     isolinux/x86_64/vmlinuz
            #                     isolinux/x86_64/all.rdz
            # Mageia 4 i586     - isolinux/isolinux.cfg
            #                     isolinux/i586/vmlinuz
            #                     isolinuz/i586/all.rdz
            # Mageia 4.1 dual   - isolinux/i586.cfg
            #                     isolinux/x86_64.cfg
            #                     isolinux/i586/vmlinuz
            #                     isolinux/i586/all.rdz
            #                     isolinux/x86_64/vmlinuz
            #                     isolinux/x86_64/all.rdz
            # Mageia 4.1 x86_64 - isolinux/isolinux.cfg
            #                     isolinux/x86_64/vmlinuz
            #                     isolinux/x86_64/all.rdz
            # Mageia 4.1 i586 -   isolinux/isolinux.cfg
            #                     isolinux/i586/vmlinuz
            #                     isolinux/i586/all.rdz
            # Mageia 5 dual     - isolinux/i586.cfg
            #                     isolinux/x86_64.cfg
            #                     isolinux/i586/vmlinuz
            #                     isolinux/i586/all.rdz
            #                     isolinux/x86_64/vmlinuz
            #                     isolinux/x86_64/all.rdz
            # Mageia 5 x86_64   - isolinux/isolinux.cfg
            #                     isolinux/x86_64/vmlinuz
            #                     isolinux/x86_64/all.rdz
            # Mageia 5 i586 -     isolinux/isolinux.cfg
            #                     isolinux/i586/vmlinuz
            #                     isolinux/i586/all.rdz

            # Starting with Mageia 4, things are a lot more regular.  The
            # directory always starts with isolinux.  If it is a dual ISO, then
            # there is an i586.cfg and x86_64.cfg describing how to boot each
            # of them.  Otherwise, there is just an isolinux.cfg.  The kernel
            # and initrd are always in the same place.
            mageia_arch = self.tdl.arch
            if self.tdl.arch == "i386":
                mageia_arch = "i586"
            if os.path.exists(os.path.join(self.iso_contents, 'isolinux', 'i586.cfg')):
                # A dual, so use the correct cfg
                isolinuxcfg = os.path.join(self.iso_contents, 'isolinux', mageia_arch + ".cfg")
                self.isolinuxbin = os.path.join('isolinux', mageia_arch + ".bin")
            else:
                isolinuxcfg = os.path.join(self.iso_contents, 'isolinux', 'isolinux.cfg')
                self.isolinuxbin = os.path.join('isolinux', 'isolinux.bin')
            kernel = mageia_arch + "/vmlinuz"
            initrd = mageia_arch + "/all.rdz"
            if self.tdl.installtype == "url":
                url = urlparse.urlparse(self.tdl.url)
                flags = "automatic=method:%s,ser:%s,dir:%s,int:eth0,netw:dhcp" % (url.scheme, url.hostname, url.path)
            else:
                flags = "automatic=method:cdrom"

        with open(isolinuxcfg, 'w') as f:
            f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel %s
  append initrd=%s kickstart=floppy %s
""" % (kernel, initrd, flags))

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")

        oz.ozutil.subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                           "-J", "-l", "-no-emul-boot",
                                           "-b", self.isolinuxbin,
                                           "-c", "boot.catalog",
                                           "-boot-load-size", "4",
                                           "-cache-inodes", "-boot-info-table",
                                           "-v", "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

    def _get_service_runlevel_link(self, g_handle, service):
        """
        Method to find the runlevel link(s) for a service based on the name
        and the (detected) default runlevel.
        """
        runlevel = self.get_default_runlevel(g_handle)

        lines = g_handle.cat('/etc/init.d/' + service).split("\n")
        startlevel = "99"
        for line in lines:
            if re.match('# chkconfig:', line):
                try:
                    startlevel = line.split(':')[1].split()[1]
                except Exception:
                    pass
                break

        return "/etc/rc" + runlevel + ".d/S" + startlevel + service

    def _image_ssh_teardown_step_1(self, g_handle):
        """
        First step to undo _image_ssh_setup (remove authorized keys).
        """
        self.log.debug("Teardown step 1")
        # reset the authorized keys
        self.log.debug("Resetting authorized_keys")
        g_handle.path_restore('/root/.ssh/authorized_keys')

    def _image_ssh_teardown_step_2(self, g_handle):
        """
        Second step to undo _image_ssh_setup (remove custom sshd_config).
        """
        self.log.debug("Teardown step 2")
        # remove custom sshd_config
        self.log.debug("Resetting sshd_config")
        g_handle.path_restore('/etc/ssh/sshd_config')

        # reset the service link
        self.log.debug("Resetting sshd service")
        if g_handle.exists('/usr/lib/systemd/system/sshd.service'):
            if not self.sshd_was_active:
                g_handle.rm('/etc/systemd/system/multi-user.target.wants/sshd.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'sshd')
            g_handle.path_restore(startuplink)

    def _image_ssh_teardown_step_3(self, g_handle):
        """
        Third step to undo _image_ssh_setup (remove guest announcement).
        """
        self.log.debug("Teardown step 3")
        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        g_handle.remove_if_exists('/etc/cron.d/announce')

        # remove reportip
        self.log.debug("Removing reportip")
        g_handle.remove_if_exists('/root/reportip')

        # reset the service link
        self.log.debug("Resetting cron service")
        if g_handle.exists('/usr/lib/systemd/system/cron.service'):
            if not self.crond_was_active:
                g_handle.rm('/etc/systemd/system/multi-user.target.wants/cron.service')
        else:
            runlevel = self.get_default_runlevel(g_handle)
            startuplink = '/etc/rc.d/rc' + runlevel + ".d/S06cron"
            g_handle.path_restore(startuplink)

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
            g_handle.remove_if_exists(f)

        # Remove any lease files; this is so that subsequent boots don't try
        # to connect to a DHCP server that is on a totally different network
        for lease in g_handle.glob_expand("/var/lib/dhcp/*.leases"):
            g_handle.rm(lease)

        for lease in g_handle.glob_expand("/var/lib/dhcp6/*.leases"):
            g_handle.rm(lease)

        for lease in g_handle.glob_expand("/var/lib/dhcp6/*.lease"):
            g_handle.rm(lease)

    def _collect_teardown(self, libvirt_xml):
        """
        Method to reverse the changes done in _collect_setup.
        """
        self.log.info("Collection Teardown")

        g_handle = oz.GuestFSManager.GuestFSLibvirtFactory(libvirt_xml, self.libvirt_conn)
        g_handle.mount_partitions()

        try:
            self._image_ssh_teardown_step_1(g_handle)

            self._image_ssh_teardown_step_2(g_handle)

            self._image_ssh_teardown_step_3(g_handle)

            self._image_ssh_teardown_step_4(g_handle)
        finally:
            g_handle.cleanup()
            shutil.rmtree(self.icicle_tmp)

    def _image_ssh_setup_step_1(self, g_handle):
        """
        First step for allowing remote access (generate and upload ssh keys).
        """
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if not g_handle.exists('/root/.ssh'):
            g_handle.mkdir('/root/.ssh')

        g_handle.path_backup('/root/.ssh/authorized_keys')

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
            g_handle.path_backup(startuplink)
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
            g_handle.path_backup("/etc/ssh/sshd_config")
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
            g_handle.path_backup(startuplink)
            g_handle.ln_sf('/etc/init.d/cron', startuplink)

    def _collect_setup(self, libvirt_xml):
        """
        Setup the guest for remote access.
        """
        self.log.info("Collection Setup")

        g_handle = oz.GuestFSManager.GuestFSLibvirtFactory(libvirt_xml, self.libvirt_conn)
        g_handle.mount_partitions()

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
            g_handle.cleanup()

    def do_icicle(self, guestaddr):
        """
        Method to collect the package information and generate the ICICLE
        XML.
        """
        self.log.debug("Generating ICICLE")
        stdout, stderr_unused, retcode_unused = self.guest_execute_command(guestaddr,
                                                                           'rpm -qa',
                                                                           timeout=30)

        package_split = stdout.split("\n")

        extrasplit = None
        if self.tdl.icicle_extra_cmd:
            extrastdout, stderr_unused, retcode_unused = self.guest_execute_command(guestaddr,
                                                                                    self.tdl.icicle_extra_cmd,
                                                                                    timeout=30)
            extrasplit = extrastdout.split("\n")

            if len(package_split) != len(extrasplit):
                raise oz.OzException.OzException("Invalid extra package command; it must return the same set of packages as 'rpm -qa'")

        return self._output_icicle_xml(package_split, self.tdl.description,
                                       extrasplit)

    def generate_install_media(self, force_download=False,
                               customize_or_icicle=False):
        """
        Method to generate the install media for Mageia based operating
        systems.  If force_download is False (the default), then the
        original media will only be fetched if it is not cached locally.  If
        force_download is True, then the original media will be downloaded
        regardless of whether it is cached locally.
        """
        fetchurl = self.url
        if self.tdl.installtype == 'url':
            fetchurl += "/install/images/boot.iso"
        return self._iso_generate_install_media(fetchurl, force_download,
                                                customize_or_icicle)

    def install(self, timeout=None, force=False):
        fddev = self._InstallDev("floppy", self.output_floppy, "fda")
        return self._do_install(timeout, force, 0, None, None, None,
                                [fddev])


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Mageia installs.
    """
    if tdl.update in version_to_config.keys():
        return MageiaGuest(tdl, config, auto, output_disk, netdev, diskbus,
                           macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Mageia: " + ", ".join(sorted(version_to_config.keys()))
