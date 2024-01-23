# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
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
Common methods for installing and configuring RedHat-based guests
"""

try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import gzip
import os
import re
import shutil

import oz.Guest
import oz.GuestFSManager
import oz.Linux
import oz.OzException
import oz.ozutil


class RedHatLinuxCDGuest(oz.Linux.LinuxCDGuest):
    """
    Class for RedHat-based CD guests.
    """
    def __init__(self, tdl, config, auto, output_disk, nicmodel, diskbus,
                 iso_allowed, url_allowed, initrdtype, macaddress):
        oz.Linux.LinuxCDGuest.__init__(self, tdl, config, auto, output_disk,
                                       nicmodel, diskbus, iso_allowed,
                                       url_allowed, macaddress)
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
Subsystem	sftp	/usr/libexec/openssh/sftp-server
"""

        # initrdtype is actually a tri-state:
        # None - don't try to do direct kernel/initrd boot
        # "cpio" - Attempt to do direct kernel/initrd boot with a gzipped CPIO
        #        archive
        # "ext2" - Attempt to do direct kernel/initrd boot with a gzipped ext2
        #         filesystem
        self.initrdtype = initrdtype

        self.kernelfname = os.path.join(self.output_dir,
                                        self.tdl.name + "-kernel")
        self.initrdfname = os.path.join(self.output_dir,
                                        self.tdl.name + "-ramdisk")
        self.kernelcache = os.path.join(self.data_dir, "kernels",
                                        self.tdl.distro + self.tdl.update + self.tdl.arch + "-kernel")
        self.initrdcache = os.path.join(self.data_dir, "kernels",
                                        self.tdl.distro + self.tdl.update + self.tdl.arch + "-ramdisk")

        self.cmdline = "inst.method=" + self.url + " inst.ks=file:/ks.cfg"
        # don't write the kickstart to the image, or else initial-setup
        # will think a root password has been set:
        # https://bugzilla.redhat.com/show_bug.cgi?id=2015490
        self.cmdline += " inst.nosave=output_ks"
        if self.tdl.kernel_param:
            self.cmdline += " " + self.tdl.kernel_param

        self.virtio_channel_name = None

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.debug("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage", "-r", "-T", "-J", "-joliet-long",
                                           "-V", "Custom", "-no-emul-boot",
                                           "-b", "isolinux/isolinux.bin",
                                           "-c", "isolinux/boot.cat",
                                           "-boot-load-size", "4",
                                           "-boot-info-table", "-v",
                                           "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

    def _check_iso_tree(self, customize_or_icicle):
        kernel = os.path.join(self.iso_contents, "isolinux", "vmlinuz")
        if not os.path.exists(kernel):
            raise oz.OzException.OzException("Fedora/Red Hat installs can only be done using a boot.iso (netinst) or DVD image (LiveCDs are not supported)")

    def _modify_isolinux(self, initrdline):
        """
        Method to modify the isolinux.cfg file on a RedHat style CD.
        """
        self.log.debug("Modifying isolinux.cfg")
        # append additional kernel params from the TDL to initrdline
        if self.tdl.kernel_param:
            initrdline += " " + self.tdl.kernel_param
        initrdline += '\n'
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")

        with open(isolinuxcfg, "w") as f:
            f.write("""\
default customiso
timeout 1
prompt 0
label customiso
  kernel vmlinuz
%s
""" % (initrdline))

    def _copy_kickstart(self, outname):
        """
        Method to copy and modify a RedHat style kickstart file.
        """
        self.log.debug("Putting the kickstart in place")

        if self.default_auto_file():
            def _kssub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify kickstart files as appropriate.
                """
                if re.match("^rootpw", line):
                    return "rootpw " + self.rootpw + '\n'
                return line

            oz.ozutil.copy_modify_file(self.auto, outname, _kssub)
        else:
            shutil.copy(self.auto, outname)

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

        return "/etc/rc.d/rc" + runlevel + ".d/S" + startlevel + service

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
        if g_handle.exists('/lib/systemd/system/sshd.service'):
            if not self.sshd_was_active:
                g_handle.rm('/etc/systemd/system/multi-user.target.wants/sshd.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'sshd')
            g_handle.path_restore(startuplink)

    def _image_ssh_teardown_step_3(self, g_handle):
        """
        Third step to undo _image_ssh_setup (reset iptables).
        """
        self.log.debug("Teardown step 3")
        # reset iptables
        self.log.debug("Resetting iptables rules")
        g_handle.path_restore('/etc/sysconfig/iptables')

    def _image_ssh_teardown_step_4(self, g_handle):
        """
        Fourth step to undo _image_ssh_setup (remove guest announcement).
        """
        self.log.debug("Teardown step 4")
        self.log.debug("Removing announcement to host")
        g_handle.remove_if_exists('/etc/NetworkManager/dispatcher.d/99-reportip')

        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        g_handle.remove_if_exists('/etc/cron.d/announce')

        # remove reportip
        self.log.debug("Removing reportip")
        g_handle.remove_if_exists('/root/reportip')

        # reset the service link
        self.log.debug("Resetting crond service")
        if g_handle.exists('/lib/systemd/system/crond.service'):
            if not self.crond_was_active:
                g_handle.rm('/etc/systemd/system/multi-user.target.wants/crond.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'crond')
            g_handle.path_restore(startuplink)

    def _image_ssh_teardown_step_5(self, g_handle):
        """
        Fifth step to undo _image_ssh_setup (reset SELinux).
        """
        self.log.debug("Teardown step 5")
        g_handle.path_restore("/etc/selinux/config")

    def _image_ssh_teardown_step_6(self, g_handle):
        """
        Sixth step to undo changes by the operating system.  For instance,
        during first boot openssh generates ssh host keys and stores them
        in /etc/ssh.  Since this image might be cached later on, this method
        removes those keys.
        """
        for key in g_handle.glob_expand("/etc/ssh/*_key*"):
            g_handle.remove_if_exists(key)

        # Remove any lease files; this is so that subsequent boots don't try
        # to connect to a DHCP server that is on a totally different network
        for lease in g_handle.glob_expand("/var/lib/dhclient/*.leases"):
            g_handle.rm(lease)

        for lease in g_handle.glob_expand("/var/lib/NetworkManager/*.lease"):
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

            self._image_ssh_teardown_step_5(g_handle)

            self._image_ssh_teardown_step_6(g_handle)
        finally:
            g_handle.cleanup()
            shutil.rmtree(self.icicle_tmp)

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

        if g_handle.exists('/lib/systemd/system/sshd.service'):
            if g_handle.exists('/etc/systemd/system/multi-user.target.wants/sshd.service'):
                self.sshd_was_active = True
            else:
                g_handle.ln_sf('/lib/systemd/system/sshd.service',
                               '/etc/systemd/system/multi-user.target.wants/sshd.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'sshd')
            g_handle.path_backup(startuplink)
            g_handle.ln_sf('/etc/init.d/sshd', startuplink)

        sshd_config_file = os.path.join(self.icicle_tmp, "sshd_config")
        with open(sshd_config_file, 'w') as f:
            f.write(self.sshd_config)

        try:
            g_handle.path_backup('/etc/ssh/sshd_config')
            g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
        finally:
            os.unlink(sshd_config_file)

    def _image_ssh_setup_step_3(self, g_handle):
        """
        Third step for allowing remote access (open up the firewall).
        """
        # part 3; open up iptables
        self.log.debug("Step 3: Open up the firewall")
        g_handle.path_backup('/etc/sysconfig/iptables')

    def _image_ssh_setup_step_4(self, g_handle):
        """
        Fourth step for allowing remote access (make the guest announce itself
        on bootup).
        """
        # part 4; make sure the guest announces itself
        self.log.debug("Step 4: Guest announcement")

        if self.tdl.arch in ['ppc64', 'ppc64le']:
            announce_device = '/dev/hvc1'
        elif self.tdl.arch == 's390x':
            announce_device = '/dev/sclp_line0'
        else:
            announce_device = '/dev/ttyS1'

        scriptfile = os.path.join(self.icicle_tmp, "script")

        if g_handle.exists("/etc/NetworkManager/dispatcher.d"):
            with open(scriptfile, 'w') as f:
                f.write("""\
#!/bin/bash

if [ "$1" != "lo" -a "$2" = "up" ]; then
    echo -n "!$DHCP4_IP_ADDRESS,%s!" > %s
fi
""" % (self.uuid, announce_device))

            try:
                g_handle.upload(scriptfile,
                                '/etc/NetworkManager/dispatcher.d/99-reportip')
                g_handle.chmod(0o755,
                               '/etc/NetworkManager/dispatcher.d/99-reportip')
            finally:
                os.unlink(scriptfile)

        if not g_handle.exists('/usr/sbin/crond'):
            raise oz.OzException.OzException("cron not installed on the image, cannot continue")

        with open(scriptfile, 'w') as f:
            f.write("""\
#!/bin/bash
DEV=$(/bin/awk '{if ($2 == 0) print $1}' /proc/net/route) &&
[ -z "$DEV" ] && exit 0
ADDR=$(/sbin/ip -4 -o addr show dev $DEV | /bin/awk '{print $4}' | /bin/cut -d/ -f1) &&
[ -z "$ADDR" ] && exit 0
echo -n "!$ADDR,%s!" > %s
""" % (self.uuid, announce_device))

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

        if g_handle.exists('/lib/systemd/system/crond.service'):
            if g_handle.exists('/etc/systemd/system/multi-user.target.wants/crond.service'):
                self.crond_was_active = True
            else:
                g_handle.ln_sf('/lib/systemd/system/crond.service',
                               '/etc/systemd/system/multi-user.target.wants/crond.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'crond')
            g_handle.path_backup(startuplink)
            g_handle.ln_sf('/etc/init.d/crond', startuplink)

    def _image_ssh_setup_step_5(self, g_handle):
        """
        Fifth step for allowing remote access (set SELinux to permissive).
        """
        # part 5; set SELinux to permissive mode so we don't have to deal with
        # incorrect contexts
        self.log.debug("Step 5: Set SELinux to permissive mode")
        g_handle.path_backup('/etc/selinux/config')

        selinuxfile = self.icicle_tmp + "/selinux"
        with open(selinuxfile, 'w') as f:
            f.write("SELINUX=permissive\n")
            f.write("SELINUXTYPE=targeted\n")

        try:
            g_handle.upload(selinuxfile, "/etc/selinux/config")
        finally:
            os.unlink(selinuxfile)

    def _collect_setup(self, libvirt_xml):
        """
        Setup the guest for remote access.
        """
        self.log.info("Collection Setup")

        g_handle = oz.GuestFSManager.GuestFSLibvirtFactory(libvirt_xml, self.libvirt_conn)
        g_handle.mount_partitions()

        # we have to do 5 things to make sure we can ssh into RHEL/Fedora:
        # 1)  Upload our ssh key
        # 2)  Make sure sshd is running on boot
        # 3)  Make sure that port 22 is open in the firewall
        # 4)  Make the guest announce itself to the host
        # 5)  Set SELinux to permissive mode

        try:
            try:
                self._image_ssh_setup_step_1(g_handle)

                try:
                    self._image_ssh_setup_step_2(g_handle)

                    try:
                        self._image_ssh_setup_step_3(g_handle)

                        try:
                            self._image_ssh_setup_step_4(g_handle)

                            try:
                                self._image_ssh_setup_step_5(g_handle)
                            except:
                                self._image_ssh_teardown_step_5(g_handle)
                                raise
                        except:
                            self._image_ssh_teardown_step_4(g_handle)
                            raise
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

    def _parse_treeinfo(self, fp):
        """
        Internal method to parse the treeinfo file and get the kernel and
        initrd paths out of it.
        """
        self.log.debug("Got treeinfo, parsing")
        try:
            config = configparser.SafeConfigParser()
            config.readfp(fp)
        except AttributeError:
            # SafeConfigParser was deprecated in Python 3.2 and readfp
            # was renamed to read_file
            config = configparser.ConfigParser()
            config.read_file(fp)
        section = "images-%s" % (self.tdl.arch)
        kernel = oz.ozutil.config_get_key(config, section, "kernel", None)
        initrd = oz.ozutil.config_get_key(config, section, "initrd", None)
        return (kernel, initrd)

    def _get_kernel_from_treeinfo(self, fetchurl):
        """
        Internal method to download and parse the .treeinfo file from a URL.  If
        the .treeinfo file does not exist, or it does not have the keys that we
        expect, this method raises an error.
        """
        treeinfourl = fetchurl + "/.treeinfo"

        # first we check if the .treeinfo exists; this throws an exception if
        # it is missing
        info = oz.ozutil.http_get_header(treeinfourl)
        if info['HTTP-Code'] != 200:
            raise oz.OzException.OzException("Could not find %s" % (treeinfourl))

        treeinfo = os.path.join(self.icicle_tmp, "treeinfo")
        self.log.debug("Going to write treeinfo to %s", treeinfo)
        treeinfofd = os.open(treeinfo, os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        fp = os.fdopen(treeinfofd)
        try:
            os.unlink(treeinfo)
            self.log.debug("Trying to get treeinfo from " + treeinfourl)
            oz.ozutil.http_download_file(treeinfourl, treeinfofd,
                                         False, self.log)

            # if we made it here, the .treeinfo existed.  Parse it and
            # find out the location of the vmlinuz and initrd
            fp.seek(0)
            (kernel, initrd) = self._parse_treeinfo(fp)
        finally:
            fp.close()

        if kernel is None or initrd is None:
            raise oz.OzException.OzException("Empty kernel or initrd")

        self.log.debug("Returning kernel %s and initrd %s", kernel, initrd)
        return (kernel, initrd)

    def _create_cpio_initrd(self, kspath):
        """
        Internal method to create a modified CPIO initrd
        """
        # if initrdtype is cpio, then we can just append a gzipped
        # archive onto the end of the initrd
        extrafname = os.path.join(self.icicle_tmp, "extra.cpio")
        self.log.debug("Writing cpio to %s", extrafname)
        cpiofiledict = {}
        cpiofiledict[kspath] = 'ks.cfg'
        oz.ozutil.write_cpio(cpiofiledict, extrafname)

        try:
            shutil.copyfile(self.initrdcache, self.initrdfname)
            oz.ozutil.gzip_append(extrafname, self.initrdfname)
        finally:
            os.unlink(extrafname)

    def _create_ext2_initrd(self, kspath):
        """
        Internal method to create a modified ext2 initrd
        """
        # in this case, the archive is not CPIO but is an ext2
        # filesystem.  use guestfs to mount it and add the kickstart
        self.log.debug("Creating temporary directory")
        tmpdir = os.path.join(self.icicle_tmp, "initrd")
        oz.ozutil.mkdir_p(tmpdir)

        ext2file = os.path.join(tmpdir, "initrd.ext2")
        self.log.debug("Uncompressing initrd %s to %s", self.initrdfname, ext2file)
        inf = gzip.open(self.initrdcache, 'rb')
        outf = open(ext2file, "w")
        try:
            outf.writelines(inf)
            inf.close()

            g_handle = oz.GuestFSManager.GuestFS(ext2file, 'raw')
            g_handle.mount_partitions()
            g_handle.upload(kspath, "/ks.cfg")
            g_handle.cleanup()

            # kickstart is added, lets recompress it
            oz.ozutil.gzip_create(ext2file, self.initrdfname)
        finally:
            os.unlink(ext2file)

    def _initrd_inject_ks(self, fetchurl, force_download):
        """
        Internal method to download and inject a kickstart into an initrd.
        """
        # we first see if we can use direct kernel booting, as that is
        # faster than downloading the ISO
        kernel = None
        initrd = None
        try:
            (kernel, initrd) = self._get_kernel_from_treeinfo(fetchurl)
        except Exception:
            pass

        if kernel is None:
            self.log.debug("Kernel was None, trying images/pxeboot/vmlinuz")
            # we couldn't find the kernel in the treeinfo, so try a
            # hard-coded path
            kernel = "images/pxeboot/vmlinuz"
        if initrd is None:
            self.log.debug("Initrd was None, trying images/pxeboot/initrd.img")
            # we couldn't find the initrd in the treeinfo, so try a
            # hard-coded path
            initrd = "images/pxeboot/initrd.img"

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

            try:
                kspath = os.path.join(self.icicle_tmp, "ks.cfg")
                self._copy_kickstart(kspath)

                try:
                    if self.initrdtype == "cpio":
                        self._create_cpio_initrd(kspath)
                    elif self.initrdtype == "ext2":
                        self._create_ext2_initrd(kspath)
                    else:
                        raise oz.OzException.OzException("Invalid initrdtype, this is a programming error")
                finally:
                    os.unlink(kspath)
            except:
                os.unlink(self.kernelfname)
                raise
        finally:
            os.close(fd)

    def generate_install_media(self, force_download=False,
                               customize_or_icicle=False):
        """
        Method to generate the install media for RedHat based operating
        systems.  If force_download is False (the default), then the
        original media will only be fetched if it is not cached locally.  If
        force_download is True, then the original media will be downloaded
        regardless of whether it is cached locally.
        """
        fetchurl = self.url
        if self.tdl.installtype == 'url':
            # set the fetchurl up-front so that if the OS doesn't support
            # initrd injection, or the injection fails for some reason, we
            # fall back to the boot.iso
            fetchurl += "/images/boot.iso"

            if self.initrdtype is not None:
                self.log.debug("Installtype is URL, trying to do direct kernel boot")
                try:
                    return self._initrd_inject_ks(self.url, force_download)
                except Exception as err:
                    # if any of the above failed, we couldn't use the direct
                    # kernel/initrd build method.  Fall back to trying to fetch
                    # the boot.iso instead
                    self.log.debug("Could not do direct boot, fetching boot.iso instead (the following error message is useful for bug reports, but can be ignored)")
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

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        return self._do_install(timeout, force, 0, self.kernelfname,
                                self.initrdfname, self.cmdline, None,
                                self.virtio_channel_name)


class RedHatLinuxCDYumGuest(RedHatLinuxCDGuest):
    """
    Class for RedHat-based CD guests with yum support.
    """
    def __init__(self, tdl, config, auto, output_disk, nicmodel, diskbus,
                 iso_allowed, url_allowed, initrdtype, macaddress, use_yum):
        oz.RedHat.RedHatLinuxCDGuest.__init__(self, tdl, config, auto,
                                              output_disk, nicmodel, diskbus,
                                              iso_allowed, url_allowed,
                                              initrdtype, macaddress)

        self.use_yum = use_yum

    def _check_url(self, iso=True, url=True):
        """
        Method to check if a URL specified by the user is one that will work
        with anaconda.
        """
        url = RedHatLinuxCDGuest._check_url(self, iso, url)

        if self.tdl.installtype == 'url':
            # The HTTP/1.1 specification allows for servers that don't support
            # byte ranges; if the client requests it and the server doesn't
            # support it, it is supposed to return a header that looks like:
            #
            #   Accept-Ranges: none
            #
            # You can see this in action by editing httpd.conf:
            #
            #   ...
            #   LoadModule headers_module
            #   ...
            #   Header set Accept-Ranges "none"
            #
            # and then trying to fetch a file with wget:
            #
            #   wget --header="Range: bytes=5-10" http://path/to/my/file
            #
            # Unfortunately, anaconda does not honor this server header, and
            # blindly requests a byte range anyway.  When this happens, the
            # server throws a "403 Forbidden", and the URL install fails.
            #
            # There is the additional problem of mirror lists.  If we take
            # the original URL that was given to us, and it happens to be
            # a redirect, then what can happen is that each individual package
            # during the install can come from a different mirror (some of
            # which may not support the byte ranges).  To avoid both of these
            # problems, resolve the (possible) redirect to a real mirror, and
            # check if we hit a server that doesn't support ranges.  If we do
            # hit one of these, try up to 5 times to redirect to a different
            # mirror.  If after this we still cannot find a server that
            # supports byte ranges, fail.
            count = 5
            while count > 0:
                info = oz.ozutil.http_get_header(url, redirect=False)

                if 'Accept-Ranges' in info and info['Accept-Ranges'] == "none":
                    if url == info['Redirect-URL']:
                        # optimization; if the URL we resolved to is exactly
                        # the same as what we started with, this is *not*
                        # a redirect, and we should fail immediately
                        count = 0
                        break

                    count -= 1
                    continue

                if 'Redirect-URL' in info and info['Redirect-URL'] is not None:
                    url = info['Redirect-URL']
                break

            if count == 0:
                raise oz.OzException.OzException("%s URL installs cannot be done using servers that don't accept byte ranges.  Please try another mirror" % (self.tdl.distro))

        return url

    def _customize_repos(self, guestaddr):
        """
        Method to generate and upload custom repository files based on the TDL.
        """
        self.log.debug("Installing additional repository files")

        for repo in list(self.tdl.repositories.values()):
            filename = repo.name.replace(" ", "_") + ".repo"
            localname = os.path.join(self.icicle_tmp, filename)
            with open(localname, 'w') as f:
                f.write("[%s]\n" % repo.name.replace(" ", "_"))
                f.write("name=%s\n" % repo.name)
                f.write("baseurl=%s\n" % repo.url)
                f.write("skip_if_unavailable=1\n")
                f.write("enabled=1\n")

                if repo.sslverify:
                    f.write("sslverify=1\n")
                else:
                    f.write("sslverify=0\n")

                if repo.signed:
                    f.write("gpgcheck=1\n")
                else:
                    f.write("gpgcheck=0\n")

            try:
                remotename = os.path.join("/etc/yum.repos.d/", filename)
                self.guest_live_upload(guestaddr, localname, remotename)
            finally:
                os.unlink(localname)

    def _install_packages(self, guestaddr, packstr):
        if self.use_yum:
            self.guest_execute_command(guestaddr, 'yum -y install %s' % (packstr))
        else:
            self.guest_execute_command(guestaddr, 'dnf -y install %s' % (packstr))

    def _remove_repos(self, guestaddr):
        for repo in list(self.tdl.repositories.values()):
            if not repo.persisted:
                filename = os.path.join("/etc/yum.repos.d",
                                        repo.name.replace(" ", "_") + ".repo")
                self.guest_execute_command(guestaddr, "rm -f " + filename,
                                           timeout=30)


class RedHatFDGuest(oz.Guest.FDGuest):
    """
    Class for RedHat-based floppy guests.
    """
    def __init__(self, tdl, config, auto, output_disk, nicmodel, diskbus,
                 macaddress):
        oz.Guest.FDGuest.__init__(self, tdl, config, auto, output_disk,
                                  nicmodel, None, None, diskbus, macaddress)

        if self.tdl.arch != "i386":
            raise oz.OzException.OzException("Invalid arch " + self.tdl.arch + "for " + self.tdl.distro + " guest")

    def _modify_floppy(self):
        """
        Method to make the floppy auto-boot with appropriate parameters.
        """
        oz.ozutil.mkdir_p(self.floppy_contents)

        self.log.debug("Putting the kickstart in place")

        output_ks = os.path.join(self.floppy_contents, "ks.cfg")

        if self.default_auto_file():
            def _kssub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify kickstart files as appropriate for RHL.
                """
                if re.match("^url", line):
                    return "url --url " + self.url + "\n"
                elif re.match("^rootpw", line):
                    return "rootpw " + self.rootpw + "\n"
                return line

            oz.ozutil.copy_modify_file(self.auto, output_ks, _kssub)
        else:
            shutil.copy(self.auto, output_ks)

        oz.ozutil.subprocess_check_output(["mcopy", "-i", self.output_floppy,
                                           output_ks, "::KS.CFG"],
                                          printfn=self.log.debug)

        self.log.debug("Modifying the syslinux.cfg")

        syslinux = os.path.join(self.floppy_contents, "SYSLINUX.CFG")
        with open(syslinux, 'w') as outfile:
            outfile.write("""\
default customboot
prompt 1
timeout 1
label customboot
  kernel vmlinuz
  append initrd=initrd.img lang= devfs=nomount ramdisk_size=9126 ks=floppy method=%s
""" % (self.url))

        # sometimes, syslinux.cfg on the floppy gets marked read-only.  Avoid
        # problems with the subsequent mcopy by marking it read/write.
        oz.ozutil.subprocess_check_output(["mattrib", "-r", "-i",
                                           self.output_floppy,
                                           "::SYSLINUX.CFG"],
                                          printfn=self.log.debug)

        oz.ozutil.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                           self.output_floppy, syslinux,
                                           "::SYSLINUX.CFG"],
                                          printfn=self.log.debug)

    def generate_install_media(self, force_download=False,
                               customize_or_icicle=False):
        """
        Method to generate the install media for RedHat based operating
        systems that install from floppy.  If force_download is False (the
        default), then the original media will only be fetched if it is
        not cached locally.  If force_download is True, then the original
        media will be downloaded regardless of whether it is cached locally.
        """
        self.log.info("Generating install media")

        if not force_download:
            if os.access(self.jeos_filename, os.F_OK):
                # if we found a cached JEOS, we don't need to do anything here;
                # we'll copy the JEOS itself later on
                return
            elif os.access(self.modified_floppy_cache, os.F_OK):
                self.log.info("Using cached modified media")
                shutil.copyfile(self.modified_floppy_cache, self.output_floppy)
                return

        # name of the output file
        (fd, outdir) = oz.ozutil.open_locked_file(self.orig_floppy)

        try:
            self._get_original_floppy(self.url + "/images/bootnet.img", fd,
                                      outdir, force_download)
            self._copy_floppy()
            try:
                self._modify_floppy()
                if self.cache_modified_media:
                    self.log.info("Caching modified media for future use")
                    shutil.copyfile(self.output_floppy, self.modified_floppy_cache)
            finally:
                self._cleanup_floppy()
        finally:
            os.close(fd)
