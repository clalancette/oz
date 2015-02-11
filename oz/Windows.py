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
Windows installation
"""

import base64
import random
import re
import libvirt
import lxml.etree
import os
import shutil
import time
import winrm

import oz.Guest
import oz.ozutil
import oz.OzException

class Windows(oz.Guest.CDGuest):
    """
    Shared Windows base class.
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk,
                                  netdev, "localtime", "usb", diskbus, True,
                                  False, macaddress)

        if self.tdl.key is None:
            raise oz.OzException.OzException("A key is required when installing Windows")

class Windows_v5(Windows):
    """
    Class for Windows versions based on kernel 5.x (2000, XP, and 2003).
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        Windows.__init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                         macaddress)

        if self.tdl.update == "2000" and self.tdl.arch != "i386":
            raise oz.OzException.OzException("Windows 2000 only supports i386 architecture")

        self.winarch = self.tdl.arch
        if self.winarch == "x86_64":
            self.winarch = "amd64"

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.debug("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage",
                                           "-b", "cdboot/boot.bin",
                                           "-no-emul-boot", "-boot-load-seg",
                                           "1984", "-boot-load-size", "4",
                                           "-iso-level", "2", "-J", "-l", "-D",
                                           "-N", "-joliet-long",
                                           "-relaxed-filenames", "-v",
                                           "-V", "Custom",
                                           "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

    def generate_diskimage(self, size=10, force=False):
        """
        Method to generate a diskimage.  By default, a blank diskimage of
        10GB will be created; the caller can override this with the size
        parameter, specified in GB.  If force is False (the default), then
        a diskimage will not be created if a cached JEOS is found.  If
        force is True, a diskimage will be created regardless of whether a
        cached JEOS exists.  See the oz-install man page for more
        information about JEOS caching.
        """
        createpart = False
        if self.tdl.update == "2000":
            # If given a blank diskimage, windows 2000 stops very early in
            # install with a message:
            #
            #  Setup has determined that your computer's starupt hard disk is
            #  new or has been erased...
            #
            # To avoid that message, create a partition table that spans
            # the entire disk
            createpart = True
        return self._internal_generate_diskimage(size, force, createpart)

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self._geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                      "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents, self.winarch, "winnt.sif")

        if self.default_auto_file():
            # if this is the oz default siffile, we modify certain parameters
            # to make installation succeed
            computername = "OZ" + str(random.randrange(1, 900000))

            def _sifsub(line):
                """
                Method that is called back from oz.ozutil.copy_modify_file() to
                modify sif files as appropriate for Windows 2000/XP/2003.
                """
                if re.match(" *ProductKey", line):
                    return "    ProductKey=" + self.tdl.key + "\n"
                elif re.match(" *ProductID", line):
                    return "    ProductID=" + self.tdl.key + "\n"
                elif re.match(" *ComputerName", line):
                    return "    ComputerName=" + computername + "\n"
                elif re.match(" *AdminPassword", line):
                    return "    AdminPassword=" + self.rootpw + "\n"
                else:
                    return line

            oz.ozutil.copy_modify_file(self.auto, outname, _sifsub)
        else:
            # if the user provided their own siffile, do not override their
            # choices; the user gets to keep both pieces if something breaks
            shutil.copy(self.auto, outname)

    def install(self, timeout=None, force=False):
        """
        Method to run the operating system installation.
        """
        internal_timeout = timeout
        if internal_timeout is None:
            internal_timeout = 3600
        return self._do_install(internal_timeout, force, 1)

class Windows_v6(Windows):
    """
    Class for Windows versions based on kernel 6.x (2008, 7, 2012, 8, and 8.1).
    """
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
        Windows.__init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                         macaddress)

        self.winarch = "x86"
        if self.tdl.arch == "x86_64":
            self.winarch = "amd64"

    def _generate_new_iso(self):
        """
        Method to create a new ISO based on the modified CD/DVD.
        """
        self.log.debug("Generating new ISO")
        # NOTE: Windows 2008 is very picky about which arguments to genisoimage
        # will generate a bootable CD, so modify these at your own risk
        oz.ozutil.subprocess_check_output(["genisoimage",
                                           "-b", "cdboot/boot.bin",
                                           "-no-emul-boot", "-c", "BOOT.CAT",
                                           "-iso-level", "2", "-J", "-l", "-D",
                                           "-N", "-joliet-long",
                                           "-relaxed-filenames", "-v",
                                           "-V", "Custom", "-udf",
                                           "-o", self.output_iso,
                                           self.iso_contents],
                                          printfn=self.log.debug)

    def _modify_iso(self):
        """
        Method to make the boot ISO auto-boot with appropriate parameters.
        """
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self._geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                      "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents, "autounattend.xml")

        if self.default_auto_file():
            # if this is the oz default unattend file, we modify certain
            # parameters to make installation succeed
            doc = lxml.etree.parse(self.auto)

            for component in doc.xpath('/ms:unattend/ms:settings/ms:component',
                                       namespaces={'ms':'urn:schemas-microsoft-com:unattend'}):
                component.set('processorArchitecture', self.winarch)

            keys = doc.xpath('/ms:unattend/ms:settings/ms:component/ms:ProductKey',
                             namespaces={'ms':'urn:schemas-microsoft-com:unattend'})
            if len(keys) != 1:
                raise oz.OzException.OzException("Invalid autounattend file; expected 1 key, saw %d" % (len(keys)))
            keys[0].text = self.tdl.key

            adminpw = doc.xpath('/ms:unattend/ms:settings/ms:component/ms:UserAccounts/ms:AdministratorPassword/ms:Value',
                                namespaces={'ms':'urn:schemas-microsoft-com:unattend'})
            if len(adminpw) != 1:
                raise oz.OzException.OzException("Invalid autounattend file; expected 1 admin password, saw %d" % (len(adminpw)))
            adminpw[0].text = self.rootpw

            autologinpw = doc.xpath('/ms:unattend/ms:settings/ms:component/ms:AutoLogon/ms:Password/ms:Value',
                                    namespaces={'ms':'urn:schemas-microsoft-com:unattend'})
            if len(autologinpw) != 1:
                raise oz.OzException.OzException("Invalid autounattend file; expected 1 auto logon password, saw %d" % (len(autologinpw)))
            autologinpw[0].text = self.rootpw

            f = open(outname, 'w')
            f.write(lxml.etree.tostring(doc, pretty_print=True))
            f.close()
        else:
            # if the user provided their own unattend file, do not override
            # their choices; the user gets to keep both pieces if something
            # breaks
            shutil.copy(self.auto, outname)

    def install(self, timeout=None, force=False):
        internal_timeout = timeout
        if internal_timeout is None:
            internal_timeout = 8500
        return self._do_install(internal_timeout, force, 2)

    def guest_execute_command(self, guestaddr, command, timeout=10):
        session_address = "http://%s:5985/wsman" % (guestaddr)
        s = winrm.Session(session_address, auth=('Administrator', self.rootpw))
        self.log.debug("Running %s on Windows guest %s" % (command, session_address))
        r = s.run_ps(command)
        return (r.std_out, r.std_err, r.status_code)

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
                self.guest_execute_command(guestaddr, 'shutdown -s -t 0')
            except:
                pass

            try:
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

    def _install_packages(self, guestaddr, packstr):
        self.guest_execute_command(guestaddr,
                                   'msiexec.exe /qn /i %s' % (packstr))

    def guest_live_upload(self, guestaddr, file_to_upload, destination,
                          timeout=10):
        with open (file_to_upload, "r") as myfile:
            data=myfile.read()
        script = """
