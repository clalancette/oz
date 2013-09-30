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
import libvirt
import gzip

import oz.Guest
import oz.ozutil
import oz.OzException
import oz.linuxutil

class UbuntuGuest(oz.Guest.CDGuest):
    """
    Class for Ubuntu 5.04, 5.10, 6.06, 6.10, 7.04, 7.10, 8.04, 8.10, 9.04, 9.10, 10.04, 10.10, 11.04, 11.10, 12.04, 12.10, and 13.04 installation.
    """
    def __init__(self, tdl, config, auto, output_disk, initrd, nicmodel,
                 diskbus, macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk,
                                  nicmodel, None, None, diskbus, True, True,
                                  macaddress)

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
Subsystem       sftp    /usr/libexec/openssh/sftp-server
"""

        self.casper_initrd = initrd

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
        f = open(isolinuxcfg, 'w')

        if self.tdl.update in ["5.04", "5.10"]:
            f.write("DEFAULT /install/vmlinuz\n")
            f.write("APPEND initrd=/install/initrd.gz ramdisk_size=16384 root=/dev/rd/0 rw preseed/file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US kbd-chooser/method=us netcfg/choose_interface=auto keyboard-configuration/layoutcode=us debconf/priority=critical --\n")
            f.write("TIMEOUT 1\n")
            f.write("PROMPT 0\n")
        else:
            f.write("default customiso\n")
            f.write("timeout 1\n")
            f.write("prompt 0\n")
            f.write("label customiso\n")
            f.write("  menu label ^Customiso\n")
            f.write("  menu default\n")
            if os.path.isdir(os.path.join(self.iso_contents, "casper")):
                kernelname = "/casper/vmlinuz"
                # sigh.  Ubuntu 12.04.2, amd64 changed the name of the kernel
                # on the boot CD to "/casper/vmlinuz.efi".  Handle that here
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

        f.close()

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
        runlevel = oz.linuxutil.get_default_runlevel(g_handle)

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
        f = open(sshd_config_file, 'w')
        f.write(self.sshd_config)
        f.close()

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

    def _test_ssh_connection(self, guestaddr):
        """
        Internal method to test out the ssh connection before we try to use it.
        Under systemd, the IP address of a guest can come up and reportip can
        run before the ssh key is generated and sshd starts up.  This check makes
        sure that we allow an additional 30 seconds (1 second per ssh attempt)
        for sshd to finish initializing.
        """
        self.log.debug("Testing ssh connection")
        count = 30
        success = False
        while count > 0:
            try:
                stdout, stderr, retcode = self.guest_execute_command(guestaddr, 'ls', timeout=1)
                self.log.debug("Succeeded")
                success = True
                break
            except:
                count -= 1

        if not success:
            raise oz.OzException.OzException("Failed to connect to ssh on running guest")

    def _internal_customize(self, libvirt_xml, action):
        """
        Internal method to customize and optionally generate an ICICLE for the
        operating system after initial installation.
        """
        # the "action" input is actually a tri-state:
        # action = "gen_and_mod" means to generate the icicle and to
        #          potentially make modifications
        # action = "gen_only" means to generate the icicle only, and not
        #          look at any modifications
        # action = "mod_only" means to not generate the icicle, but still
        #          potentially make modifications

        self.log.info("Customizing image")

        if not self.tdl.packages and not self.tdl.files and not self.tdl.commands:
            if action == "mod_only":
                self.log.info("No additional packages, files, or commands to install, and icicle generation not requested, skipping customization")
                return
            elif action == "gen_and_mod":
                # It is actually possible to get here with a "gen_and_mod"
                # action but a TDL that contains no real customizations.
                # In the "safe ICICLE" code below it is important to know
                # when we are truly in a "gen_only" state so we modify
                # the action here if we detect that ICICLE generation is the
                # only task to be done.
                # FIXME: See about doing this test earlier or in a more generic
                # way
                self.log.debug("Asked to gen_and_mod but no mods are present - changing action to gen_only")
                action = "gen_only"

        # when doing an oz-install with -g, this isn't necessary as it will
        # just replace the port with the same port.  However, it is very
        # necessary when doing an oz-customize since the serial port might
        # not match what is specified in the libvirt XML
        modified_xml = self._modify_libvirt_xml_for_serial(libvirt_xml)

        if action == "gen_only" and self.safe_icicle_gen:
            # We are only generating ICICLE and the user has asked us to do
            # this without modifying the completed image by booting it.
            # Create a copy on write snapshot to use for ICICLE
            # generation - discard when finished
            cow_diskimage = self.diskimage + "-icicle-snap.qcow2"
            self._internal_generate_diskimage(force=True,
                                              backing_filename=self.diskimage,
                                              image_filename=cow_diskimage)
            modified_xml = self._modify_libvirt_xml_diskimage(modified_xml, cow_diskimage, 'qcow2')

        self._collect_setup(modified_xml)

        icicle = None
        try:
            libvirt_dom = self.libvirt_conn.createXML(modified_xml, 0)

            try:
                guestaddr = None
                guestaddr = self._wait_for_guest_boot(libvirt_dom)
                self._test_ssh_connection(guestaddr)

                if action == "gen_and_mod":
                    self.do_customize(guestaddr)
                    icicle = self.do_icicle(guestaddr)
                elif action == "gen_only":
                    icicle = self.do_icicle(guestaddr)
                elif action == "mod_only":
                    self.do_customize(guestaddr)
                else:
                    raise oz.OzException.OzException("Invalid customize action %s; this is a programming error" % (action))
            finally:
                if action == "gen_only" and self.safe_icicle_gen:
                    # if this is a gen_only and safe_icicle_gen, there is no
                    # reason to wait around for the guest to shutdown; we'll
                    # be removing the overlay file anyway.  Just destroy it
                    libvirt_dom.destroy()
                else:
                    self._shutdown_guest(guestaddr, libvirt_dom)
        finally:
            if action == "gen_only" and self.safe_icicle_gen:
                # no need to teardown because we simply discard the file
                # containing those changes
                os.unlink(cow_diskimage)
            else:
                self._collect_teardown(modified_xml)

        return icicle

    def _discover_repo_locality(self, repo_url, guestaddr, certdict):
        """
        Internal method to discover whether a repository is reachable from the
        guest or not.  It is used by customize_repos to decide which method to
        use to reach the repository.
        """

    def _customize_repos(self, guestaddr):
        """
        Method to generate and upload custom repository files based on the TDL.
        """

        self.log.debug("Installing additional repository files")

        for repo in list(self.tdl.repositories.values()):
            self.guest_execute_command(guestaddr, "apt-add-repository --yes '%s'" % (repo.url.strip('\'"')))
            self.guest_execute_command(guestaddr, "apt-get update")

    def do_customize(self, guestaddr):
        """
        Method to customize by installing additional packages and files.
        """
        if not self.tdl.packages and not self.tdl.files and not self.tdl.commands:
            # no work to do, just return
            return

        self._customize_repos(guestaddr)

        self.log.debug("Installing custom packages")
        packstr = ''
        for package in self.tdl.packages:
            packstr += package.name + ' '

        if packstr != '':
            self.guest_execute_command(guestaddr,
                                       'apt-get install -y %s' % (packstr),
                                       tunnels=None)

        self._customize_files(guestaddr)

        self.log.debug("Running custom commands")
        for cmd in self.tdl.commands:
            self.guest_execute_command(guestaddr, cmd.read())

        self.log.debug("Syncing")
        self.guest_execute_command(guestaddr, 'sync')

    def guest_execute_command(self, guestaddr, command, timeout=10,
                              tunnels=None):
        """
        Method to execute a command on the guest and return the output.
        """
        return oz.ozutil.ssh_execute_command(guestaddr, self.sshprivkey,
                                             command, timeout, tunnels)

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
        for name, fp in list(self.tdl.files.items()):
            # all of the self.tdl.files are named temporary files; we just need
            # to fetch the name out and have scp upload it
            self.guest_live_upload(guestaddr, fp.name, name)

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

    def customize(self, libvirt_xml):
        """
        Method to customize the operating system after installation.
        """
        return self._internal_customize(libvirt_xml, "mod_only")

    def customize_and_generate_icicle(self, libvirt_xml):
        """
        Method to customize and generate the ICICLE for an operating system
        after installation.  This is equivalent to calling customize() and
        generate_icicle() back-to-back, but is faster.
        """
        return self._internal_customize(libvirt_xml, "gen_and_mod")

    def generate_icicle(self, libvirt_xml):
        """
        Method to generate the ICICLE from an operating system after
        installation.  The ICICLE contains information about packages and
        other configuration on the diskimage.
        """
        return self._internal_customize(libvirt_xml, "gen_only")

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
                      "11.04", "11.10", "12.04", "12.04.1", "12.04.2", "12.04.3",
                      "12.10", "13.04"]:
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
    return "Ubuntu: 5.04, 5.10, 6.06[.1,.2], 6.10, 7.04, 7.10, 8.04[.1,.2,.3,.4], 8.10, 9.04, 9.10, 10.04[.1,.2,.3], 10.10, 11.04, 11.10, 12.04[.1,.2,.3], 12.10, 13.04"
