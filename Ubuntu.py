import Guest
import shutil
import subprocess
import re
import os
import stat

def generate_new_iso(output, inputdir):
    print "Generating new ISO"
    subprocess.call(["mkisofs", "-r", "-V", "Custom", "-cache-inodes",
                     "-J", "-l", "-b", "isolinux/isolinux.bin",
                     "-c", "isolinux/boot.cat", "-no-emul-boot",
                     "-boot-load-size", "4", "-boot-info-table", "-quiet",
                     "-o", output, inputdir])

class Ubuntu904Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "rtl8139", None, None)
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        generate_new_iso(self.output_iso, self.iso_contents)

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
        lines.append("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us boot=casper automatic-ubiquity noprompt initrd=/casper/initrd.gz ramdisk_size=14984 --\n")
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

class Ubuntu810Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "rtl8139", None, None)
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        generate_new_iso(self.output_iso, self.iso_contents)

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
        lines.append("  append file=/cdrom/preseed/customiso.seed debian-installer/locale=en_US console-setup/layoutcode=us boot=casper automatic-ubiquity noprompt initrd=/casper/initrd.gz ramdisk_size=14984 --\n")
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

class Ubuntu8041Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "rtl8139", None, None)
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        generate_new_iso(self.output_iso, self.iso_contents)

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

class Ubuntu710Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "rtl8139", None, None)
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        generate_new_iso(self.output_iso, self.iso_contents)

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

class Ubuntu704Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "rtl8139", None, None)
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        generate_new_iso(self.output_iso, self.iso_contents)

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

class Ubuntu610Guest(Guest.CDGuest):
    def __init__(self, update, arch, preseed, iso):
        Guest.CDGuest.__init__(self, "Ubuntu", update, arch, None, "rtl8139", None, None)
        self.ubuntuarch = arch
        if self.ubuntuarch == "x86_64":
            self.ubuntuarch = "amd64"
        self.isourl = iso
        self.preseed_file = preseed

    def generate_install_media(self):
        self.get_original_iso(self.isourl)
        self.copy_iso()
        self.modify_iso()
        generate_new_iso(self.output_iso, self.iso_contents)

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

def get_class(update, arch, isourl):
    if update == "9.04":
        return Ubuntu904Guest(update, arch, "./ubuntu-904-jeos.preseed", isourl)
    if update == "8.10":
        return Ubuntu810Guest(update, arch, "./ubuntu-810-jeos.preseed", isourl)
    if update == "8.04.1":
        return Ubuntu8041Guest(update, arch, "./ubuntu-8041-jeos.preseed", isourl)
    if update == "7.10":
        return Ubuntu710Guest(update, arch, "./ubuntu-710-jeos.preseed", isourl)
    if update == "7.04":
        return Ubuntu704Guest(update, arch, "./ubuntu-704-jeos.preseed", isourl)
    if update == "6.10":
        return Ubuntu610Guest(update, arch, "./ubuntu-610-jeos.preseed", isourl)
    raise Exception, "Unsupported Ubuntu update " + update