$stream = [System.IO.StreamWriter] "%s"
$s = @"
%s
"@ | %%{ $_.Replace("`n","`r`n") }
$stream.WriteLine($s)
$stream.close()
        """ % (destination, data)
        self.log.info("Script to run: %s" % (script))
        encoded_script = base64.b64encode(script.encode("utf_16_le"))
        result = self.guest_execute_command(guestaddr, "powershell -encodedcommand %s" % (encoded_script))
        self.log.info("%s-%s-%s" % (result[0], result[1], result[2]))

    def _customize_files(self, guestaddr):
        """
        Method to upload the custom files specified in the TDL to the guest.
        """
        self.log.info("Uploading custom files")
        for name, fp in list(self.tdl.files.items()):
            # all of the self.tdl.files are named temporary files; we just need
            # to fetch the name out and have scp upload it
            self.log.info("Uploading: %s"%(name))
            self.guest_live_upload(guestaddr, fp.name, name)

    def _image_winrm_teardown_step_1(self, g_handle):
        """
        First step to undo _image_winrm_setup (delete WinRM config script)
        """
        self._guestfs_remove_if_exists(g_handle, '/config-winrm.bat')

    def _image_winrm_teardown_step_2(self, g_handle):
        """
        Second step to undo _image_winrm_setup (delete announce script)
        """
        self._guestfs_remove_if_exists(g_handle, '/send-announce.ps1')

    def _image_winrm_teardown_step_3(self, g_handle):
        """
        Third step to undo _image_winrm_setup (delete startup script)
        """
        self._guestfs_remove_if_exists(g_handle, '/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup/winrm-announce.bat')

    def _collect_teardown(self, libvirt_xml):
        """
        Method to reverse the changes done in _collect_setup.
        """
        self.log.info("Collection Teardown")

        g_handle = self._guestfs_handle_setup(libvirt_xml)

        try:
            self._image_winrm_teardown_step_1(g_handle)

            self._image_winrm_teardown_step_2(g_handle)

            self._image_winrm_teardown_step_3(g_handle)
        finally:
            self._guestfs_handle_cleanup(g_handle)
            shutil.rmtree(self.icicle_tmp)

    def _image_winrm_setup_step_1(self, g_handle):
        """
        First step for allowing remote access (configure WinRM)
        """
        # part 1; make sure WinRM is configured
        self.log.debug("Step 1: WinRM configuration")

        scriptfile = os.path.join(self.icicle_tmp, "script")

        with open(scriptfile, 'w') as f:
            f.write("""\
cmd /c winrm quickconfig -quiet
cmd /c winrm set winrm/config/service/Auth @{Basic="true"}
cmd /c winrm set winrm/config/service @{AllowUnencrypted="true"}
""")

        try:
            g_handle.upload(scriptfile,
                            '/config-winrm.bat')
        finally:
            os.unlink(scriptfile)

    def _image_winrm_setup_step_2(self, g_handle):
        """
        Second step for allowing remote access (make the guest announce itself)
        """
        # part 2; make sure the guest announces itself
        self.log.debug("Step 2: Guest announcement")

        scriptfile = os.path.join(self.icicle_tmp, "script")

        with open(scriptfile, 'w') as f:
            f.write("""\
$GuestIp = Get-WmiObject -Class Win32_NetworkAdapterConfiguration | Where {$_.IPEnabled } |Select-Object -expand IPAddress | Where-Object { ([Net.IPAddress]$_).AddressFamily -eq "InterNetwork" };
$port= new-Object System.IO.Ports.SerialPort COM2;
$port.open();
$port.WriteLine("!$GuestIp,%s!");
$port.Close();
""" % (self.uuid))

        try:
            g_handle.upload(scriptfile,
                            '/send-announce.ps1')
        finally:
            os.unlink(scriptfile)

    def _image_winrm_setup_step_3(self, g_handle):
        """
        Third step for allowing remote access (ensure both commands run on startup).
        """
        # part 3; run previous commands on startup
        self.log.debug("Step 3: Startup link")

        scriptfile = os.path.join(self.icicle_tmp, "script")

        with open(scriptfile, 'w') as f:
            f.write("""\
cmd /c %SystemDrive%\config-winrm.bat
powershell.exe -ExecutionPolicy ByPass -File %SystemDrive%\send-announce.ps1
""")

        try:
            g_handle.upload(scriptfile,
                            '/ProgramData/Microsoft/Windows/Start Menu/Programs/Startup/winrm-announce.bat')
        finally:
            os.unlink(scriptfile) 

    def _collect_setup(self, libvirt_xml):
        """
        Setup the guest for remote access.
        """
        self.log.info("Collection Setup")

        g_handle = self._guestfs_handle_setup(libvirt_xml)

        # we have to do 3 things to make sure we can WinRM into Windows:
        # 1)  Configure WinRM
        # 2)  Configure VM announcement of itself to the host
        # 3)  Make sure previous steps are run on startup

        try:
            try:
                self._image_winrm_setup_step_1(g_handle)

                try:
                    self._image_winrm_setup_step_2(g_handle)

                    try:
                        self._image_winrm_setup_step_3(g_handle)
                    except:
                        self._image_winrm_teardown_step_3(g_handle)
                        raise
                except:
                    self._image_winrm_teardown_step_2(g_handle)
                    raise
            except:
                self._image_winrm_teardown_step_1(g_handle)
                raise

        finally:
            self._guestfs_handle_cleanup(g_handle)

    def _test_winrm_connection(self, guestaddr):
        """
        Internal method to test out the WinRM connection before we try to use it.
        """
        count = 30
        success = False
        while count > 0:
            try:
                self.log.debug("Testing WinRM connection, try %d" % (count))
                start = time.time()
                self.guest_execute_command(guestaddr, 'dir', timeout=1)
                self.log.debug("Succeeded")
                success = True
                break
            except Exception:
                # ensure that we spent at least one second before trying again
                end = time.time()
                if (end - start) < 1:
                    time.sleep(1 - (end - start))
                count -= 1

        if not success:
            self.log.debug("Failed to connect to WinRM on running guest")
            raise oz.OzException.OzException("Failed to connect to WinRM on running guest")

    def do_customize(self, guestaddr):
        """
        Method to customize by installing additional packages and files.
        """
        if not self.tdl.packages and not self.tdl.files and not self.tdl.commands:
            # no work to do, just return
            return

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

    def customize(self, libvirt_xml):
        """
        Method to customize the operating system after installation.
        """

        self.log.info("Customizing image")

        if not self.tdl.packages and not self.tdl.files and not self.tdl.commands:
            self.log.info("No additional packages, files, or commands to install, skipping customization")
            return

        # when doing an oz-install with -g, this isn't necessary as it will
        # just replace the port with the same port.  However, it is very
        # necessary when doing an oz-customize since the serial port might
        # not match what is specified in the libvirt XML
        modified_xml = self._modify_libvirt_xml_for_serial(libvirt_xml)

        self._collect_setup(modified_xml)
        self.log.info("Customizing machine with UUID: %s" %(self.uuid))
        try:
            libvirt_dom = self.libvirt_conn.createXML(modified_xml, 0)

            try:
                guestaddr = None
                guestaddr = self._wait_for_guest_boot(libvirt_dom)
                self._test_winrm_connection(guestaddr)
                self.do_customize(guestaddr)
            finally:
                self._shutdown_guest(guestaddr, libvirt_dom)
        finally:
            self._collect_teardown(modified_xml)
            pass

        return None

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Windows installs.
    """
    if tdl.update in ["2000", "XP", "2003"]:
        return Windows_v5(tdl, config, auto, output_disk, netdev,
                          diskbus, macaddress)
    if tdl.update in ["2008", "7", "2012", "8", "8.1"]:
        return Windows_v6(tdl, config, auto, output_disk, netdev, diskbus,
                          macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Windows: 2000, XP, 2003, 7, 2008, 2012, 8, 8.1"
