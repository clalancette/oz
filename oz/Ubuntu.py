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
Ubuntu installation
"""

import shutil
import re
import os
import gzip

import oz.Linux
import oz.ozutil
import oz.OzException

class UbuntuGuest(oz.Linux.LinuxCDGuest):
    """
    Class for Ubuntu 5.04, 5.10, 6.06, 6.10, 7.04, 7.10, 8.04, 8.10, 9.04, 9.10, 10.04, 10.10, 11.04, 11.10, 12.04, 12.10, 13.04, and 13.10 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, initrd, nicmodel,
                 diskbus, macaddress):
        oz.Linux.LinuxCDGuest.__init__(self, tdl, config, auto, output_disk,
                                       nicmodel, diskbus, True, True,
                                       macaddress)

        self.crond_was_active = False
        self.sshd_was_active = False
        self.sshd_config = """\
SyslogFacility AUTHPRIV
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
Subsystem       sftp    /usr/libexec/openssh/sftp-server
"""

        self.casper_initrd = initrd

        self.ssh_startuplink = None
        self.cron_startuplink = None

        self.debarch = self.tdl.arch
        if self.debarch == "x86_64":
            self.debarch = "amd64"

        self.kernelfname = os.path.join(self.output_dir,
                                        self.tdl.name + "-kernel")
        self.initrdfname = os.path.join(self.output_dir,
                                        self.tdl.name + "-ramdisk")
        self.kernelcache = os.path.join(self.data_dir, "kernels",
                                        self.tdl.distro + self.tdl.update + self.tdl.arch + "-kernel")
        self.initrdcache = os.path.join(self.data_dir, "kernels",
                                        self.tdl.distro + self.tdl.update + self.tdl.arch + "-ramdisk")

        self.cmdline = "priority=critical locale=en_US"

        self.reboots = 0
        if self.tdl.update in ["5.04", "5.10"]:
            self.reboots = 1

    def _check_iso_tree(self, customize_or_icicle):
        # ISOs that contain casper are desktop install CDs
        if os.path.isdir(os.path.join(self.iso_contents, "casper")):
            if self.tdl.update in ["6.06", "6.10", "7.04"]:
                raise oz.OzException.OzException("Ubuntu %s installs can only be done using the alternate or server CDs" % (self.tdl.update))
            if customize_or_icicle:
                raise oz.OzException.OzException("Ubuntu customization or ICICLE generation can only be done using the alternate or server CDs")

    def _copy_preseed(self, outname):
        """
        Method to copy and modify an Ubuntu style preseed file.
        """
        self.log.debug("Putting the preseed file in place")

        if self.default_auto_file():
            def _preseed_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Ubuntu.
                """
                if re.match('d-i passwd/root-password password', line):
                    return 'd-i passwd/root-password password ' + self.rootpw + '\n'
                elif re.match('d-i passwd/root-password-again password', line):
                    return 'd-i passwd/root-password-again password ' + self.rootpw + '\n'
                else:
                    return line

            oz.ozutil.copy_modify_file(self.auto, outname, _preseed_sub)
        else:
            shutil.copy(self.auto, outname)

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        self.log.debug("Copying preseed file")
        outname = os.path.join(self.iso_contents, "preseed", "customiso.seed")
        outdir = os.path.dirname(outname)
        oz.ozutil.mkdir_p(outdir)

        self._copy_preseed(outname)

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")
        isolinuxdir = os.path.dirname(isolinuxcfg)
        if not os.path.isdir(isolinuxdir):
            oz.ozutil.mkdir_p(isolinuxdir)
            shutil.copyfile(os.path.join(self.iso_contents, "isolinux.bin"),
                            os.path.join(isolinuxdir, "isolinux.bin"))
            shutil.copyfile(os.path.join(self.iso_contents, "boot.cat"),
                            os.path.join(isolinuxdir, "boot.cat"))

        with open(isolinuxcfg, 'w') as f:

            if self.tdl.update in ["5.04", "5.10"]:
                f.write("""\
