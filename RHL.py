import Guest
import subprocess
import re
import shutil
import os

class RHL9Guest(Guest.CDGuest):
    def __init__(self, url):
        Guest.CDGuest.__init__(self, "RHL", "9", "i386", None, "rtl8139", None, None, None)
        self.url = url
        self.ks_file = ks

    def modify_iso(self):
        print "Putting the kickstart in place"

        output_ks = self.iso_contents + "/ks.cfg"
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

        print "Modifying the boot options"
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            elif re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel vmlinuz\n")
        lines.append("  append initrd=initrd.img ks=cdrom:/ks.cfg method=" + self.url + "\n")

        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "w")
        f.writelines(lines)
        f.close()

    def generate_new_iso(self):
        print "Generating new ISO"
        subprocess.call(["mkisofs", "-r", "-T", "-J", "-V", "Custom",
                         "-b", "isolinux/isolinux.bin",
                         "-c", "isolinux/boot.cat", "-no-emul-boot",
                         "-boot-load-size", "4", "-boot-info-table", "-quiet",
                         "-o", self.output_iso, self.iso_contents])

    def generate_install_media(self):
        self.get_original_iso(self.url + "/images/boot.iso")
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

class RHL8Guest(Guest.FDGuest):
    def __init__(self, url, ks):
        Guest.FDGuest.__init__(self, "RHL", "8", "i386", None, "rtl8139", None, None, None)
        self.url = url
        self.ks_file = ks

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

def get_class(update, arch, url, key):
    ks = "./rhl-" + update + "-jeos.ks"
    if arch != "i386":
        raise Exception, "Invalid arch " + arch + "for RHL guest"
    if update == "9":
        return RHL9Guest(url, ks)
    if update == "8":
        return RHL8Guest(url, ks)
    raise Exception, "Unsupported RHL update " + update
