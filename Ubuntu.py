import Guest
import shutil
import subprocess
import re
import os
import stat
import ozutil

def ubuntu_generate_iso(output, inputdir):
    print "Generating new ISO"
    Guest.subprocess_check_output(["mkisofs", "-r", "-V", "Custom",
                                  "-cache-inodes", "-J", "-l", "-b",
                                  "isolinux/isolinux.bin", "-c",
                                  "isolinux/boot.cat", "-no-emul-boot",
                                  "-boot-load-size", "4", "-boot-info-table",
                                  "-v", "-v", "-o", output, inputdir])

class Ubuntu810and904and910Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso, initrd):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "virtio", None, None, "virtio")
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed
        self.initrd = initrd

    def generate_new_iso(self):
        ubuntu_generate_iso(self.output_iso, self.iso_contents)

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

    def modify_iso(self):
        print "Putting the preseed file in place"

        shutil.copy(self.preseed_file, self.iso_contents + "/preseed/customiso.seed")

        print "Modifying text.cfg"
        f = open(self.iso_contents + "/isolinux/text.cfg", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  menu label ^Customiso\n")
        lines.append("  kernel /casper/vmlinuz\n")
        lines.append("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us boot=casper automatic-ubiquity noprompt initrd=" + self.initrd + " ramdisk_size=14984 --\n")
        f = open(self.iso_contents + "/isolinux/text.cfg", "w")
        f.writelines(lines)
        f.close()

        print "Modifying isolinux.cfg"
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
            elif re.match("timeout", line):
                lines[lines.index(line)] = "timeout 10\n"
            elif re.match("gfxboot", line):
                lines[lines.index(line)] = ""
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "w")
        f.writelines(lines)
        f.close()

class Ubuntu710and8041Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "rtl8139", None, None, None)
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed

    def generate_new_iso(self):
        ubuntu_generate_iso(self.output_iso, self.iso_contents)

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

    def modify_iso(self):
        print "Putting the preseed file in place"

        shutil.copy(self.preseed_file, self.iso_contents + "/preseed/customiso.seed")

        print "Modifying isolinux.cfg"
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match(" *TIMEOUT", line, re.IGNORECASE):
                lines[lines.index(line)] = "TIMEOUT 1\n"
            elif re.match(" *DEFAULT", line, re.IGNORECASE):
                lines[lines.index(line)] = "DEFAULT customiso\n"
            elif re.match(" *GFXBOOT", line, re.IGNORECASE):
                lines[lines.index(line)] = ""
            elif re.match("^APPEND", line, re.IGNORECASE):
                lines[lines.index(line)] = ""
        lines.append("LABEL customiso\n")
        lines.append("  menu label ^Customiso\n")
        lines.append("  kernel /casper/vmlinuz\n")
        lines.append("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us boot=casper automatic-ubiquity noprompt initrd=/casper/initrd.gz --\n")
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "w")
        f.writelines(lines)
        f.close()

class Ubuntu610and704Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "rtl8139", None, None, None)
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed

    def generate_new_iso(self):
        ubuntu_generate_iso(self.output_iso, self.iso_contents)

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

    def modify_iso(self):
        print "Putting the preseed file in place"
        shutil.copy(self.preseed_file, self.iso_contents + "/preseed/customiso.seed")

        print "Modifying isolinux.cfg"
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match(" *TIMEOUT", line, re.IGNORECASE):
                lines[lines.index(line)] = "TIMEOUT 1\n"
            elif re.match(" *DEFAULT", line, re.IGNORECASE):
                lines[lines.index(line)] = "DEFAULT customiso\n"
            elif re.match(" *GFXBOOT", line, re.IGNORECASE):
                lines[lines.index(line)] = ""
            elif re.match("^APPEND", line, re.IGNORECASE):
                lines[lines.index(line)] = ""
        lines.append("LABEL customiso\n")
        lines.append("  menu label ^Customiso\n")
        lines.append("  kernel /install/vmlinuz\n")
        lines.append("  append file=/cdrom/preseed/customiso.seed locale=en_US console-setup/ask_detect=false console-setup/layoutcode=us priority=critical ramdisk_size=141876 root=/dev/ram rw initrd=/install/initrd.gz --\n")
        f = open(self.iso_contents + "/isolinux/isolinux.cfg", "w")
        f.writelines(lines)
        f.close()

def get_class(idl):
    update = idl.update()
    arch = idl.arch()
    isourl = idl.iso()
    preseed = "./ubuntu-" + update + "-jeos.preseed"

    if idl.installtype() != 'iso':
        raise Exception, "Ubuntu installs must be done via iso"

    ozutil.check_iso_install(isourl)

    if update == "9.10":
        return Ubuntu810and904and910Guest(update, arch, preseed, isourl, "/casper/initrd.lz")
    if update == "8.10" or update == "9.04":
        return Ubuntu810and904and910Guest(update, arch, preseed, isourl, "/casper/initrd.gz")
    if update == "7.10" or update == "8.04" or update == "8.04.1" or update == "8.04.2" or update =="8.04.3" or update == "8.04.4":
        return Ubuntu710and8041Guest(update, arch, preseed, isourl)
    if update == "6.10" or update == "7.04":
        return Ubuntu610and704Guest(update, arch, preseed, isourl)
    raise Exception, "Unsupported Ubuntu update " + update