DEFAULT /install/vmlinuz
APPEND initrd=/install/initrd.gz ramdisk_size=16384 root=/dev/rd/0 rw preseed/file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US kbd-chooser/method=us netcfg/choose_interface=auto keyboard-configuration/layoutcode=us debconf/priority=critical --
TIMEOUT 1
PROMPT 0
""")
            else:
                f.write("default customiso\n")
                f.write("timeout 1\n")
                f.write("prompt 0\n")
                f.write("label customiso\n")
                f.write("  menu label ^Customiso\n")
                f.write("  menu default\n")
                if os.path.isdir(os.path.join(self.iso_contents, "casper")):
                    kernelname = "/casper/vmlinuz"
                    if self.tdl.update in ["12.04.2", "13.04"] and self.tdl.arch == "x86_64":
                        kernelname += ".efi"
                    f.write("  kernel " + kernelname + "\n")
                    f.write("  append file=/cdrom/preseed/customiso.seed boot=casper automatic-ubiquity noprompt keyboard-configuration/layoutcode=us initrd=/casper/" + self.casper_initrd + "\n")
                else:
                    keyboard = "console-setup/layoutcode=us"
                    if self.tdl.update == "6.06":
                        keyboard = "kbd-chooser/method=us"
                    f.write("  kernel /install/vmlinuz\n")
                    f.write("  append preseed/file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US " + keyboard + " netcfg/choose_interface=auto keyboard-configuration/layoutcode=us priority=critical initrd=/install/initrd.gz --\n")


    def get_auto_path(self):
        autoname = self.tdl.distro + self.tdl.update + ".auto"
        sp = self.tdl.update.split('.')
        if len(sp) == 3:
            autoname = self.tdl.distro + sp[0] + "." + sp[1] + ".auto"
        return oz.ozutil.generate_full_auto_path(autoname)

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.info("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage", "-r", "-V", "Custom",
                                           "-J", "-l", "-no-emul-boot",
                                           "-b", "isolinux/isolinux.bin",
                                           "-c", "isolinux/boot.cat",
                                           "-boot-load-size", "4",
                                           "-cache-inodes", "-boot-info-table",
                                           "-v", "-v", "-o", self.output_iso,
                                           self.iso_contents])

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        if self.tdl.update in ["5.04", "5.10", "6.06", "6.10", "7.04"]:
            if not timeout:
                timeout = 3000
        return self._do_install(timeout, force, self.reboots, self.kernelfname,
                                self.initrdfname, self.cmdline)

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
                except:
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
        self._guestfs_path_restore(g_handle, '/root/.ssh')

    def _image_ssh_teardown_step_2(self, g_handle):
        """
        Second step to undo _image_ssh_setup (reset sshd service).
        """
        self.log.debug("Teardown step 2")
        # remove custom sshd_config
        self.log.debug("Resetting sshd_config")
        self._guestfs_path_restore(g_handle, '/etc/ssh/sshd_config')

        # reset the service link
        self.log.debug("Resetting sshd service")
        if self.ssh_startuplink:
            self._guestfs_path_restore(g_handle, self.ssh_startuplink)

    def _image_ssh_teardown_step_3(self, g_handle):
        """
        Fourth step to undo _image_ssh_setup (remove guest announcement).
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
        if self.cron_startuplink:
            self._guestfs_path_restore(g_handle, self.cron_startuplink)

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

    def _image_ssh_setup_step_1(self, g_handle):
        """
        First step for allowing remote access (generate and upload ssh keys).
        """
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        self._guestfs_path_backup(g_handle, '/root/.ssh')
        g_handle.mkdir('/root/.ssh')

        self._guestfs_path_backup(g_handle, '/root/.ssh/authorized_keys')

        self._generate_openssh_key(self.sshprivkey)

        g_handle.upload(self.sshprivkey + ".pub", '/root/.ssh/authorized_keys')

    def _image_ssh_setup_step_2(self, g_handle):
        """
        Second step for allowing remote access (configure sshd).
        """
        # part 2; check and setup sshd
        self.log.debug("Step 2: setup sshd")
        if not g_handle.exists('/usr/sbin/sshd'):
            raise oz.OzException.OzException("ssh not installed on the image, cannot continue")

        self.ssh_startuplink = self._get_service_runlevel_link(g_handle, 'ssh')
        self._guestfs_path_backup(g_handle, self.ssh_startuplink)
        g_handle.ln_sf('/etc/init.d/ssh', self.ssh_startuplink)

        sshd_config_file = os.path.join(self.icicle_tmp, "sshd_config")
        with open(sshd_config_file, 'w') as f:
            f.write(self.sshd_config)

        try:
            self._guestfs_path_backup(g_handle, '/etc/ssh/sshd_config')
            g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
        finally:
            os.unlink(sshd_config_file)

    def _image_ssh_setup_step_3(self, g_handle):
        """
        Fourth step for allowing remote access (make the guest announce itself
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

        if not g_handle.exists('/usr/sbin/cron'):
            raise oz.OzException.OzException("cron not installed on the image, cannot continue")

        with open(scriptfile, 'w') as f:
            f.write("""\
