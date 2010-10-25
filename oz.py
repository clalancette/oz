#!/usr/bin/python

import sys
import getopt
import os

import IDL
import Fedora
import FedoraCore
import RHEL_2_1
import RHEL_3
import RHEL_4
import RHEL_5
import RHL
import Ubuntu
import Windows

def usage():
    print "Usage: oz [OPTIONS] <idl>"
    print " OPTIONS:"
    print "  -h\t\tPrint this help message"
    print " Currently supported architectures are:"
    print "   i386, x86_64"
    print " Currently supported distros are:"
    print "   Fedora: 7, 8, 9, 10, 11, 12, 13"
    print "   Fedora Core: 1, 2, 3, 4, 5, 6"
    print "   RHEL 2.1: GOLD, U1, U2, U3, U4, U5, U6"
    print "   RHEL 3: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   RHEL 4: GOLD, U1, U2, U3, U4, U5, U6, U7, U8"
    print "   RHEL 5: GOLD, U1, U2, U3, U4, U5"
    print "   Ubuntu: 6.10, 7.04, 7.10, 8.04.[1,2,3,4], 8.10, 9.04, 9.10"
    print "   Windows: 2000, XP, 2003"
    print "   RHL: 7.0, 7.1, 7.2, 7.3, 8, 9"
    sys.exit(1)

try:
    opts, args = getopt.gnu_getopt(sys.argv[1:], 'h', ['help'])
except getopt.GetoptError, err:
    print str(err)
    usage()

for o, a in opts:
    if o in ("-h", "--help"):
        usage()
    else:
        assert False, "unhandled option"

if os.geteuid() != 0:
    print "%s must be run as root" % (sys.argv[0])
    sys.exit(2)

if len(args) != 1:
    usage();

idl = IDL.IDL(args[0])

distro = idl.distro()

if distro == "Fedora":
    guest = Fedora.get_class(idl)
elif distro == "FedoraCore":
    guest = FedoraCore.get_class(idl)
elif distro == "RHEL-2.1":
    guest = RHEL_2_1.get_class(idl)
elif distro == "RHEL-3":
    guest = RHEL_3.get_class(idl)
elif distro == "RHEL-4":
    guest = RHEL_4.get_class(idl)
elif distro == "RHEL-5":
    guest = RHEL_5.get_class(idl)
elif distro == "Ubuntu":
    guest = Ubuntu.get_class(idl)
elif distro == "Windows":
    guest = Windows.get_class(idl)
elif distro == "RHL":
    guest = RHL.get_class(idl)
else:
    usage()

guest.cleanup_old_guest()
guest.generate_install_media()
guest.generate_diskimage()
guest.install()
