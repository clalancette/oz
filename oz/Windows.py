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

import random
import re
import os
import libxml2
import shutil
import parted
import hivex
import subprocess

import oz.Guest
import oz.ozutil
import oz.OzException

class Windows(oz.Guest.CDGuest):
    def __init__(self, tdl, config):
        oz.Guest.CDGuest.__init__(self, tdl, "rtl8139", "localtime", "usb",
                                  None, config)

        if self.tdl.key is None:
            raise oz.OzException.OzException("A key is required when installing Windows")

        self.url = self.check_url(self.tdl, iso=True, url=False)

    def generate_install_media(self, force_download=False):
        return self.iso_generate_install_media(self.url, force_download)

class Samba:
    def __init__(self):
        self.user = None
        self.password = None
        self.server = None
        self.path = None

    def __str__(self):
        return "server: %s, path: %s, user: %s, pw: %s" % (self.server, self.path, self.user, self.password)

class Windows2000andXPand2003(Windows):
    def __init__(self, tdl, config, auto):
        Windows.__init__(self, tdl, config)

        if self.tdl.update == "2000" and self.tdl.arch != "i386":
            raise oz.OzException.OzException("Windows 2000 only supports i386 architecture")

        self.siffile = auto
        if self.siffile is None:
            self.siffile = oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif")

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        oz.Guest.subprocess_check_output(["mkisofs", "-b", "cdboot/boot.bin",
                                          "-no-emul-boot", "-boot-load-seg",
                                          "1984", "-boot-load-size", "4",
                                          "-iso-level", "2", "-J", "-l", "-D",
                                          "-N", "-joliet-long",
                                          "-relaxed-filenames", "-v", "-v",
                                          "-V", "Custom",
                                          "-o", self.output_iso,
                                          self.iso_contents])

    def generate_diskimage(self, size=10, force=False):
        if not force and os.access(self.jeos_cache_dir, os.F_OK) and os.access(self.jeos_filename, os.F_OK):
            # if we found a cached JEOS, we don't need to do anything here;
            # we'll copy the JEOS itself later on
            return

        self.log.info("Generating %dGB diskimage for %s" % (size,
                                                            self.tdl.name))

        f = open(self.diskimage, "w")
        f.truncate(size * 1024 * 1024 * 1024)
        f.close()

        if self.tdl.update == "2000":
            # If given a blank diskimage, windows 2000 stops very early in
            # install with a message:
            #
            #  Setup has determined that your computer's starupt hard disk is
            #  new or has been erased...
            #
            # To avoid that message, just create a partition table that spans
            # the entire disk
            dev = parted.Device(self.diskimage)
            disk = parted.freshDisk(dev, 'msdos')
            constraint = parted.Constraint(device=dev)
            geom = parted.Geometry(device=dev, start=1, end=2)
            #                       end=(constraint.maxSize - 1))
            partition = parted.Partition(disk=disk,
                                         type=parted.PARTITION_NORMAL,
                                         geometry=geom)
            disk.addPartition(partition=partition, constraint=constraint)
            disk.commit()

    def get_windows_arch(self, tdl_arch):
        arch = tdl_arch
        if arch == "x86_64":
            arch = "amd64"
        return arch

    def modify_iso(self):
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self.geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                     "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents,
                               self.get_windows_arch(self.tdl.arch),
                               "winnt.sif")

        if self.siffile == oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.sif"):
            # if this is the oz default siffile, we modify certain parameters
            # to make installation succeed
            computername = "OZ" + str(random.randrange(1, 900000))

            def sifsub(line):
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

            self.copy_modify_file(self.siffile, outname, sifsub)
        else:
            # if the user provided their own siffile, do not override their
            # choices; the user gets to keep both pieces if something breaks
            shutil.copy(self.siffile, outname)

    def install(self, timeout=None, force=False):
        if not force and os.access(self.jeos_cache_dir, os.F_OK) and os.access(self.jeos_filename, os.F_OK):
            self.log.info("Found cached JEOS, using it")
            oz.ozutil.copyfile_sparse(self.jeos_filename, self.diskimage)
        else:
            self.log.info("Running install for %s" % (self.tdl.name))

            cddev = self.InstallDev("cdrom", self.output_iso, "hdc")

            if timeout is None:
                timeout = 3600

            dom = self.libvirt_conn.createXML(self.generate_xml("cdrom", cddev),
                                              0)
            self.wait_for_install_finish(dom, timeout)

            dom = self.libvirt_conn.createXML(self.generate_xml("hd", cddev), 0)
            self.wait_for_install_finish(dom, timeout)

            if self.cache_jeos:
                self.log.info("Caching JEOS")
                self.mkdir_p(self.jeos_cache_dir)
                oz.ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self.generate_xml("hd", None)

