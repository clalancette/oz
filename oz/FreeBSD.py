"""
FreeBSD installation
"""

#import random
import re
import os
import libxml2
import shutil

import oz.Guest
import oz.ozutil
import oz.OzException

class FreeBSD(oz.Guest.CDGuest):
    def __init__(self, tdl, config, auto, output_disk, netdev, diskbus,
                 macaddress):
	oz.Guest.CDGuest.__init__(self, tdl, config, auto, output_disk,
                                  netdev, "localtime", "usb", diskbus, True,
                                  False, macaddress)

    def _generate_new_iso(self):
        self.log.debug("Generating new ISO")
        oz.ozutil.subprocess_check_output(["genisoimage",
                                           "-R", "-no-emul-boot",
                                           "-b", "boot/cdboot",
                                           "-o", self.output_iso,
                                           self.iso_contents])

    def _modify_iso(self):
        self.log.debug("Modifying ISO")

	internalscript = ''

	packstr = ''
	for package in self.tdl.packages:
		packstr += package.name + ' '

	"""
	Pkg needs to get itself on first run, so networking is needed.
	Afterwords, it is used to install the extra packages.
	"""

        if packstr != '':
		self.log.debug("Install package(s): " + packstr)
		internalscript = "dhclient vtnet0\n"
		internalscript += "export ASSUME_ALWAYS_YES=yes\n"
		internalscript += "export PACKAGESITE='http://pkgbeta.freebsd.org/freebsd:10:x86:64/latest'\n"
		internalscript += "pkg install " + packstr

	def _replace(line):
		keys = {
			'#ROOTPW#':self.rootpw,
			'###OZ###':internalscript
		}
		for key, val in keys.iteritems():
			line = line.replace(key, val)
		return line

	"""
	Check to make sure our magic variable is present so we can replace that
	with even more magic :)
	"""

	if not '###OZ###' in open(self.auto).read():
		raise oz.OzException.OzException("Marker not found, cannot continue: '###OZ###'")

	"""
	Copy the installconfig file to /etc/ on the iso image so bsdinstall(8)
	can use that to do an unattended installation. This rules file contains
	both setup rules and a post script. This stage also prepends the post
	script with additional commands so it's possible to install extra
	packages specified in the .tdl file.
	"""

	outname = os.path.join(self.iso_contents, "etc", "installerconfig")
	oz.ozutil.copy_modify_file(self.auto, outname, _replace)

	"""
	Make sure the iso can be mounted at boot, otherwise this error shows up
	after booting the kernel:
	  mountroot: waiting for device /dev/iso9660/FREEBSD_INSTALL ...
	  Mounting from cd9660:/dev/iso9660/FREEBSD_INSTALL failed with error 19.
	"""

	with open('/tmp/loader.conf', 'w') as conf:
		conf.write('vfs.root.mountfrom="cd9660:/dev/cd0"\n')

	loaderconf = os.path.join(self.iso_contents, "boot", "loader.conf")
	shutil.copy('/tmp/loader.conf', loaderconf)

    def install(self, timeout=None, force=False):
        internal_timeout = timeout
        if internal_timeout is None:
            internal_timeout = 8500
        return self._do_install(internal_timeout, force, 2)

def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    return FreeBSD(tdl, config, auto, output_disk, netdev, diskbus,
                          macaddress)

def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "FreeBSD: 10"
