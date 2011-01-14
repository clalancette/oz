import Guest
import subprocess
import re
import os
import ozutil

class RedHatCDGuest(Guest.CDGuest):
    def __init__(self, distro, update, arch, installtype, nicmodel, clockoffset,
                 mousetype, diskbus, config):
        Guest.CDGuest.__init__(self, distro, update, arch, installtype,
                               nicmodel, clockoffset, mousetype, diskbus,
                               config)
        self.sshprivkey = self.icicle_tmp + '/id_rsa-icicle-gen'

    def generate_iso(self):
        self.log.debug("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-T", "-J", "-V",
                                       "Custom", "-b", "isolinux/isolinux.bin",
                                       "-c", "isolinux/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-boot-info-table", "-v", "-v",
                                       "-o", self.output_iso,
                                       self.iso_contents])

    def get_default_runlevel(self, g_handle):
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

    def get_service_runlevel_link(self, g_handle, service):
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

        return "/etc/rc.d/rc" + runlevel + ".d/S" + startlevel + service

    def image_ssh_teardown_step_1(self, g_handle):
        self.log.debug("Teardown step 1")
        # reset the authorized keys
        self.log.debug("Resetting authorized_keys")
        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.rm('/root/.ssh/authorized_keys')
        if g_handle.exists('/root/.ssh/authorized_keys.icicle'):
            g_handle.mv('/root/.ssh/authorized_keys.icicle',
                        '/root/.ssh/authorized_keys')

    def image_ssh_teardown_step_2(self, g_handle):
        self.log.debug("Teardown step 2")
        # remove custom sshd_config
        self.log.debug("Resetting sshd_config")
        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.rm('/etc/ssh/sshd_config')
        if g_handle.exists('/etc/ssh/sshd_config.icicle'):
            g_handle.mv('/etc/ssh/sshd_config.icicle', '/etc/ssh/sshd_config')

        # reset the service link
        self.log.debug("Resetting sshd service")
        startuplink = self.get_service_runlevel_link(g_handle, 'sshd')
        if g_handle.exists(startuplink):
            g_handle.rm(startuplink)
        if g_handle.exists(startuplink + ".icicle"):
            g_handle.mv(startuplink + ".icicle", startuplink)

    def image_ssh_teardown_step_3(self, g_handle):
        self.log.debug("Teardown step 3")
        # reset iptables
        self.log.debug("Resetting iptables rules")
        if g_handle.exists('/etc/sysconfig/iptables'):
            g_handle.rm('/etc/sysconfig/iptables')
        if g_handle.exists('/etc/sysconfig/iptables.icicle'):
            g_handle.mv('/etc/sysconfig/iptables')

    def image_ssh_teardown_step_4(self, g_handle):
        self.log.debug("Teardown step 4")
        # remove announce cronjob
        self.log.debug("Resetting announcement to host")
        if g_handle.exists('/etc/cron.d/announce'):
            g_handle.rm('/etc/cron.d/announce')

        # remove icicle-nc binary
        self.log.debug("Removing icicle-nc binary")
        if g_handle.exists('/root/icicle-nc'):
            g_handle.rm('/root/icicle-nc')

        # reset the service link
        self.log.debug("Resetting crond service")
        startuplink = self.get_service_runlevel_link(g_handle, 'crond')
        if g_handle.exists(startuplink):
            g_handle.rm(startuplink)
        if g_handle.exists(startuplink + ".icicle"):
            g_handle.mv(startuplink + ".icicle", startuplink)

    def collect_teardown(self, libvirt_xml):
        self.log.info("Collection Teardown")

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        try:
            self.image_ssh_teardown_step_1(g_handle)

            self.image_ssh_teardown_step_2(g_handle)

            self.image_ssh_teardown_step_3(g_handle)

            self.image_ssh_teardown_step_4(g_handle)
        finally:
            self.guestfs_handle_cleanup(g_handle)

    def image_ssh_setup_step_1(self, g_handle):
        # part 1; upload the keys
        self.log.debug("Step 1: Uploading ssh keys")
        if not g_handle.exists('/root/.ssh'):
            g_handle.mkdir('/root/.ssh')

        if g_handle.exists('/root/.ssh/authorized_keys'):
            g_handle.mv('/root/.ssh/authorized_keys',
                        '/root/.ssh/authorized_keys.icicle')

        if not os.access(self.icicle_tmp, os.F_OK):
            os.makedirs(self.icicle_tmp)

        pubname = self.sshprivkey + ".pub"
        if os.access(self.sshprivkey, os.F_OK):
            os.remove(self.sshprivkey)
        if os.access(pubname, os.F_OK):
            os.remove(pubname)
        subprocess.call(['ssh-keygen', '-q', '-t', 'rsa', '-b', '2048',
                         '-N', '', '-f', self.sshprivkey])

        g_handle.upload(pubname, '/root/.ssh/authorized_keys')

    def image_ssh_setup_step_2(self, g_handle):
        # part 2; check and setup sshd
        self.log.debug("Step 2: setup sshd")
        if not g_handle.exists('/etc/init.d/sshd') or not g_handle.exists('/usr/sbin/sshd'):
            raise Guest.OzException("ssh not installed on the image, cannot continue")

        startuplink = self.get_service_runlevel_link(g_handle, 'sshd')
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".icicle")
        g_handle.ln_sf('/etc/init.d/sshd', startuplink)

        sshd_config = \
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

        sshd_config_file = self.icicle_tmp + "/sshd_config"
        f = open(sshd_config_file, 'w')
        f.write(sshd_config)
        f.close()

        if g_handle.exists('/etc/ssh/sshd_config'):
            g_handle.mv('/etc/ssh/sshd_config', '/etc/ssh/sshd_config.icicle')
        g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
        os.unlink(sshd_config_file)

    def image_ssh_setup_step_3(self, g_handle):
        # part 3; open up iptables
        self.log.debug("Step 3: Open up the firewall")
        if g_handle.exists('/etc/sysconfig/iptables'):
            g_handle.mv('/etc/sysconfig/iptables', '/etc/sysconfig/iptables.icicle')
        # implicit else; if there is no iptables file, the firewall is open

    def image_ssh_setup_step_4(self, g_handle):
        # part 4; make sure the guest announces itself
        self.log.debug("Step 4: Guest announcement")
        if not g_handle.exists('/etc/init.d/crond') or not g_handle.exists('/usr/sbin/crond'):
            raise Guest.OzException("cron not installed on the image, cannot continue")

        iciclepath = ozutil.generate_full_guesttools_path('icicle-nc')
        g_handle.upload(iciclepath, '/root/icicle-nc')
        g_handle.chmod(0755, '/root/icicle-nc')

        announcefile = self.icicle_tmp + "/announce"
        f = open(announcefile, 'w')
        f.write('*/1 * * * * root /bin/bash -c "/root/icicle-nc ' + self.host_bridge_ip + ' ' + str(self.listen_port) + '"\n')
        f.close()

        g_handle.upload(announcefile, '/etc/cron.d/announce')

        startuplink = self.get_service_runlevel_link(g_handle, 'crond')
        if g_handle.exists(startuplink):
            g_handle.mv(startuplink, startuplink + ".icicle")
        g_handle.ln_sf('/etc/init.d/crond', startuplink)

        os.unlink(announcefile)

    def collect_setup(self, libvirt_xml):
        self.log.info("Collection Setup")

        g_handle = self.guestfs_handle_setup(libvirt_xml)

        # we have to do 3 things to make sure we can ssh into Fedora 13:
        # 1)  Upload our ssh key
        # 2)  Make sure sshd is running on boot
        # 3)  Make sure that port 22 is open in the firewall
        # 4)  Make the guest announce itself to the host

        try:
            try:
                self.image_ssh_setup_step_1(g_handle)
            except:
                self.image_ssh_teardown_step_1(g_handle)
                raise

            try:
                self.image_ssh_setup_step_2(g_handle)
            except:
                self.image_ssh_teardown_step_2(g_handle)
                raise

            try:
                self.image_ssh_setup_step_3(g_handle)
            except:
                self.image_ssh_teardown_step_3(g_handle)
                raise

            try:
                self.image_ssh_setup_step_4(g_handle)
            except:
                self.image_ssh_teardown_step_4(g_handle)
                raise
        finally:
            self.guestfs_handle_cleanup(g_handle)

    def guest_execute_command(self, guestaddr, command):
        sub = subprocess.Popen(["ssh", "-i", self.sshprivkey,
                                "-o", "StrictHostKeyChecking=no",
                                "-o", "ConnectTimeout=5", guestaddr, command],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        data = sub.communicate()

        # here we return a tuple that is (stdout,stderr,returncode)
        return data+(sub.returncode,)

    def generate_icicle(self, libvirt_xml):
        self.log.info("Generating ICICLE")

        self.collect_setup(libvirt_xml)

        icicle_output = ''
        try:
            libvirt_dom = self.libvirt_conn.createXML(libvirt_xml, 0)

            guestaddr = self.wait_for_guest_boot()

            try:
                output = self.guest_execute_command(guestaddr, 'rpm -qa')
                stdout = output[0]
                stderr = output[1]
                returncode = output[2]
                if returncode != 0:
                    raise Guest.OzException("Failed to execute guest command 'rpm -qa': %s" % (stderr))

                icicle_output = self.output_icicle_xml(stdout.split("\n"),
                                                       self.tdl.services)

            finally:
                output = self.guest_execute_command(guestaddr,
                                                    'shutdown -h now')
                returncode = output[2]
                if returncode != 0:
                    self.log.warn("Failed shutting down guest, continuing anyway")
                else:
                    if self.wait_for_guest_shutdown(libvirt_dom):
                        libvirt_dom = None
        finally:
            if libvirt_dom is not None:
                libvirt_dom.destroy()
            self.collect_teardown(libvirt_xml)

        return icicle_output