class Windows2008and7(Windows):
    def __init__(self, tdl, config, auto):
        Windows.__init__(self, tdl, config)

        self.unattendfile = auto
        if self.unattendfile is None:
            self.unattendfile = oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml")

    def generate_new_iso(self):
        self.log.debug("Generating new ISO")
        # NOTE: Windows 2008 is very picky about which arguments to mkisofs
        # will generate a bootable CD, so modify these at your own risk
        oz.Guest.subprocess_check_output(["mkisofs", "-b", "cdboot/boot.bin",
                                          "-no-emul-boot", "-c", "BOOT.CAT",
                                          "-iso-level", "2", "-J", "-l", "-D",
                                          "-N", "-joliet-long",
                                          "-relaxed-filenames", "-v", "-v",
                                          "-V", "Custom", "-udf",
                                          "-o", self.output_iso,
                                          self.iso_contents])

    def get_windows_arch(self, tdl_arch):
        arch = "x86"
        if tdl_arch == "x86_64":
            arch = "amd64"
        return arch

    def modify_iso(self):
        self.log.debug("Modifying ISO")

        os.mkdir(os.path.join(self.iso_contents, "cdboot"))
        self.geteltorito(self.orig_iso, os.path.join(self.iso_contents,
                                                     "cdboot", "boot.bin"))

        outname = os.path.join(self.iso_contents, "autounattend.xml")

        if self.unattendfile == oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-jeos.xml"):
            # if this is the oz default unattend file, we modify certain
            # parameters to make installation succeed
            doc = libxml2.parseFile(self.unattendfile)
            xp = doc.xpathNewContext()
            xp.xpathRegisterNs("ms", "urn:schemas-microsoft-com:unattend")

            for component in xp.xpathEval('/ms:unattend/ms:settings/ms:component'):
                component.setProp('processorArchitecture',
                                  self.get_windows_arch(self.tdl.arch))

            keys = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:ProductKey')
            keys[0].setContent(self.tdl.key)

            adminpw = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:UserAccounts/ms:AdministratorPassword/ms:Value')
            adminpw[0].setContent(self.rootpw)

            autologinpw = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:AutoLogon/ms:Password/ms:Value')
            autologinpw[0].setContent(self.rootpw)

            doc.saveFile(outname)
        else:
            # if the user provided their own unattend file, do not override
            # their choices; the user gets to keep both pieces if something
            # breaks
            shutil.copy(self.unattendfile, outname)

    def install(self, timeout=None, force=False):
        if not force and os.access(self.jeos_cache_dir, os.F_OK) and os.access(self.jeos_filename, os.F_OK):
            self.log.info("Found cached JEOS, using it")
            oz.ozutil.copyfile_sparse(self.jeos_filename, self.diskimage)
        else:
            self.log.info("Running install for %s" % (self.tdl.name))

            cddev = self.InstallDev("cdrom", self.output_iso, "hdc")

            if timeout is None:
                timeout = 6000

            dom = self.libvirt_conn.createXML(self.generate_xml("cdrom", cddev),
                                              0)
            self.wait_for_install_finish(dom, timeout)

            dom = self.libvirt_conn.createXML(self.generate_xml("hd", cddev), 0)
            self.wait_for_install_finish(dom, timeout)

            dom = self.libvirt_conn.createXML(self.generate_xml("hd", cddev), 0)
            self.wait_for_install_finish(dom, timeout)

            if self.cache_jeos:
                self.log.info("Caching JEOS")
                self.mkdir_p(self.jeos_cache_dir)
                oz.ozutil.copyfile_sparse(self.diskimage, self.jeos_filename)

        return self.generate_xml("hd", None)

    def guest_execute_command(self, guestaddr, command):
        admin = "Administrator%" + self.get_password()
        sub = subprocess.Popen(["winexe", "-U", admin, "//" + guestaddr,
                                "--runas=" + admin, command],
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
        result = sub.communicate()
        retcode = sub.poll()

        return (result[0], result[1], retcode)

    def get_password(self):
        doc = libxml2.parseFile(self.unattendfile)
        xp = doc.xpathNewContext()
        xp.xpathRegisterNs("ms", "urn:schemas-microsoft-com:unattend")

        passnode = xp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:UserAccounts/ms:AdministratorPassword/ms:Value')
        if len(passnode) == 1:
            password = passnode[0].getContent()
        else:
            self.log.warn("Could not find password from unattend file, using default")
            password = 'ozrootpw'

        doc.freeDoc()

        return password

    def sysprep_install_file(self, g_handle):
        sysprepfile = oz.ozutil.generate_full_auto_path("windows-" + self.tdl.update + "-sysprep.xml")

        outfile = os.path.join(self.icicle_tmp, "sysprep.xml")

        sysprepdoc = libxml2.parseFile(sysprepfile)
        sysprepxp = sysprepdoc.xpathNewContext()
        sysprepxp.xpathRegisterNs("ms", "urn:schemas-microsoft-com:unattend")

        for component in sysprepxp.xpathEval('/ms:unattend/ms:settings/ms:component'):
            component.setProp('processorArchitecture',
                              self.get_windows_arch(self.tdl.arch))

        command_notify = sysprepxp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:FirstLogonCommands/ms:SynchronousCommand/ms:CommandLine')
        command_notify[0].content = "C:\\Windows\\System32\\WindowsPowershell\\v1.0\\powershell.exe -ExecutionPolicy RemoteSigned -command Start-Sleep 5;$socket=new-object System.Net.Sockets.TcpClient;$socket.Connect(\'" + self.host_bridge_ip + "\'," + str(self.listen_port) + ")"
        command_notify[0].setContent(command_notify[0].content)

        command = sysprepxp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:FirstLogonCommands/ms:SynchronousCommand/ms:CommandLine')
        command[1].content = "cmd /C del /q /f c:\Windows\Windows-" + self.tdl.update + "-sysprep.xml"
        command[1].setContent(command[1].content)

        sysprep_os_password = sysprepxp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:UserAccounts/ms:AdministratorPassword/ms:Value')
        sysprep_os_password[0].setContent(self.get_password())

        sysprep_autologon_os_password = sysprepxp.xpathEval('/ms:unattend/ms:settings/ms:component/ms:AutoLogon/ms:Password/ms:Value')
        sysprep_autologon_os_password[0].setContent(self.get_password())

        sysprepdoc.saveFile(outfile)

        path = g_handle.case_sensitive_path("/Windows")
        g_handle.upload(outfile, path + "/sysprep.xml")

        os.unlink(outfile)

    def collect_setup(self, libvirt_xml):
        self.log.info("Collection Setup")

        self.mkdir_p(self.icicle_tmp)

        g_handle = self.guestfs_handle_setup(libvirt_xml)
        try:
            self.log.debug("Downloading ntuser.dat")
            ntuser = os.path.join(self.icicle_tmp, "ntuser.dat")
            path = g_handle.case_sensitive_path("/users/Administrator/ntuser.dat")
            g_handle.download(path, ntuser)

            self.log.debug("Modifying ntuser")
            hive = hivex.Hivex(ntuser, write=True)
            root = hive.root()
            software = hive.node_get_child(root, "Software")
            ms = hive.node_get_child(software, "Microsoft")
            windows = hive.node_get_child(ms, "Windows")
            currentversion = hive.node_get_child(windows, "CurrentVersion")
            runonce = hive.node_get_child(currentversion, "RunOnce")

            if runonce is None:
                runonce = hive.node_add_child(currentversion, "RunOnce")

            Key = "ReportIp".encode('utf-16le')
            Value = "C:\\Windows\\System32\\WindowsPowershell\\v1.0\\powershell.exe -ExecutionPolicy RemoteSigned \"&{Start-Sleep 10;$socket=new-object System.Net.Sockets.TcpClient;$socket.Connect(\'" + self.host_bridge_ip + "\'," + str(self.listen_port) + ")}\""
            Value = Value.encode('utf-16le')

            hive.node_set_value(runonce, {'key': Key, 't': 1, 'value': Value})

            hive.commit(None)

            self.log.debug("Uploading modified ntuser")
            g_handle.upload(ntuser, path)

            os.unlink(ntuser)

            self.sysprep_install_file(g_handle)
        finally:
            self.guestfs_handle_cleanup(g_handle)

    def collect_teardown(self, libvirt_xml):
        self.log.info("Collection Teardown")

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        try:
            pass
            # FIXME: we probably need to remove the sysprep file here
        finally:
            self.guestfs_handle_cleanup(g_handle)

    def copy_package(self, guestaddr, package, samba):
        self.log.info("Copying package %s" % package.name)
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             "cmd.exe /c net use \\\\" + samba.server + "\\" + samba.path + " " + samba.password + " /u:" + samba.user + " & xcopy \\\\" + samba.server + "\\" + samba.path + "\\" + package.filename + " c:\\temp\\ /S /I /Y")
        if retcode != 0:
            if stderr:
                raise oz.OzException.OzException("Failed to copy package %s with error %s" % (package.filename, stderr))
            else:
                raise oz.OzException.OzException("Failed to copy package %s, unknown error" % (package.filename))

    def delete_package(self, guestaddr, package):
        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             "cmd.exe /c del c:\\temp\\" + package.name)

    def install_package(self, guestaddr, package):
        share = self.tdl.repositories[package.repo]

        samba = Samba()

        matches = re.match(r'(smb|cifs)://(.*@)?(.*)$', share.url)
        if not matches:
            raise oz.OzException.OzException("Failed to identify repository share, must have syntax of smb://workgroup:username@server")

        userpw = matches.groups()[1]
        serverpath = matches.groups()[2]

        if userpw is not None:
            split = re.match(r'(.*?)([:].*)?@$', userpw)

            samba.user = split.groups()[0]

            if split.groups()[1] is not None:
                samba.password = split.groups()[1][1:]

        if serverpath is not None:
            split = re.match(r'(.*?)\\(.*)$', serverpath)

            samba.server = split.groups()[0]
            samba.path = split.groups()[1]

        self.log.debug("Original path: %s" % (share.url))
        self.log.debug("Samba %s" % (str(samba)))

        self.copy_package(guestaddr, package, samba)

        guestcmd = 'cmd.exe /c c:\\temp\\' + package.filename
        if package.args is not None:
            guestcmd += ' ' + package.args

        self.log.debug("Issuing install command")

        stdout, stderr, retcode = self.guest_execute_command(guestaddr,
                                                             guestcmd)
        # FIXME: check for errors here

        self.delete_package(guestaddr, package)

    def customize(self, libvirt_xml):
        self.log.info("Customization")

        if not self.tdl.packages:
            self.log.info("No additional packages to install, skipping customization")
            return

        self.collect_setup(libvirt_xml)

        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)
            try:
                guestaddr = self.wait_for_guest_boot()
            except:
                libvirt_dom.destroy()
                raise

            try:
                # first install all of the additional packages
                for package in self.tdl.packages:
                    self.install_package(guestaddr, package)

                # now sysprep the OS
                self.log.info("Starting sysprep")

                self.log.debug("Sysprep stage 1")
                sysprep_out, sysprep_err, sysprep_ret = self.guest_execute_command(guestaddr, "C:\\windows\\system32\\sysprep\\sysprep /oobe /generalize /unattend:c:\\windows\\sysprep.xml")
                if sysprep_ret != 0:
                    raise oz.OzException.OzException("Failed initial sysprep: %s" % (sysprep_err))
            except:
                # if installing a package or the first sysprep step threw an
                # error, the OS is still up, so we tell it to shutdown
                self.guest_execute_command(guestaddr,
                                           "cmd.exe /c shutdown /s /t 0")
                if not self.wait_for_guest_shutdown(libvirt_dom):
                    self.log.warn("Failed shutting down guest, forcibly killing")
                    libvirt_dom.destroy()
                raise

            try:
                # if the sysprep step was successful, the guest will shut
                # down on its own.  Wait around here for that to happen
                if not self.wait_for_guest_shutdown(libvirt_dom, count=600):
                    raise oz.OzException.OzException("Guest did not shut down in time, initial sysprep failed")

                self.log.debug("Sysprep stage 2")
                libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

                # when we launch the guest the second time, sysprep will
                # continue without input from us.  Just wait around for it
                # to shutdown again
                if not self.wait_for_guest_shutdown(libvirt_dom, count=600):
                    raise oz.OzException.OzException("Guest did not shut down in time, sysprep stage 2 failed")

                self.log.debug("Sysprep stage 3")
                libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

                guestaddr = self.wait_for_guest_boot()
                if not self.wait_for_guest_shutdown(libvirt_dom, count=600):
                    raise oz.OzException.OzException("Guest did not shut down in time, sysprep stage 3 failed")
            except:
                # if the guest did not shutdown properly during the end of
                # sysprep stage 1, sysprep stage 2, or sysprep stage 3,
                # forcibly kill it here
                if libvirt_dom:
                    libvirt_dom.destroy()
                raise
        finally:
            self.collect_teardown(libvirt_xml)

def get_class(tdl, config, auto):
    if tdl.update in ["2000", "XP", "2003"]:
        return Windows2000andXPand2003(tdl, config, auto)
    if tdl.update in ["2008", "7"]:
        return Windows2008and7(tdl, config, auto)
    raise oz.OzException.OzException("Unsupported Windows update " + tdl.update)
