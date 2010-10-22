import Guest
import subprocess
import re
import shutil

class RHL9Guest(Guest.CDGuest):
    def __init__(self, url):
        Guest.CDGuest.__init__(self, "RHL", "9", "i386", None, "rtl8139", None, None, None)
        self.url = url
        self.ks_file = "./rhl-9-jeos.ks"

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

def get_class(update, arch, url, key):
    if arch != "i386":
        raise Exception, "Invalid arch " + arch + "for RHL guest"
    if update == "9":
        return RHL9Guest(url)
    raise Exception, "Unsupported RHL update " + update
