#!/usr/bin/python

import sys
import Fedora
import FedoraCore
import RHEL_3
import RHEL_4
import RHEL_5
import Ubuntu

def usage():
    print "Usage: oz <distro> <update> <arch> <url>"
    print " Currently supported architectures are:"
    print "  i386, x86_64"
    print " Currently supported distros are:"
    print "   Fedora: 7, 8, 9, 10, 11, 12"
    print "   Fedora Core: 1, 2, 3, 4, 5, 6"
    print "   RHEL 3: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   RHEL 4: GOLD, U1, U2, U3, U4, U5, U6, U7, U8"
    print "   RHEL 5: GOLD, U1, U2, U3, U4, U5"
    print "   Ubuntu: 7.04 7.10 8.04.1 8.10 9.04"
    sys.exit(1)

if len(sys.argv) != 5:
    usage()

distro = sys.argv[1]
update = sys.argv[2]
arch = sys.argv[3]
url = sys.argv[4]

if distro == "Fedora":
    guest = Fedora.get_class(update, arch, url)
elif distro == "FedoraCore":
    guest = FedoraCore.get_class(update, arch, url)
elif distro == "RHEL-3":
    guest = RHEL_3.get_class(update, arch, url)
elif distro == "RHEL-4":
    guest = RHEL_4.get_class(update, arch, url)
elif distro == "RHEL-5":
    guest = RHEL_5.get_class(update, arch, url)
elif distro == "Ubuntu":
    guest = Ubuntu.get_class(update, arch, url)
else:
    usage()

guest.cleanup_old_guest()
guest.generate_install_media()
guest.generate_diskimage()
guest.install()
