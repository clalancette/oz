import Guest
import subprocess
import re
import os
import ozutil

def generate_iso(output_iso, input_dir):
    Guest.subprocess_check_output(["mkisofs", "-r", "-T", "-J", "-V",
                                   "Custom", "-b", "isolinux/isolinux.bin",
                                   "-c", "isolinux/boot.cat",
                                   "-no-emul-boot", "-boot-load-size", "4",
                                   "-boot-info-table", "-v", "-v",
                                   "-o", output_iso, input_dir ])

def guest_execute_command(guestaddr, keypath, command):
    sub = subprocess.Popen(["ssh", "-i", keypath,
                            "-o", "StrictHostKeyChecking=no",
                            "-o", "ConnectTimeout=5", guestaddr,
                            command], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)

    data = sub.communicate()

    # here we return a tuple that is (stdout,stderr,returncode)
    return data+(sub.returncode,)

def get_default_runlevel(g_handle):
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

def get_service_runlevel_link(g_handle, service):
    runlevel = get_default_runlevel(g_handle)

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


def image_ssh_setup(log, g_handle, icicle_tmp, host_bridge_ip, listen_port, libvirt_xml):
    # we have to do 3 things to make sure we can ssh into Fedora 13:
    # 1)  Upload our ssh key
    # 2)  Make sure sshd is running on boot
    # 3)  Make sure that port 22 is open in the firewall
    # 4)  Make the guest announce itself to the host

    # part 1; upload the keys
    log.debug("Step 1: Uploading ssh keys")
    if not g_handle.exists('/root/.ssh'):
        g_handle.mkdir('/root/.ssh')

    if g_handle.exists('/root/.ssh/authorized_keys'):
        g_handle.mv('/root/.ssh/authorized_keys',
                    '/root/.ssh/authorized_keys.icicle')

    if not os.access(icicle_tmp, os.F_OK):
        os.makedirs(icicle_tmp)

    privname = icicle_tmp + '/id_rsa-icicle-gen'
    pubname = icicle_tmp + '/id_rsa-icicle-gen.pub'
    if os.access(privname, os.F_OK):
        os.remove(privname)
    if os.access(pubname, os.F_OK):
        os.remove(pubname)
    subprocess.call(['ssh-keygen', '-q', '-t', 'rsa', '-b', '2048', '-N', '',
                     '-f', privname])

    g_handle.upload(pubname, '/root/.ssh/authorized_keys')

    # part 2; check and setup sshd
    log.debug("Step 2: setup sshd")
    if not g_handle.exists('/etc/init.d/sshd') or not g_handle.exists('/usr/sbin/sshd'):
        raise OzException("ssh not installed on the image, cannot continue")

    startuplink = get_service_runlevel_link(g_handle, 'sshd')
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

    sshd_config_file = icicle_tmp + "/sshd_config"
    f = open(sshd_config_file, 'w')
    f.write(sshd_config)
    f.close()

    if g_handle.exists('/etc/ssh/sshd_config'):
        g_handle.mv('/etc/ssh/sshd_config', '/etc/ssh/sshd_config.icicle')
    g_handle.upload(sshd_config_file, '/etc/ssh/sshd_config')
    os.unlink(sshd_config_file)

    # part 3; open up iptables
    log.debug("Step 3: Open up the firewall")
    if g_handle.exists('/etc/sysconfig/iptables'):
        g_handle.mv('/etc/sysconfig/iptables', '/etc/sysconfig/iptables.icicle')
    # implicit else; if there is no iptables file, the firewall is open

    # part 4; make sure the guest announces itself
    log.debug("Step 4: Guest announcement")
    if not g_handle.exists('/etc/init.d/crond') or not g_handle.exists('/usr/sbin/crond'):
        raise OzException("cron not installed on the image, cannot continue")

    iciclepath = ozutil.generate_full_guesttools_path('icicle-nc')
    g_handle.upload(iciclepath, '/root/icicle-nc')
    g_handle.chmod(0755, '/root/icicle-nc')

    announcefile = icicle_tmp + "/announce"
    f = open(announcefile, 'w')
    f.write('*/1 * * * * root /bin/bash -c "/root/icicle-nc ' + host_bridge_ip + ' ' + str(listen_port) + '"\n')
    f.close()

    g_handle.upload(announcefile, '/etc/cron.d/announce')

    startuplink = get_service_runlevel_link(g_handle, 'crond')
    if g_handle.exists(startuplink):
        g_handle.mv(startuplink, startuplink + ".icicle")
    g_handle.ln_sf('/etc/init.d/crond', startuplink)

    os.unlink(announcefile)

def image_ssh_teardown(log, g_handle):
    # reset the authorized keys
    log.debug("Resetting authorized_keys")
    if g_handle.exists('/root/.ssh/authorized_keys'):
        g_handle.rm('/root/.ssh/authorized_keys')
    if g_handle.exists('/root/.ssh/authorized_keys.icicle'):
        g_handle.mv('/root/.ssh/authorized_keys.icicle',
                    '/root/.ssh/authorized_keys')

    # reset iptables
    log.debug("Resetting iptables rules")
    if g_handle.exists('/etc/sysconfig/iptables'):
        g_handle.rm('/etc/sysconfig/iptables')
    if g_handle.exists('/etc/sysconfig/iptables.icicle'):
        g_handle.mv('/etc/sysconfig/iptables')

    # remove announce cronjob
    log.debug("Resetting announcement to host")
    if g_handle.exists('/etc/cron.d/announce'):
        g_handle.rm('/etc/cron.d/announce')

    # remove icicle-nc binary
    log.debug("Removing icicle-nc binary")
    if g_handle.exists('/root/icicle-nc'):
        g_handle.rm('/root/icicle-nc')

    # remove custom sshd_config
    log.debug("Resetting sshd_config")
    if g_handle.exists('/etc/ssh/sshd_config'):
        g_handle.rm('/etc/ssh/sshd_config')
    if g_handle.exists('/etc/ssh/sshd_config.icicle'):
        g_handle.mv('/etc/ssh/sshd_config.icicle', '/etc/ssh/sshd_config')

    # reset the service links
    for service in ["sshd", "crond"]:
        log.debug("Resetting %s service" % (service))
        startuplink = get_service_runlevel_link(g_handle, service)
        if g_handle.exists(startuplink):
            g_handle.rm(startuplink)
        if g_handle.exists(startuplink + ".icicle"):
            g_handle.mv(startuplink + ".icicle", startuplink)

