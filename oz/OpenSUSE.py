import Guest
import re
import shutil
import ozutil

class OpenSUSEGuest(Guest.CDGuest):
    def __init__(self, update, arch, url, autoyast, config):
        Guest.CDGuest.__init__(self, "OpenSUSE", update, arch, "rtl8139", None, None, None, config)
        self.isourl = url
        self.autoyast = autoyast

    def modify_iso(self):
        self.log.debug("Putting the autoyast in place")
        shutil.copy(self.autoyast, self.iso_contents + "/autoinst.xml")

        self.log.debug("Modifying the boot options")
        f = open(self.iso_contents + "/boot/" + self.arch + "/loader/isolinux.cfg", "r")
        lines = f.readlines()
        f.close()
        for line in lines:
            if re.match("timeout", line):
                lines[lines.index(line)] = "timeout 1\n"
            elif re.match("default", line):
                lines[lines.index(line)] = "default customiso\n"
        lines.append("label customiso\n")
        lines.append("  kernel linux\n")
        lines.append("  append initrd=initrd splash=silent instmode=cd autoyast=default")

        f = open(self.iso_contents + "/boot/" + self.arch + "/loader/isolinux.cfg", "w")
        f.writelines(lines)
        f.close()

    def generate_new_iso(self):
        self.log.info("Generating new ISO")
        Guest.subprocess_check_output(["mkisofs", "-r", "-J", "-V", "Custom",
                                       "-l", "-b",
                                       "boot/" + self.arch + "/loader/isolinux.bin",
                                       "-c", "boot/" + self.arch + "/loader/boot.cat",
                                       "-no-emul-boot", "-boot-load-size", "4",
                                       "-boot-info-table", "-graft-points",
                                       "-iso-level", "4", "-pad",
                                       "-allow-leading-dots",
                                       "-o", self.output_iso,
                                       self.iso_contents])

    def generate_install_media(self, force_download):
        self.log.info("Generating install media")
        self.get_original_iso(self.isourl, force_download)
        self.copy_iso()
        self.modify_iso()
        self.generate_new_iso()
        self.cleanup_iso()

def get_class(idl, config):
    update = idl.update()
    arch = idl.arch()
    autoyast = ozutil.generate_full_auto_path("opensuse-" + update + "-jeos.xml")

    if idl.installtype() != 'iso':
        raise Exception, "OpenSUSE installs must be done via ISO"

    url = ozutil.check_url(idl.iso())

    if update == "11.3":
        return OpenSUSEGuest(update, arch, url, autoyast, config)

    raise Exception, "Unsupported OpenSUSE update " + update
