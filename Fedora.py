import Guest
import shutil
import subprocess
import re

class FedoraGuest(Guest.CDGuest):
    def __init__(self, update, arch, url, ks, nicmodel, haverepo):
        Guest.CDGuest.__init__(self, "Fedora", update, arch, None, nicmodel, None, None)
        self.ks_file = ks
        # FIXME: check that the url is accessible
        self.url = url
        self.haverepo = haverepo

    def modify_iso(self):
        print "Putting the kickstart in place"

        shutil.copy(self.ks_file, self.iso_contents + "/ks.cfg")

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
        if self.haverepo:
            lines.append("  append initrd=initrd.img ks=cdrom:/ks.cfg repo=" + self.url + "\n")
        else:
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

def get_class(update, arch, url):
    ks = "./fedora-" + update + "-jeos.ks"
    if update == "10" or update == "11" or update == "12":
        return FedoraGuest(update, arch, url, ks, "virtio", True)
    if update == "9" or update == "8" or update == "7":
        return FedoraGuest(update, arch, url, ks, "rtl8139", False)
    raise Exception, "Unsupported Fedora update " + update
