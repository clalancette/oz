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

"""
Common methods for installing and configuring RedHat-based guests
"""

import re
import os
import shutil
import urllib2
import libvirt
import ConfigParser
import gzip
import guestfs
import threading
import random

import oz.Guest
import oz.ozutil
import oz.OzException
import oz.proxy

class RedHatCDGuest(oz.Guest.CDGuest):
    """
    Class for RedHat-based CD guests.
    """
    def __init__(self, tdl, nicmodel, diskbus, config, stock_ks, iso_allowed,
                 url_allowed, initrdtype):
        oz.Guest.CDGuest.__init__(self, tdl, nicmodel, None, None, diskbus,
                                  config, iso_allowed, url_allowed)
        self.sshprivkey = os.path.join('/etc', 'oz', 'id_rsa-icicle-gen')
        self.crond_was_active = False
        self.sshd_was_active = False
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

        self.stock_ks = stock_ks

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
        self.cmdline = "method=" + self.url + " ks=file:/ks.cfg"

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.debug("Generating new ISO")
        oz.ozutil.subprocess_check_output(["mkisofs", "-r", "-T", "-J",
                                           "-V", "Custom", "-no-emul-boot",
                                           "-b", "isolinux/isolinux.bin",
                                           "-c", "isolinux/boot.cat",
                                           "-boot-load-size", "4",
                                           "-boot-info-table", "-v", "-v",
                                           "-o", self.output_iso,
                                           self.iso_contents])

    def _check_iso_tree(self):
        kernel = os.path.join(self.iso_contents, "isolinux", "vmlinuz")
        if not os.path.exists(kernel):
            raise oz.OzException.OzException("Fedora/Red Hat installs can only be done using a boot.iso (netinst) or DVD image (LiveCDs are not supported)")

    def _modify_isolinux(self, initrdline):
        """
        Method to modify the isolinux.cfg file on a RedHat style CD.
        """
        self.log.debug("Modifying isolinux.cfg")
        isolinuxcfg = os.path.join(self.iso_contents, "isolinux",
                                   "isolinux.cfg")

        f = open(isolinuxcfg, "w")
        f.write("default customiso\n")
        f.write("timeout 1\n")
        f.write("prompt 0\n")
        f.write("label customiso\n")
        f.write("  kernel vmlinuz\n")
        f.write(initrdline)
        f.close()

    def _copy_kickstart(self, outname):
        """
        Method to copy and modify a RedHat style kickstart file.
        """
        self.log.debug("Putting the kickstart in place")

        if self.auto is None:
            def _kssub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify kickstart files as appropriate.
                """
                if re.match("^rootpw", line):
                    return "rootpw " + self.rootpw + '\n'
                else:
                    return line

            oz.ozutil.copy_modify_file(oz.ozutil.generate_full_auto_path(self.stock_ks),
                                       outname, _kssub)
        else:
            shutil.copy(self.auto, outname)

    def _get_default_runlevel(self, g_handle):
        """
        Method to determine the default runlevel based on the /etc/inittab.
        """
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

    def _get_service_runlevel_link(self, g_handle, service):
        """
        Method to find the runlevel link(s) for a service based on the name
        and the (detected) default runlevel.
        """
        runlevel = self._get_default_runlevel(g_handle)

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

    def _image_ssh_teardown_step_1(self, g_handle):
        """
        First step to undo _image_ssh_setup (remove authorized keys).
        """
        self.log.debug("Teardown step 1")
        # reset the authorized keys
        self.log.debug("Resetting authorized_keys")
        if g_handle.exists('/root/.ssh'):
            g_handle.rm_rf('/root/.ssh')

        if g_handle.exists('/root/.ssh.icicle'):
            g_handle.mv('/root/.ssh.icicle', '/root/.ssh')

    def _image_ssh_teardown_step_2(self, g_handle):
        """
        Second step to undo _image_ssh_setup (reset sshd service).
        """
        self.log.debug("Teardown step 2")
        # remove custom sshd_config
        self.log.debug("Resetting sshd_config")
        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.rm('/etc/ssh/sshd_config')
        if g_handle.exists('/etc/ssh/sshd_config.icicle'):
            g_handle.mv('/etc/ssh/sshd_config.icicle', '/etc/ssh/sshd_config')

        # reset the service link
        self.log.debug("Resetting sshd service")
        if g_handle.exists('/lib/systemd/system/sshd.service'):
            if not self.sshd_was_active:
                g_handle.rm('/etc/systemd/system/multi-user.target.wants/sshd.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'sshd')
            if g_handle.exists(startuplink):
                g_handle.rm(startuplink)
            if g_handle.exists(startuplink + ".icicle"):
                g_handle.mv(startuplink + ".icicle", startuplink)

    def _image_ssh_teardown_step_3(self, g_handle):
        """
        Third step to undo _image_ssh_setup (reset iptables).
        """
        self.log.debug("Teardown step 3")
        # reset iptables
        self.log.debug("Resetting iptables rules")
        if g_handle.exists('/etc/sysconfig/iptables'):
            g_handle.rm('/etc/sysconfig/iptables')
        if g_handle.exists('/etc/sysconfig/iptables.icicle'):
            g_handle.mv('/etc/sysconfig/iptables.icicle',
                        '/etc/sysconfig/iptables')

    def _image_ssh_teardown_step_4(self, g_handle):
        """
        Fourth step to undo _image_ssh_setup (remove guest announcement).
        """
        self.log.debug("Teardown step 4")
        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        if g_handle.exists('/etc/cron.d/announce'):
            g_handle.rm('/etc/cron.d/announce')

        # remove reportip
        self.log.debug("Removing reportip")
        if g_handle.exists('/root/reportip'):
            g_handle.rm('/root/reportip')

        # reset the service link
        self.log.debug("Resetting crond service")
        if g_handle.exists('/lib/systemd/system/crond.service'):
            if not self.crond_was_active:
                g_handle.rm('/etc/systemd/system/multi-user.target.wants/crond.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'crond')
            if g_handle.exists(startuplink):
                g_handle.rm(startuplink)
            if g_handle.exists(startuplink + ".icicle"):
                g_handle.mv(startuplink + ".icicle", startuplink)

    def _image_ssh_teardown_step_5(self, g_handle):
        """
        Fifth step to undo _image_ssh_setup (reset SELinux).
        """
        self.log.debug("Teardown step 5")
        if g_handle.exists('/etc/selinux/config'):
            g_handle.rm('/etc/selinux/config')

        if g_handle.exists('/etc/selinux/config.icicle'):
            g_handle.mv('/etc/selinux/config.icicle', '/etc/selinux/config')

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

            self._image_ssh_teardown_step_5(g_handle)
        finally:
            self._guestfs_handle_cleanup(g_handle)
            shutil.rmtree(self.icicle_tmp)

    def _image_ssh_setup_step_1(self, g_handle):
        """
        First step for allowing remote access (generate and upload ssh keys).
        """
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if g_handle.exists('/root/.ssh'):
            g_handle.mv('/root/.ssh', '/root/.ssh.icicle')
        g_handle.mkdir('/root/.ssh')

        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.mv('/root/.ssh/authorized_keys',
                        '/root/.ssh/authorized_keys.icicle')

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

    def _image_ssh_setup_step_3(self, g_handle):
        """
        Third step for allowing remote access (open up the firewall).
        """
        # part 3; open up iptables
        self.log.debug("Step 3: Open up the firewall")
        if g_handle.exists('/etc/sysconfig/iptables'):
            g_handle.mv('/etc/sysconfig/iptables',
                        '/etc/sysconfig/iptables.icicle')
        # implicit else; if there is no iptables file, the firewall is open

    def _image_ssh_setup_step_4(self, g_handle):
        """
        Fourth step for allowing remote access (make the guest announce itself
        on bootup).
        """
        # part 4; make sure the guest announces itself
        self.log.debug("Step 4: Guest announcement")
        if not g_handle.exists('/usr/sbin/crond'):
            raise oz.OzException.OzException("cron not installed on the image, cannot continue")

        scriptfile = os.path.join(self.icicle_tmp, "script")
        f = open(scriptfile, 'w')
        f.write("#!/bin/bash\n")
        f.write("DEV=$(/bin/awk '{if ($2 == 0) print $1}' /proc/net/route) &&\n")
        f.write('[ -z "$DEV" ] && exit 0\n')
        f.write("ADDR=$(/sbin/ip -4 -o addr show dev $DEV | /bin/awk '{print $4}' | /bin/cut -d/ -f1) &&\n")
        f.write('[ -z "$ADDR" ] && exit 0\n')
        f.write('echo -n "!$ADDR,%s!" > /dev/ttyS0\n' % (self.uuid))
        f.close()

        try:
            announcefile = os.path.join(self.icicle_tmp, "announce")
            f = open(announcefile, 'w')
            f.write('*/1 * * * * root /bin/bash -c "/root/reportip"\n')
            f.close()

            try:
                g_handle.upload(scriptfile, '/root/reportip')
                g_handle.chmod(0755, '/root/reportip')
                g_handle.upload(announcefile, '/etc/cron.d/announce')
            finally:
                os.unlink(announcefile)
        finally:
            os.unlink(scriptfile)

        if g_handle.exists('/lib/systemd/system/crond.service'):
            if g_handle.exists('/etc/systemd/system/multi-user.target.wants/crond.service'):
                self.crond_was_active = True
            else:
                g_handle.ln_sf('/lib/systemd/system/crond.service',
                               '/etc/systemd/system/multi-user.target.wants/crond.service')
        else:
            startuplink = self._get_service_runlevel_link(g_handle, 'crond')
            if g_handle.exists(startuplink):
                g_handle.mv(startuplink, startuplink + ".icicle")
            g_handle.ln_sf('/etc/init.d/crond', startuplink)

    def _image_ssh_setup_step_5(self, g_handle):
        """
        Fifth step for allowing remote access (set SELinux to permissive).
        """
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

    def _collect_setup(self, libvirt_xml):
        """
        Setup the guest for remote access.
        """
        self.log.info("Collection Setup")

        oz.ozutil.mkdir_p(self.icicle_tmp)

        g_handle = self._guestfs_handle_setup(libvirt_xml)

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
            self._guestfs_handle_cleanup(g_handle)

    def guest_execute_command(self, guestaddr, command, timeout=10):
        """
        Method to execute a command on the guest and return the output.
        """
        return oz.ozutil.ssh_execute_command(guestaddr, self.sshprivkey,
                                             command, timeout)

    def guest_execute_command_tunnel(self, guestaddr, remoteport, localport,
                                     command, timeout=10):
        # ServerAliveInterval protects against NAT firewall timeouts
        # on long-running commands with no output
        # PasswordAuthentication=no prevents us from falling back to
        # keyboard-interactive password prompting
        return oz.Guest.subprocess_check_output(["ssh", "-i", self.sshprivkey,
                                                 "-o", "ServerAliveInterval=30",
                                                 "-o", "StrictHostKeyChecking=no",
                                                 "-o", "ConnectTimeout=" + str(timeout),
                                                 "-o", "UserKnownHostsFile=/dev/null",
                                                 "-o", "PasswordAuthentication=no",
                                                 "-R", "%s:localhost:%s" % (remoteport, localport),
                                                 "root@" + guestaddr, command])

    def do_icicle(self, guestaddr):
        """
        Method to collect the package information and generate the ICICLE XML.
        """
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             'rpm -qa')

        return self._output_icicle_xml(stdout.split("\n"),
                                       self.tdl.description)

    def generate_icicle(self, libvirt_xml):
        """
        Method to generate the ICICLE from an operating system after
        installation.  The ICICLE contains information about packages and
        other configuration on the diskimage.
        """
        self.log.info("Generating ICICLE")

        # when doing an oz-install with -g, this isn't necessary as it will
        # just replace the port with the same port.  However, it is very
        # necessary when doing an oz-customize since the serial port might
        # not match what is specified in the libvirt XML
        modified_xml = self._modify_libvirt_xml_for_serial(libvirt_xml)

        self._collect_setup(modified_xml)

        icicle_output = ''
        libvirt_dom = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(modified_xml, 0)

            try:
                guestaddr = None
                guestaddr = self._wait_for_guest_boot(libvirt_dom)
                icicle_output = self.do_icicle(guestaddr)
            finally:
                self._shutdown_guest(guestaddr, libvirt_dom)

        finally:
            self._collect_teardown(modified_xml)

        return icicle_output

    def guest_live_upload(self, guestaddr, file_to_upload, destination,
                          timeout=10):
        """
        Method to copy a file to the live guest.
        """
        return oz.ozutil.scp_copy_file(guestaddr, self.sshprivkey,
                                       file_to_upload, destination, timeout)

    def _customize_files(self, guestaddr):
        """
        Method to upload the custom files specified in the TDL to the guest.
        """
        self.log.info("Uploading custom files")
        for name, content in self.tdl.files.items():
            localname = os.path.join(self.icicle_tmp, "file")
            f = open(localname, 'w')
            f.write(content)
            f.close()
            self.guest_live_upload(guestaddr, localname, name)
            os.unlink(localname)

    def _shutdown_guest(self, guestaddr, libvirt_dom):
        """
        Method to shutdown the guest (gracefully at first, then with prejudice).
        """
        if guestaddr is not None:
            try:
                self.guest_execute_command(guestaddr, 'shutdown -h now')
                if not self._wait_for_guest_shutdown(libvirt_dom):
                    self.log.warn("Guest did not shutdown in time, going to kill")
                else:
                    libvirt_dom = None
            except:
                self.log.warn("Failed shutting down guest, forcibly killing")

        if libvirt_dom is not None:
            try:
                libvirt_dom.destroy()
            except libvirt.libvirtError:
                # the destroy failed for some reason.  This can happen if
                # _wait_for_guest_shutdown times out, but the domain shuts
                # down before we get to destroy.  Check to make sure that the
                # domain is gone from the list of running domains; if so, just
                # continue on; if not, re-raise the error.
                for domid in self.libvirt_conn.listDomainsID():
                    if domid == libvirt_dom.ID():
                        raise

    def _get_kernel_from_treeinfo(self, fetchurl):
        """
        Internal method to download and parse the .treeinfo file from a URL.
        """
        kernel = None
        initrd = None

        oz.ozutil.mkdir_p(self.icicle_tmp)
        treeinfo = os.path.join(self.icicle_tmp, "treeinfo")
        self.log.debug("Going to write treeinfo to %s" % (treeinfo))
        treeinfofd = os.open(treeinfo, os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        os.unlink(treeinfo)
        fp = os.fdopen(treeinfofd)
        try:
            self.log.debug("Trying to get treeinfo from " + fetchurl + "/.treeinfo")
            self._download_file(fetchurl + "/.treeinfo", treeinfofd, 0)

            # if we made it here, the .treeinfo existed.  Parse it and
            # find out the location of the vmlinuz and initrd
            self.log.debug("Got treeinfo, parsing")
            os.lseek(treeinfofd, 0, os.SEEK_SET)
            config = ConfigParser.SafeConfigParser()
            config.readfp(fp)
            section = "images-%s" % (self.tdl.arch)
            kernel = oz.ozutil.config_get_key(config, section, "kernel", None)
            initrd = oz.ozutil.config_get_key(config, section, "initrd", None)
        except:
            # OK, it looks like the .treeinfo didn't exist
            self.log.debug(".treeinfo didn't exist!")
        finally:
            fp.close()

        self.log.debug("Returning kernel %s and initrd %s" % (kernel, initrd))
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
            # though, get the initrd created right here.  C'est le vie
            os.unlink(self.initrdfname)
            raise

    def _initrd_inject_ks(self, fetchurl, force_download):
        """
        Internal method to download and inject a kickstart into an initrd.
        """
        # we first see if we can use direct kernel booting, as that is
        # faster than downloading the ISO
        (kernel, initrd) = self._get_kernel_from_treeinfo(fetchurl)

        if kernel is None:
            self.log.debug("Kernel was None, so hardcoding to images/pxeboot/vmlinuz")
            # we couldn't find the kernel in the treeinfo, so try a
            # hard-coded path
            kernel = "images/pxeboot/vmlinuz"
        if initrd is None:
            self.log.debug("Initrd was None, so hardcoding to images/pxeboot/initrd.img")
            # we couldn't find the initrd in the treeinfo, so try a
            # hard-coded path
            initrd = "images/pxeboot/initrd.img"

        kernelcache = os.path.join(self.data_dir, "kernels",
                                   self.tdl.distro + self.tdl.update + self.tdl.arch + "-kernel")
        initrdcache = os.path.join(self.data_dir, "kernels",
                                   self.tdl.distro + self.tdl.update + self.tdl.arch + "-ramdisk")

        self._get_original_media('/'.join([self.url.rstrip('/'),
                                           kernel.lstrip('/')]),
                                 kernelcache, force_download)

        try:
            self._get_original_media('/'.join([self.url.rstrip('/'),
                                               initrd.lstrip('/')]),
                                     initrdcache, force_download)
        except:
            os.unlink(self.kernelfname)
            raise

        # if we made it here, then we can copy the kernel into place
        shutil.copyfile(kernelcache, self.kernelfname)

        try:
            kspath = os.path.join(self.icicle_tmp, self.stock_ks)
            self._copy_kickstart(kspath)

            try:
                if self.initrdtype == "cpio":
                    # if initrdtype is cpio, then we can just append a gzipped
                    # archive onto the end of the initrd
                    extrafname = os.path.join(self.icicle_tmp, "extra.cpio")
                    self.log.debug("Writing cpio to %s" % (extrafname))
                    cpiofiledict = {}
                    cpiofiledict[kspath] = 'ks.cfg'
                    oz.ozutil.write_cpio(cpiofiledict, extrafname)

                    try:
                        shutil.copyfile(initrdcache, self.initrdfname)
                        self._gzip_file(extrafname, 'ab')
                    finally:
                        os.unlink(extrafname)
                elif self.initrdtype == "ext2":
                    # in this case, the archive is not CPIO but is an ext2
                    # filesystem.  use guestfs to mount it and add the kickstart
                    self.log.debug("Creating temporary directory")
                    tmpdir = os.path.join(self.icicle_tmp, "initrd")
                    oz.ozutil.mkdir_p(tmpdir)

                    ext2file = os.path.join(tmpdir, "initrd.ext2")
                    self.log.debug("Uncompressing initrd %s to %s" % (self.initrdfname, ext2file))
                    inf = gzip.open(initrdcache, 'rb')
                    outf = open(ext2file, "w")
                    try:
                        outf.writelines(inf)
                        inf.close()

                        g = guestfs.GuestFS()
                        g.add_drive_opts(ext2file, format='raw')
                        self.log.debug("Launching guestfs")
                        g.launch()

                        g.mount_options('', g.list_devices()[0], "/")

                        g.upload(kspath, "/ks.cfg")

                        g.sync()
                        g.umount_all()
                        g.kill_subprocess()

                        # kickstart is added, lets recompress it
                        self._gzip_file(ext2file, 'wb')
                    finally:
                        os.unlink(ext2file)
                else:
                    raise oz.OzException.OzException("Invalid initrdtype, this is a programming error")
            finally:
                os.unlink(kspath)
        except:
            os.unlink(self.kernelfname)
            raise

    def generate_install_media(self, force_download=False):
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
                except Exception, err:
                    # if any of the above failed, we couldn't use the direct
                    # kernel/initrd build method.  Fall back to trying to fetch
                    # the boot.iso instead
                    self.log.debug("Could not do direct boot, fetching boot.iso instead (the following error message is useful for bug reports, but can be ignored)")
                    self.log.debug(err)

        return self._iso_generate_install_media(fetchurl, force_download)

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
            try:
                os.unlink(self.orig_iso)
            except:
                pass

class RedHatCDYumGuest(RedHatCDGuest):
    """
    Class for RedHat-based CD guests with yum support.
    """
    def _check_url(self, iso=True, url=True):
        """
        Method to check if a URL specified by the user is one that will work
        with anaconda.
        """
        url = RedHatCDGuest._check_url(self, iso, url)

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
                response = urllib2.urlopen(url)
                info = response.info()
                new_url = response.geturl()
                response.close()

                self.log.debug("Original URL %s resolved to %s" % (url,
                                                                   new_url))

                if 'Accept-Ranges' in info and info['Accept-Ranges'] == "none":
                    if url == new_url:
                        # optimization; if the URL we resolved to is exactly
                        # the same as what we started with, this is *not*
                        # a redirect, and we should fail immediately
                        count = 0
                        break

                    count -= 1
                    continue

                url = new_url
                break

            if count == 0:
                raise oz.OzException.OzException("%s URL installs cannot be done using servers that don't accept byte ranges.  Please try another mirror" % (self.tdl.distro))

        return url

    def _customize_repos(self, guestaddr):
        """
        Method to generate and upload custom repository files based on the TDL.
        """
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
        """
        Method to customize by installing additional packages and files.
        """
        self._customize_repos(guestaddr)

        self.log.debug("Installing custom packages")
        packstr = ''
        for package in self.tdl.packages.list:
            packstr += package.name + ' '

        if packstr != '':
            if self.tdl.packages.packtype == 'proxy':
                # if we are doing a proxy install, we need to do a number of
                # things:
                # 1)  setup /etc/yum.conf to use a proxy
                # 2)  Fire off the proxy server
                # 3)  ssh into the guest with a valid -R

                remoteport = random.randrange(1024, 65535)
                localport = random.randrange(1024, 65535)
                # FIXME: we need to undo the yum changes when we are done
                self.guest_execute_command(guestaddr,
                                           'sed -i -e "s/\[main\]/\[main\]\\nproxy=http:\/\/localhost:%d/" /etc/yum.conf' % (remoteport))

                # FIXME: hardcoded port here, choose one dynamically
                proxy_server = oz.proxy.ThreadingHTTPServer(('0.0.0.0',
                                                             localport),
                                                            oz.proxy.ProxyHandler)
                proxy_thread = threading.Thread(target=proxy_server.serve_forever)
                proxy_thread.setDaemon(True)
                proxy_thread.start()
                self.guest_execute_command_tunnel(guestaddr, str(remoteport),
                                                  str(localport),
                                                  "yum -y install %s" % (packstr))
                proxy_server.shutdown()
            else:
                self.guest_execute_command(guestaddr,
                                           'yum -y install %s' % (packstr))

        self._customize_files(guestaddr)

        self.log.debug("Running custom commands")
        for content in self.tdl.commands.values():
            self.guest_execute_command(guestaddr, content)

        self.log.debug("Syncing")
        self.guest_execute_command(guestaddr, 'sync')

    def _internal_customize(self, libvirt_xml, generate_icicle):
        """
        Internal method to customize and optionally generate an ICICLE for the
        operating system after initial installation.
        """
        self.log.info("Customizing image")

        if not self.tdl.packages and not self.tdl.files and not self.tdl.commands and not generate_icicle:
            self.log.info("No additional packages, files, or commands to install, and icicle generation not requested, skipping customization")
            return

        # when doing an oz-install with -g, this isn't necessary as it will
        # just replace the port with the same port.  However, it is very
        # necessary when doing an oz-customize since the serial port might
        # not match what is specified in the libvirt XML
        modified_xml = self._modify_libvirt_xml_for_serial(libvirt_xml)

        self._collect_setup(modified_xml)

        icicle = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(modified_xml, 0)

            try:
                guestaddr = None
                guestaddr = self._wait_for_guest_boot(libvirt_dom)

                if self.tdl.packages or self.tdl.files or self.tdl.commands:
                    self.do_customize(guestaddr)

                if generate_icicle:
                    self.log.debug("Generating ICICLE")
                    icicle = self.do_icicle(guestaddr)
            finally:
                self._shutdown_guest(guestaddr, libvirt_dom)
        finally:
            self._collect_teardown(modified_xml)

        return icicle

    def customize(self, libvirt_xml):
        """
        Method to customize the operating system after installation.
        """
        return self._internal_customize(libvirt_xml, False)

    def customize_and_generate_icicle(self, libvirt_xml):
        """
        Method to customize and generate the ICICLE for an operating system
        after installation.  This is equivalent to calling customize() and
        generate_icicle() back-to-back, but is faster.
        """
        return self._internal_customize(libvirt_xml, True)

class RedHatFDGuest(oz.Guest.FDGuest):
    """
    Class for RedHat-based floppy guests.
    """
    def __init__(self, tdl, config, auto, ks_name, nicmodel):
        oz.Guest.FDGuest.__init__(self, tdl, nicmodel, None, None, None, config)

        if self.tdl.arch != "i386":
            raise oz.OzException.OzException("Invalid arch " + self.tdl.arch + "for " + self.tdl.distro + " guest")

        self.ks_name = ks_name

        self.ks_file = auto
        if self.ks_file is None:
            self.ks_file = oz.ozutil.generate_full_auto_path(self.ks_name)

    def _modify_floppy(self):
        """
        Method to make the floppy auto-boot with appropriate parameters.
        """
        oz.ozutil.mkdir_p(self.floppy_contents)

        self.log.debug("Putting the kickstart in place")

        output_ks = os.path.join(self.floppy_contents, "ks.cfg")

        if self.ks_file == oz.ozutil.generate_full_auto_path(self.ks_name):
            def _kssub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify kickstart files as appropriate for RHL.
                """
                if re.match("^url", line):
                    return "url --url " + self.url + "\n"
                elif re.match("^rootpw", line):
                    return "rootpw " + self.rootpw + "\n"
                else:
                    return line

            oz.ozutil.copy_modify_file(self.ks_file, output_ks, _kssub)
        else:
            shutil.copy(self.ks_file, output_ks)

        oz.ozutil.subprocess_check_output(["mcopy", "-i", self.output_floppy,
                                           output_ks, "::KS.CFG"])

        self.log.debug("Modifying the syslinux.cfg")

        syslinux = os.path.join(self.floppy_contents, "SYSLINUX.CFG")
        outfile = open(syslinux, "w")
        outfile.write("default customboot\n")
        outfile.write("prompt 1\n")
        outfile.write("timeout 1\n")
        outfile.write("label customboot\n")
        outfile.write("  kernel vmlinuz\n")
        outfile.write("  append initrd=initrd.img lang= devfs=nomount ramdisk_size=9216 ks=floppy method=" + self.url + "\n")
        outfile.close()

        # sometimes, syslinux.cfg on the floppy gets marked read-only.  Avoid
        # problems with the subsequent mcopy by marking it read/write.
        oz.ozutil.subprocess_check_output(["mattrib", "-r", "-i",
                                           self.output_floppy,
                                           "::SYSLINUX.CFG"])

        oz.ozutil.subprocess_check_output(["mcopy", "-n", "-o", "-i",
                                           self.output_floppy, syslinux,
                                           "::SYSLINUX.CFG"])

    def generate_install_media(self, force_download=False):
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

        self._get_original_floppy(self.url + "/images/bootnet.img",
                                  force_download)
        self._copy_floppy()
        try:
            self._modify_floppy()
            if self.cache_modified_media:
                self.log.info("Caching modified media for future use")
                shutil.copyfile(self.output_floppy, self.modified_floppy_cache)
        finally:
            self._cleanup_floppy()
