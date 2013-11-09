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
import libvirt
import time

import oz.Guest
import oz.ozutil
import oz.OzException
import oz.linuxutil

class OpenSUSEGuest(oz.Guest.CDGuest):
    """
    Class for OpenSUSE installation.
    """
    def __init__(self, tdl, config, auto, output_disk, nicmodel, diskbus,
                 macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk,
                                  nicmodel, None, None, diskbus, True, False,
                                  macaddress)

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

    def guest_execute_command(self, guestaddr, command, timeout=10):
        """
        Method to execute a command on the guest and return the output.
        """
        return oz.ozutil.ssh_execute_command(guestaddr, self.sshprivkey,
                                             command, timeout)

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
        self._guestfs_path_restore(g_handle, '/etc/init.d/after.local')

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
        runlevel = oz.linuxutil.get_default_runlevel(g_handle)
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
        if not g_handle.exists('/etc/init.d/cron') or not g_handle.exists('/usr/sbin/cron'):
            raise oz.OzException.OzException("cron not installed on the image, cannot continue")

        scriptfile = os.path.join(self.icicle_tmp, "script")
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

        runlevel = oz.linuxutil.get_default_runlevel(g_handle)
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

        self._customize_files(guestaddr)

        self.log.debug("Running custom commands")
        for cmd in self.tdl.commands:
            self.guest_execute_command(guestaddr, cmd.read())

        self.log.debug("Syncing")
        self.guest_execute_command(guestaddr, 'sync')

    def _test_ssh_connection(self, guestaddr):
        """
        Internal method to test out the ssh connection before we try to use it.
        Under systemd, the IP address of a guest can come up and reportip can
        run before the ssh key is generated and sshd starts up.  This check
        makes sure that we allow an additional 30 seconds (1 second per ssh
        attempt) for sshd to finish initializing.
        """
        self.log.debug("Testing ssh connection")
        count = 30
        success = False
        while count > 0:
            try:
                self.log.debug("Testing ssh connection, try %d" % (count))
                start = time.time()
                stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                                     'ls',
                                                                     timeout=1)
                self.log.debug("Succeeded")
                success = True
                break
            except:
                # ensure that we spent at least one second before trying again
                end = time.time()
                if (end - start) < 1:
                    time.sleep(1 - (end - start))
                count -= 1

        if not success:
            self.log.debug("Failed to connect to ssh on running guest")
            raise oz.OzException.OzException("Failed to connect to ssh on running guest")

    def _internal_customize(self, libvirt_xml, action):
        """
        Internal method to customize and optionally generate an ICICLE for the
        operating system after initial installation.
        """
        # the "action" input is actually a tri-state:
        # action = "gen_and_mode" means to generate the icicle and to
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
