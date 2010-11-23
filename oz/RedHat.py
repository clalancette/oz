import Guest
import subprocess
import re

def generate_iso(output_iso, input_dir):
    Guest.subprocess_check_output(["mkisofs", "-r", "-T", "-J", "-V",
                                   "Custom", "-b", "isolinux/isolinux.bin",
                                   "-c", "isolinux/boot.cat",
                                   "-no-emul-boot", "-boot-load-size", "4",
                                   "-boot-info-table", "-v", "-v",
                                   "-o", output_iso, input_dir ])

def guest_execute_command(guestaddr, keypath, command):
    return subprocess.Popen(["ssh", "-i", keypath,
                             "-o", "StrictHostKeyChecking=no",
                             "-o", "ConnectTimeout=5", guestaddr,
                             command], stdout=subprocess.PIPE).communicate()

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

def get_service_runlevel_link(g_handle, runlevel, service):
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

