# Copyright (C) 2011  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation;
# version 2.1 of the License.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import Fedora
import FedoraCore
import RHEL_2_1
import RHEL_3
import RHEL_4
import RHEL_5
import RHEL_6
import RHL
import Ubuntu
import Windows
import OpenSUSE
import Debian
import OzException

def guest_factory(tdl, config, auto):
    if tdl.distro == "Fedora":
        return Fedora.get_class(tdl, config, auto)
    elif tdl.distro == "FedoraCore":
        return FedoraCore.get_class(tdl, config, auto)
    elif tdl.distro == "RHEL-2.1":
        return RHEL_2_1.get_class(tdl, config, auto)
    elif tdl.distro in ["RHEL-3", "CentOS-3"]:
        return RHEL_3.get_class(tdl, config, auto)
    elif tdl.distro in ["RHEL-4", "CentOS-4"]:
        return RHEL_4.get_class(tdl, config, auto)
    elif tdl.distro in ["RHEL-5", "CentOS-5"]:
        return RHEL_5.get_class(tdl, config, auto)
    elif tdl.distro == "RHEL-6":
        return RHEL_6.get_class(tdl, config, auto)
    elif tdl.distro == "Ubuntu":
        return Ubuntu.get_class(tdl, config, auto)
    elif tdl.distro == "Windows":
        return Windows.get_class(tdl, config, auto)
    elif tdl.distro == "RHL":
        return RHL.get_class(tdl, config, auto)
    elif tdl.distro == "OpenSUSE":
        return OpenSUSE.get_class(tdl, config, auto)
    elif tdl.distro == "Debian":
        return Debian.get_class(tdl, config, auto)

    raise OzException.OzException("Invalid distribution " + tdl.distro)

def distrolist():
    print "   Fedora: 7, 8, 9, 10, 11, 12, 13, 14"
    print "   Fedora Core: 1, 2, 3, 4, 5, 6"
    print "   RHEL 2.1: GOLD, U2, U3, U4, U5, U6"
    print "   RHEL 3: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   RHEL 4: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   RHEL 5: GOLD, U1, U2, U3, U4, U5, U6"
    print "   RHEL 6: 0"
    print "   Ubuntu: 6.10, 7.04, 7.10, 8.04.[1,2,3,4], 8.10, 9.04, 9.10, 10.04.1"
    print "   Windows: 2000, XP, 2003, 7, 2008"
    print "   RHL: 7.0, 7.1, 7.2, 7.3, 8, 9"
    print "   OpenSUSE: 11.0, 11.1, 11.2, 11.3, 11.4"
    print "   CentOS 3: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   CentOS 4: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   CentOS 5: GOLD, U1, U2, U3, U4, U5"
    print "   Debian: 5, 6"
