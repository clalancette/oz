import Guest
import subprocess
import os
import re
import shutil

class RHEL21Guest(Guest.FDGuest):
    def __init__(self, update, url):
        Guest.FDGuest.__init__(self, "RHEL-2.1", update, "i386", None, "pcnet", None, None, None)
        self.url = url
        self.ks_file = "./rhel-2.1-jeos.ks"

    def modify_floppy(self):
        if not os.access(self.floppy_contents, os.F_OK):
            os.makedirs(self.floppy_contents)

        print "Putting the kickstart in place"

        output_ks = self.floppy_contents + "/ks.cfg"
        shutil.copyfile(self.ks_file, output_ks)
        f = open(output_ks, "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("^url", line):
                lines[lines.index(line)] = "url --url " + self.url + "\n"

        f = open(output_ks, "w")
        f.writelines(lines)
        f.close()
        subprocess.call(["mcopy", "-i", self.output_floppy, output_ks, "::KS.CFG"])

        print "Modifying the syslinux.cfg"

        subprocess.call(["mcopy", "-n", "-o", "-i", self.output_floppy, "::SYSLINUX.CFG", self.floppy_contents])
        f = open(self.floppy_contents + "/SYSLINUX.CFG", "r")
        lines = f.readlines()
        f.close()

        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            if re.match("default", line):
                lines[lines.index(line)] = "default customboot\n"
        lines.append("label customboot\n")
        lines.append("  kernel vmlinuz\n")
        lines.append("  append initrd=initrd.img lang= devfs=nomount ramdisk_size=9216 ks=floppy method=" + self.url + "\n")

        f = open(self.floppy_contents + "/SYSLINUX.CFG", "w")
        f.writelines(lines)
        f.close()

        subprocess.call(["mcopy", "-n", "-o", "-i", self.output_floppy, self.floppy_contents + "/SYSLINUX.CFG", "::SYSLINUX.CFG"])

    def generate_install_media(self):
        self.get_original_floppy(self.url + "/images/bootnet.img")
        self.copy_floppy()
        self.modify_floppy()

    def install(self):
        print "Running install for " + self.name
        self.generate_define_xml("fd")
        self.libvirt_dom.create()

        self.wait_for_install_finish(1200)

        self.generate_define_xml("hd")

def get_class(update, arch, url, key):
    if arch != "i386":
        raise Exception, "Invalid arch " + arch + "for RHEL-2.1 guest"
    if update == "GOLD" or update == "U1" or update == "U2" or update == "U3" or update == "U4" or update == "U5" or update == "U6":
        return RHEL21Guest(update, url)
    raise Exception, "Unsupported RHEL-2.1 update " + update
