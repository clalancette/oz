# Copyright (C) 2011,2012  Chris Lalancette <clalance@redhat.com>

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

"""
Factory functions.
"""

import oz.Fedora
import oz.FedoraCore
import oz.RHEL_2_1
import oz.RHEL_3
import oz.RHEL_4
import oz.RHEL_5
import oz.RHEL_6
import oz.RHL
import oz.Ubuntu
import oz.Windows
import oz.OpenSUSE
import oz.Debian
import oz.Mandrake
import oz.Mandriva
import oz.OzException

def guest_factory(tdl, config, auto, output_disk=None):
    """
    Factory function return an appropriate Guest object based on the TDL.
    The arguments are:

    tdl    - The TDL object to be used.  The object will be determined based
             on the distro and version from the TDL.
    config - A ConfigParser object that contains configuration.  If None is
             passed for the config, Oz defaults will be used.
    auto   - An unattended installation file to be used for the
             installation.  If None is passed for auto, then Oz will use
             a known-working unattended installation file.
    """

    klass = None
    if tdl.distro == "Fedora":
        klass = oz.Fedora.get_class(tdl, config, auto, output_disk)
    elif tdl.distro in ["FedoraCore", "FC"]:
        klass = oz.FedoraCore.get_class(tdl, config, auto, output_disk)
    elif tdl.distro in ["RedHatEnterpriseLinux-2.1", "RHEL-2.1"]:
        klass = oz.RHEL_2_1.get_class(tdl, config, auto, output_disk)
    elif tdl.distro in ["RedHatEnterpriseLinux-3", "RHEL-3", "CentOS-3"]:
        klass = oz.RHEL_3.get_class(tdl, config, auto, output_disk)
    elif tdl.distro in ["RedHatEnterpriseLinux-4", "RHEL-4", "CentOS-4",
                        "ScientificLinux-4", "SL-4"]:
        klass = oz.RHEL_4.get_class(tdl, config, auto, output_disk)
    elif tdl.distro in ["RedHatEnterpriseLinux-5", "RHEL-5", "CentOS-5",
                        "ScientificLinux-5", "SL-5",
                        "ScientificLinuxCern-5", "SLC-5"]:
        klass = oz.RHEL_5.get_class(tdl, config, auto, output_disk)
    elif tdl.distro in ["RedHatEnterpriseLinux-6", "RHEL-6", "CentOS-6",
                        "ScientificLinux-6", "SL-6",
                        "ScientificLinuxCern-6", "SLC-6",
                        "OracleEnterpriseLinux-6", "OEL-6"]:
        klass = oz.RHEL_6.get_class(tdl, config, auto, output_disk)
    elif tdl.distro == "Ubuntu":
        klass = oz.Ubuntu.get_class(tdl, config, auto, output_disk)
    elif tdl.distro == "Windows":
        klass = oz.Windows.get_class(tdl, config, auto, output_disk)
    elif tdl.distro in ["RedHatLinux", "RHL"]:
        klass = oz.RHL.get_class(tdl, config, auto, output_disk)
    elif tdl.distro == "OpenSUSE":
        klass = oz.OpenSUSE.get_class(tdl, config, auto, output_disk)
    elif tdl.distro == "Debian":
        klass = oz.Debian.get_class(tdl, config, auto, output_disk)
    elif tdl.distro == "Mandrake":
        klass = oz.Mandrake.get_class(tdl, config, auto, output_disk)
    elif tdl.distro == "Mandriva":
        klass = oz.Mandriva.get_class(tdl, config, auto, output_disk)

    if klass is None:
        raise oz.OzException.OzException("Unsupported " + tdl.distro + " update " + tdl.update)

    return klass

def distrolist():
    """
    Function to print out a list of supported distributions.
    """
    print "   Fedora: 7, 8, 9, 10, 11, 12, 13, 14, 15, 16"
    print "   Fedora Core: 1, 2, 3, 4, 5, 6"
    print "   RHEL 2.1: GOLD, U2, U3, U4, U5, U6"
    print "   RHEL 3: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   RHEL 4: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   RHEL 5: GOLD, U1, U2, U3, U4, U5, U6, U7, U8"
    print "   RHEL 6: 0, 1, 2"
    print "   Ubuntu: 6.06[.1,.2], 6.10, 7.04, 7.10, 8.04[.1,.2,.3,.4], 8.10, 9.04, 9.10, 10.04[.1,.2,.3], 10.10, 11.04, 11.10"
    print "   Windows: 2000, XP, 2003, 7, 2008"
    print "   RHL: 7.0, 7.1, 7.2, 7.3, 8, 9"
    print "   OpenSUSE: 10.3, 11.0, 11.1, 11.2, 11.3, 11.4"
    print "   CentOS 3: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   CentOS 4: GOLD, U1, U2, U3, U4, U5, U6, U7, U8, U9"
    print "   CentOS 5: GOLD, U1, U2, U3, U4, U5"
    print "   CentOS 6: 0, 1"
    print "   Scientific Linux 4: U9"
    print "   Scientific Linux 5: U6"
    print "   Scientific Linux 6: 0"
    print "   Scientific Linux CERN 5: U7, U8"
    print "   Scientific Linux CERN 6: 2"
    print "   OEL 6: 0, 1"
    print "   Debian: 5, 6"
    print "   Mandrake: 8.2, 9.1, 9.2, 10.0, 10.1"
    print "   Mandriva: 2005, 2006.0, 2007.0, 2008.0"