#!/bin/bash
/bin/sleep 20
DEV=$(/usr/bin/awk '{if ($2 == 0) print $1}' /proc/net/route) &&
[ -z "$DEV" ] && exit 0
ADDR=$(/sbin/ip -4 -o addr show dev $DEV | /usr/bin/awk '{print $4}' | /usr/bin/cut -d/ -f1) &&
[ -z "$ADDR" ] && exit 0
echo -n "!$ADDR,%s!" > /dev/ttyS1
""" % (self.uuid))

        try:
            g_handle.upload(scriptfile, '/root/reportip')
            g_handle.chmod(0755, '/root/reportip')
        finally:
            os.unlink(scriptfile)

        announcefile = os.path.join(self.icicle_tmp, "announce")
        with open(announcefile, 'w') as f:
            f.write('*/1 * * * * root /bin/bash -c "/root/reportip"\n')

        try:
            g_handle.upload(announcefile, '/etc/cron.d/announce')
        finally:
            os.unlink(announcefile)

        self.cron_startuplink = self._get_service_runlevel_link(g_handle,
                                                                'cron')
        self._guestfs_path_backup(g_handle, self.cron_startuplink)
        g_handle.ln_sf('/etc/init.d/cron', self.cron_startuplink)

    def _collect_setup(self, libvirt_xml):
        """
        Setup the guest for remote access.
        """
        self.log.info("Collection Setup")

        g_handle = self._guestfs_handle_setup(libvirt_xml)

        # we have to do 3 things to make sure we can ssh into Ubuntu
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

    def _customize_repos(self, guestaddr):
        """
        Method to generate and upload custom repository files based on the TDL.
        """

        self.log.debug("Installing additional repository files")

        for repo in list(self.tdl.repositories.values()):
            self.guest_execute_command(guestaddr, "apt-add-repository --yes '%s'" % (repo.url.strip('\'"')))
            self.guest_execute_command(guestaddr, "apt-get update")

    def _install_packages(self, guestaddr, packstr):
        self.guest_execute_command(guestaddr,
                                   'apt-get install -y %s' % (packstr))

    def do_icicle(self, guestaddr):
        """
        Method to collect the package information and generate the ICICLE
        XML.
        """
        self.log.debug("Generating ICICLE")
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             'dpkg --get-selections',
                                                             timeout=30)

        # the data we get back from dpkg is in the form of:
        #
        # <package name>\t\t\tinstall
        #
        # so we have to strip out the tabs and the install before
        # passing it on to output_icicle_xml
        packages = []
        for line in stdout.split("\n"):
            packages.append(line.split("\t")[0])

        return self._output_icicle_xml(packages, self.tdl.description)

    def _get_kernel_from_txt_cfg(self, fetchurl):
        """
        Internal method to download and parse the txt.cfg file from a URL.  If
        the txt.cfg file does not exist, or it does not have the keys that we
        expect, this method raises an error.
        """
        txtcfgurl = fetchurl + "/ubuntu-installer/" + self.debarch + "/boot-screens/txt.cfg"

        # first we check if the txt.cfg exists; this throws an exception if
        # it is missing
        info = oz.ozutil.http_get_header(txtcfgurl)
        if info['HTTP-Code'] != 200:
            raise oz.OzException.OzException("Could not find %s" % (txtcfgurl))

        txtcfg = os.path.join(self.icicle_tmp, "txt.cfg")
        self.log.debug("Going to write txt.cfg to %s" % (txtcfg))
        txtcfgfd = os.open(txtcfg, os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        os.unlink(txtcfg)
        fp = os.fdopen(txtcfgfd)
        try:
            self.log.debug("Trying to get txt.cfg from " + txtcfgurl)
            oz.ozutil.http_download_file(txtcfgurl, txtcfgfd, False, self.log)

            # if we made it here, the txt.cfg existed.  Parse it and
            # find out the location of the kernel and ramdisk
            self.log.debug("Got txt.cfg, parsing")
            os.lseek(txtcfgfd, 0, os.SEEK_SET)
            grub_pattern = re.compile(r"^default\s*(?P<default_entry>\w+)$.*"
                                      r"^label\s*(?P=default_entry)$.*"
                                      r"^\s*kernel\s*(?P<kernel>\S+)$.*"
                                      r"initrd=(?P<initrd>\S+).*"
                                      r"^label", re.DOTALL | re.MULTILINE)
            config_text = fp.read()
            match = re.search(grub_pattern, config_text)
            kernel = match.group('kernel')
            initrd = match.group('initrd')
        finally:
            fp.close()

        if kernel is None or initrd is None:
            raise oz.OzException.OzException("Empty kernel or initrd")

        self.log.debug("Returning kernel %s and initrd %s" % (kernel, initrd))
        return (kernel, initrd)

    def _gzip_file(self, inputfile, outputmode):
        """
        Internal method to gzip a file and write it to the initrd.
        """
        with open(inputfile, 'rb') as f:
            gzf = gzip.GzipFile(self.initrdfname, mode=outputmode)
            try:
                gzf.writelines(f)
                gzf.close()
            except:
                # there is a bit of asymmetry here in that OSs that support cpio
                # archives have the initial initrdfname copied in the higher level
                # function, but we delete it here.  OSs that don't support cpio,
                # though, get the initrd created right here.  C'est le vie
                os.unlink(self.initrdfname)
                raise

    def _create_cpio_initrd(self, preseedpath):
        """
        Internal method to create a modified CPIO initrd
        """
        extrafname = os.path.join(self.icicle_tmp, "extra.cpio")
        self.log.debug("Writing cpio to %s" % (extrafname))
        cpiofiledict = {}
        cpiofiledict[preseedpath] = 'preseed.cfg'
        oz.ozutil.write_cpio(cpiofiledict, extrafname)

        try:
            shutil.copyfile(self.initrdcache, self.initrdfname)
            self._gzip_file(extrafname, 'ab')
        finally:
            os.unlink(extrafname)

    def _initrd_inject_preseed(self, fetchurl, force_download):
        """
        Internal method to download and inject a preseed file into an initrd.
        """
        # we first see if we can use direct kernel booting, as that is
        # faster than downloading the ISO
        kernel = None
        initrd = None
        try:
            (kernel, initrd) = self._get_kernel_from_txt_cfg(fetchurl)
        except:
            pass

        if kernel is None:
            self.log.debug("Kernel was None, trying ubuntu-installer/%s/linux" % (self.debarch))
            # we couldn't find the kernel in the txt.cfg, so try a
            # hard-coded path
            kernel = "ubuntu-installer/%s/linux" % (self.debarch)
        if initrd is None:
            self.log.debug("Initrd was None, trying ubuntu-installer/%s/initrd.gz" % (self.debarch))
            # we couldn't find the initrd in the txt.cfg, so try a
            # hard-coded path
            initrd = "ubuntu-installer/%s/initrd.gz" % (self.debarch)

        self._get_original_media('/'.join([self.url.rstrip('/'),
                                           kernel.lstrip('/')]),
                                 self.kernelcache, force_download)

        try:
            self._get_original_media('/'.join([self.url.rstrip('/'),
                                               initrd.lstrip('/')]),
                                     self.initrdcache, force_download)
        except:
            os.unlink(self.kernelfname)
            raise

        # if we made it here, then we can copy the kernel into place
        shutil.copyfile(self.kernelcache, self.kernelfname)

        try:
            preseedpath = os.path.join(self.icicle_tmp, "preseed.cfg")
            self._copy_preseed(preseedpath)

            try:
                self._create_cpio_initrd(preseedpath)
            finally:
                os.unlink(preseedpath)
        except:
            os.unlink(self.kernelfname)
            raise

    def generate_install_media(self, force_download=False,
                               customize_or_icicle=False):
        """
        Method to generate the install media for Ubuntu based operating
        systems.  If force_download is False (the default), then the
        original media will only be fetched if it is not cached locally.  If
        force_download is True, then the original media will be downloaded
        regardless of whether it is cached locally.
        """
        fetchurl = self.url
        if self.tdl.installtype == 'url':
            # set the fetchurl up-front so that if the OS doesn't support
            # initrd injection, or the injection fails for some reason, we
            # fall back to the mini.iso
            fetchurl += "/mini.iso"

            self.log.debug("Installtype is URL, trying to do direct kernel boot")
            try:
                return self._initrd_inject_preseed(self.url, force_download)
            except Exception as err:
                # if any of the above failed, we couldn't use the direct
                # kernel/initrd build method.  Fall back to trying to fetch
                # the mini.iso instead
                self.log.debug("Could not do direct boot, fetching mini.iso instead (the following error message is useful for bug reports, but can be ignored)")
                self.log.debug(err)

        return self._iso_generate_install_media(fetchurl, force_download,
                                                customize_or_icicle)

    def cleanup_install(self):
        """
        Method to cleanup any transient install data.
        """
        self.log.info("Cleaning up after install")

        for fname in [self.output_iso, self.initrdfname, self.kernelfname]:
            try:
                os.unlink(fname)
            except:
                pass

        if not self.cache_original_media:
            for fname in [self.orig_iso, self.kernelcache, self.initrdcache]:
                try:
                    os.unlink(fname)
                except:
                    pass

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Ubuntu installs.
    """
    if tdl.update in ["5.04", "5.10", "6.06", "6.06.1", "6.06.2", "6.10",
                      "7.04", "7.10"]:
        return UbuntuGuest(tdl, config, auto, output_disk, "initrd.gz",
                           netdev, diskbus, macaddress)
    if tdl.update in ["8.04", "8.04.1", "8.04.2", "8.04.3", "8.04.4", "8.10",
                      "9.04"]:
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return UbuntuGuest(tdl, config, auto, output_disk, "initrd.gz",
                           netdev, diskbus, macaddress)
    if tdl.update in ["9.10", "10.04", "10.04.1", "10.04.2", "10.04.3", "10.10",
                      "11.04", "11.10", "12.04", "12.04.1", "12.04.2",
                      "12.04.3", "12.10", "13.04", "13.10"]:
        if netdev is None:
            netdev = 'virtio'
        if diskbus is None:
            diskbus = 'virtio'
        return UbuntuGuest(tdl, config, auto, output_disk, "initrd.lz",
                           netdev, diskbus, macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Ubuntu: 5.04, 5.10, 6.06[.1,.2], 6.10, 7.04, 7.10, 8.04[.1,.2,.3,.4], 8.10, 9.04, 9.10, 10.04[.1,.2,.3], 10.10, 11.04, 11.10, 12.04[.1,.2,.3], 12.10, 13.04, 13.10"
