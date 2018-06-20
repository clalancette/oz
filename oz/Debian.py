# Copyright (C) 2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2017  Chris Lalancette <clalancette@gmail.com>

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
Debian installation
"""

import gzip
import os
import re
import shutil
import textwrap

import oz.GuestFSManager
import oz.Linux
import oz.OzException
import oz.ozutil


class DebianConfiguration(object):
    """
    Configuration class for Debian installation.
    """
    def __init__(self, need_auto_direct, need_auto_iso, default_netdev,
                 default_diskbus):
        self._need_auto_direct = need_auto_direct
        self._need_auto_iso = need_auto_iso
        self._default_netdev = default_netdev
        self._default_diskbus = default_diskbus

    @property
    def need_auto_direct(self):
        """
        Property method for whether this version of Debian needs 'auto' on the
        command-line for direct installs.
        """
        return self._need_auto_direct

    @property
    def need_auto_iso(self):
        """
        Property method for whether this version of Debian needs 'auto' on the
        command-line for ISO installs.
        """
        return self._need_auto_iso

    @property
    def default_netdev(self):
        """
        Property method for the default netdev for this version of Debian.
        """
        return self._default_netdev

    @property
    def default_diskbus(self):
        """
        Property method for the default diskbus for this version of Debian.
        """
        return self._default_diskbus


version_to_config = {
    '9': DebianConfiguration(need_auto_direct=False, need_auto_iso=True,
                             default_netdev='virtio', default_diskbus='virtio'),
    '8': DebianConfiguration(need_auto_direct=False, need_auto_iso=True,
                             default_netdev='virtio', default_diskbus='virtio'),
    '7': DebianConfiguration(need_auto_direct=True, need_auto_iso=True,
                             default_netdev='virtio', default_diskbus='virtio'),
    '6': DebianConfiguration(need_auto_direct=False, need_auto_iso=False,
                             default_netdev='virtio', default_diskbus='virtio'),
    '5': DebianConfiguration(need_auto_direct=False, need_auto_iso=False,
                             default_netdev='virtio', default_diskbus='virtio'),
}


class DebianGuest(oz.Linux.LinuxCDGuest):
    """
    Class for Debian 5, 6, 7, 8, and 9 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        self.config = version_to_config[tdl.update]

        if netdev is None:
            netdev = self.config.default_netdev
        if diskbus is None:
            diskbus = self.config.default_diskbus
        oz.Linux.LinuxCDGuest.__init__(self, tdl, config, auto, output_disk,
                                       netdev, diskbus, True, True, macaddress)

        self.crond_was_active = False
        self.sshd_was_active = False
        self.sshd_config = textwrap.dedent(
            """\
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
        )

        self.tunnels = {}

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

    def _copy_preseed(self, outname):
        """
        Method to copy and modify an Debian style preseed file.
        """
        self.log.debug("Putting the preseed file in place")

        if self.default_auto_file():
            def _preseed_sub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify preseed files as appropriate for Debian.
                """
                if re.match('d-i passwd/root-password password', line):
                    return 'd-i passwd/root-password password ' + self.rootpw + '\n'
                elif re.match('d-i passwd/root-password-again password', line):
                    return 'd-i passwd/root-password-again password ' + self.rootpw + '\n'
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

        # arch == i386
        installdir = "/install.386"
        if self.tdl.arch == "x86_64":
            installdir = "/install.amd"

        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux", "isolinux.cfg")
        extra = ""
        if self.config.need_auto_iso:
            extra = "auto=true "

        with open(isolinuxcfg, 'w') as f:
            f.write(textwrap.dedent(
                """\
                default customiso
                timeout 1
                prompt 0
                label customiso
                  menu label ^Customiso
                  menu default
                  kernel %s/vmlinuz
                  append file=/cdrom/preseed/customiso.seed %sdebian-installer/\
locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto priority=\
critical initrd=%s/initrd.gz --
                """ % (installdir, extra, installdir)))

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
                                           "-v", "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        extra = ""
        if self.config.need_auto_direct:
            extra = "auto=true "
        cmdline = "priority=critical " + extra + "locale=en_US"
        return self._do_install(timeout, force, 0, self.kernelfname,
                                self.initrdfname, cmdline)

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
        g_handle.path_restore('/root/.ssh')

    def _image_ssh_teardown_step_2(self, g_handle):
        """
        Second step to undo _image_ssh_setup (reset sshd service).
        """
        self.log.debug("Teardown step 2")
        # remove custom sshd_config
        self.log.debug("Resetting sshd_config")
        g_handle.path_restore('/etc/ssh/sshd_config')

        # reset the service link
        self.log.debug("Resetting sshd service")
        if self.ssh_startuplink:
            g_handle.path_restore(self.ssh_startuplink)

    def _image_ssh_teardown_step_3(self, g_handle):
        """
        Fourth step to undo _image_ssh_setup (remove guest announcement).
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
        if self.cron_startuplink:
            g_handle.path_restore(self.cron_startuplink)

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

    def _image_ssh_setup_step_1(self, g_handle):
        """
        First step for allowing remote access (generate and upload ssh keys).
        """
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        g_handle.path_backup('/root/.ssh')
        g_handle.mkdir('/root/.ssh')

        g_handle.path_backup('/root/.ssh/authorized_keys')

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
        g_handle.path_backup(self.ssh_startuplink)
        g_handle.ln_sf('/etc/init.d/ssh', self.ssh_startuplink)

        sshd_config_file = os.path.join(self.icicle_tmp, "sshd_config")
        f = open(sshd_config_file, 'w')
        f.write(self.sshd_config)
        f.close()

        try:
            g_handle.path_backup('/etc/ssh/sshd_config')
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
        if not g_handle.exists('/usr/sbin/cron'):
            raise oz.OzException.OzException("cron not installed on the image, cannot continue")

        scriptfile = os.path.join(self.icicle_tmp, "script")
        f = open(scriptfile, 'w')
        f.write("#!/bin/bash\n")
        f.write("/bin/sleep 20\n")
        f.write("DEV=$(/usr/bin/awk '{if ($2 == 0) print $1}' /proc/net/route) &&\n")
        f.write('[ -z "$DEV" ] && exit 0\n')
        f.write("ADDR=$(/sbin/ip -4 -o addr show dev $DEV | /usr/bin/awk '{print $4}' | /usr/bin/cut -d/ -f1) &&\n")
        f.write('[ -z "$ADDR" ] && exit 0\n')
        f.write('echo -n "!$ADDR,%s!" > /dev/ttyS1\n' % (self.uuid))
        f.close()
        try:
            g_handle.upload(scriptfile, '/root/reportip')
            g_handle.chmod(0o755, '/root/reportip')
        finally:
            os.unlink(scriptfile)

        announcefile = os.path.join(self.icicle_tmp, "announce")
        f = open(announcefile, 'w')
        f.write('*/1 * * * * root /bin/bash -c "/root/reportip"\n')
        f.close()
        try:
            g_handle.upload(announcefile, '/etc/cron.d/announce')
        finally:
            os.unlink(announcefile)

        self.cron_startuplink = self._get_service_runlevel_link(g_handle,
                                                                'cron')
        g_handle.path_backup(self.cron_startuplink)
        g_handle.ln_sf('/etc/init.d/cron', self.cron_startuplink)

    def _collect_setup(self, libvirt_xml):
        """
        Setup the guest for remote access.
        """
        self.log.info("Collection Setup")

        g_handle = oz.GuestFSManager.GuestFSLibvirtFactory(libvirt_xml, self.libvirt_conn)
        g_handle.mount_partitions()

        # we have to do 3 things to make sure we can ssh into Debian
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

    def _discover_repo_locality(self, repo_url, guestaddr, certdict):
        """
        Internal method to discover whether a repository is reachable from the
        guest or not.  It is used by customize_repos to decide which method to
        use to reach the repository.
        """

    # FIXME: Make this work for signed repositories
    def _customize_repos(self, guestaddr):
        """
        Method to generate and upload custom repository files based on the TDL.
        """

        self.log.debug("Installing additional repository files")

        for repo in list(self.tdl.repositories.values()):
            self.guest_execute_command(guestaddr, "echo '%s' > /etc/apt/sources.list.d/%s" % (repo.url.strip('\'"'), repo.name + ".list"))
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
        stdout, stderr_unused, retcode_unused = self.guest_execute_command(guestaddr,
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
        txtcfgurl = fetchurl + "/debian-installer/" + self.debarch + "/boot-screens/txt.cfg"

        # first we check if the txt.cfg exists; this throws an exception if
        # it is missing
        info = oz.ozutil.http_get_header(txtcfgurl)
        if info['HTTP-Code'] != 200:
            raise oz.OzException.OzException("Could not find %s" % (txtcfgurl))

        txtcfg = os.path.join(self.icicle_tmp, "txt.cfg")
        self.log.debug("Going to write txt.cfg to %s", txtcfg)
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
            # FIXME: This pattern doesn't match for Debian
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

        self.log.debug("Returning kernel %s and initrd %s", kernel, initrd)
        return (kernel, initrd)

    def _gzip_file(self, inputfile, outputmode):
        """
        Internal method to gzip a file and write it to the initrd.
        """
        f = open(inputfile, 'rb')
        gzf = gzip.GzipFile(self.initrdfname, mode=outputmode)
        try:
            gzf.writelines(f)
            gzf.close()
            f.close()
        except:
            # there is a bit of asymmetry here in that OSs that support cpio
            # archives have the initial initrdfname copied in the higher level
            # function, but we delete it here.  OSs that don't support cpio,
            # though, get the initrd created right here.  C'est la vie
            os.unlink(self.initrdfname)
            raise

    def _create_cpio_initrd(self, preseedpath):
        """
        Internal method to create a modified CPIO initrd
        """
        extrafname = os.path.join(self.icicle_tmp, "extra.cpio")
        self.log.debug("Writing cpio to %s", extrafname)
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
        except Exception:
            pass

        if kernel is None:
            self.log.debug("Kernel was None, trying debian-installer/%s/linux", self.debarch)
            # we couldn't find the kernel in the txt.cfg, so try a
            # hard-coded path
            kernel = "debian-installer/%s/linux" % (self.debarch)
        if initrd is None:
            self.log.debug("Initrd was None, trying debian-installer/%s/initrd.gz", self.debarch)
            # we couldn't find the initrd in the txt.cfg, so try a
            # hard-coded path
            initrd = "debian-installer/%s/initrd.gz" % (self.debarch)

        (fd, outdir) = oz.ozutil.open_locked_file(self.kernelcache)

        try:
            self._get_original_media('/'.join([self.url.rstrip('/'),
                                               kernel.lstrip('/')]),
                                     fd, outdir, force_download)

            # if we made it here, then we can copy the kernel into place
            shutil.copyfile(self.kernelcache, self.kernelfname)
        finally:
            os.close(fd)

        (fd, outdir) = oz.ozutil.open_locked_file(self.initrdcache)

        try:
            try:
                self._get_original_media('/'.join([self.url.rstrip('/'),
                                                   initrd.lstrip('/')]),
                                         fd, outdir, force_download)
            except:
                os.unlink(self.kernelfname)
                raise
        finally:
            os.close(fd)

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

    def _remove_repos(self, guestaddr):
        # FIXME: until we switch over to doing repository add by hand (instead
        # of using add-apt-repository), we can't really reliably implement this
        pass

    def generate_install_media(self, force_download=False,
                               customize_or_icicle=False):
        """
        Method to generate the install media for Debian based operating
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
            except Exception:
                pass

        if not self.cache_original_media:
            for fname in [self.orig_iso, self.kernelcache, self.initrdcache]:
                try:
                    os.unlink(fname)
                except Exception:
                    pass


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Debian installs.
    """
    if tdl.update in version_to_config.keys():
        return DebianGuest(tdl, config, auto, output_disk, netdev, diskbus,
                           macaddress)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Debian: " + ", ".join(sorted(version_to_config.keys()))
