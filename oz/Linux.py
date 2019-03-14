# Copyright (C) 2013-2017  Chris Lalancette <clalancette@gmail.com>

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
Linux installation
"""

import os
import re
import time

import libvirt

import oz.Guest
import oz.OzException


class LinuxCDGuest(oz.Guest.CDGuest):
    """
    Class for Linux installation.
    """
    def __init__(self, tdl, config, auto, output_disk, nicmodel, diskbus,
                 iso_allowed, url_allowed, macaddress, useuefi):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk,
                                  nicmodel, None, None, diskbus, iso_allowed,
                                  url_allowed, macaddress, useuefi)

    def _test_ssh_connection(self, guestaddr):
        """
        Internal method to test out the ssh connection before we try to use it.
        Under systemd, the IP address of a guest can come up and reportip can
        run before the ssh key is generated and sshd starts up.  This check
        makes sure that we allow an additional 30 seconds (1 second per ssh
        attempt) for sshd to finish initializing.
        """
        count = 30
        success = False
        while count > 0:
            try:
                self.log.debug("Testing ssh connection, try %d", count)
                start = time.time()
                self.guest_execute_command(guestaddr, 'ls', timeout=1)
                self.log.debug("Succeeded")
                success = True
                break
            except oz.ozutil.SubprocessException:
                # ensure that we spent at least one second before trying again
                end = time.time()
                if (end - start) < 1:
                    time.sleep(1 - (end - start))
                count -= 1

        if not success:
            self.log.debug("Failed to connect to ssh on running guest")
            raise oz.OzException.OzException("Failed to connect to ssh on running guest")

    def get_default_runlevel(self, g_handle):
        """
        Function to determine the default runlevel based on the /etc/inittab.
        """
        runlevel = "3"
        if g_handle.exists('/etc/inittab'):
            lines = g_handle.cat('/etc/inittab').split("\n")
            for line in lines:
                if re.match('id:', line):
                    runlevel = line.split(':')[1]
                    break

        return runlevel

    def guest_execute_command(self, guestaddr, command, timeout=10):
        """
        Method to execute a command on the guest and return the output.
        """
        # ServerAliveInterval protects against NAT firewall timeouts
        # on long-running commands with no output
        #
        # PasswordAuthentication=no prevents us from falling back to
        # keyboard-interactive password prompting
        #
        # -F /dev/null makes sure that we don't use the global or per-user
        # configuration files

        return oz.ozutil.subprocess_check_output(["ssh", "-i", self.sshprivkey,
                                                  "-F", "/dev/null",
                                                  "-o", "ServerAliveInterval=30",
                                                  "-o", "StrictHostKeyChecking=no",
                                                  "-o", "ConnectTimeout=" + str(timeout),
                                                  "-o", "UserKnownHostsFile=/dev/null",
                                                  "-o", "PasswordAuthentication=no",
                                                  "-o", "IdentitiesOnly yes",
                                                  "root@" + guestaddr, command],
                                                 printfn=self.log.debug)

    def guest_live_upload(self, guestaddr, file_to_upload, destination,
                          timeout=10):
        """
        Method to copy a file to the live guest.
        """
        self.guest_execute_command(guestaddr,
                                   "mkdir -p " + os.path.dirname(destination),
                                   timeout)

        # ServerAliveInterval protects against NAT firewall timeouts
        # on long-running commands with no output
        #
        # PasswordAuthentication=no prevents us from falling back to
        # keyboard-interactive password prompting
        #
        # -F /dev/null makes sure that we don't use the global or per-user
        # configuration files
        return oz.ozutil.subprocess_check_output(["scp", "-i", self.sshprivkey,
                                                  "-F", "/dev/null",
                                                  "-o", "ServerAliveInterval=30",
                                                  "-o", "StrictHostKeyChecking=no",
                                                  "-o", "ConnectTimeout=" + str(timeout),
                                                  "-o", "UserKnownHostsFile=/dev/null",
                                                  "-o", "PasswordAuthentication=no",
                                                  "-o", "IdentitiesOnly yes",
                                                  file_to_upload,
                                                  "root@" + guestaddr + ":" + destination],
                                                 printfn=self.log.debug)

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
            # sometimes the ssh process gets disconnected before it can return
            # cleanly (particularly when the guest is running systemd).  If that
            # happens, ssh returns 255, guest_execute_command throws an
            # exception, and the guest is forcibly destroyed.  While this
            # isn't the end of the world, it isn't desirable.  To avoid
            # this, we catch any exception thrown by ssh during the shutdown
            # command and throw them away.  In the (rare) worst case, the
            # shutdown will not have made it to the guest and we'll have to wait
            # 90 seconds for wait_for_guest_shutdown to timeout and forcibly
            # kill the guest.
            try:
                self.guest_execute_command(guestaddr, 'shutdown -h now')
            except Exception:
                pass

            try:
                if not self._wait_for_guest_shutdown(libvirt_dom):
                    self.log.warning("Guest did not shutdown in time, going to kill")
                else:
                    libvirt_dom = None
            except Exception:
                self.log.warning("Failed shutting down guest, forcibly killing")

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

    def _collect_setup(self, libvirt_xml):  # pylint: disable=unused-argument
        """
        Default method to set the guest up for remote access.
        """
        raise oz.OzException.OzException("ICICLE generation and customization is not implemented for guest %s" % (self.tdl.distro))

    def _collect_teardown(self, libvirt_xml):  # pylint: disable=unused-argument
        """
        Method to reverse the changes done in _collect_setup.
        """
        raise oz.OzException.OzException("ICICLE generation and customization is not implemented for guest %s" % (self.tdl.distro))

    def _install_packages(self, guestaddr, packstr):  # pylint: disable=unused-argument
        """
        Internal method to install packages; expected to be overriden by
        child classes.
        """
        raise oz.OzException.OzException("Customization is not implemented for guest %s" % (self.tdl.distro))

    def _customize_repos(self, guestaddr):  # pylint: disable=unused-argument
        """
        Internal method to customize repositories; expected to be overriden by
        child classes.
        """
        raise oz.OzException.OzException("Customization is not implemented for guest %s" % (self.tdl.distro))

    def _remove_repos(self, guestaddr):  # pylint: disable=unused-argument
        """
        Internal method to remove repositories; expected to be overriden by
        child classes.
        """
        raise oz.OzException.OzException("Repository removal not implemented for guest %s" % (self.tdl.distro))

    def do_customize(self, guestaddr):
        """
        Method to customize by installing additional packages and files.
        """
        if not self.tdl.packages and not self.tdl.files and not self.tdl.commands:
            # no work to do, just return
            return

        self._customize_repos(guestaddr)

        for cmd in self.tdl.precommands:
            self.guest_execute_command(guestaddr, cmd.read())

        self.log.debug("Installing custom packages")
        packstr = ''
        for package in self.tdl.packages:
            packstr += '"' + package.name + '" '

        if packstr != '':
            self._install_packages(guestaddr, packstr)

        self._customize_files(guestaddr)

        self.log.debug("Running custom commands")
        for cmd in self.tdl.commands:
            self.guest_execute_command(guestaddr, cmd.read())

        self.log.debug("Removing non-persisted repos")
        self._remove_repos(guestaddr)

        self.log.debug("Syncing")
        self.guest_execute_command(guestaddr, 'sync')

    def do_icicle(self, guestaddr):
        """
        Default method to collect the package information and generate the
        ICICLE XML.
        """
        raise oz.OzException.OzException("ICICLE generation is not implemented for this guest type")

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
