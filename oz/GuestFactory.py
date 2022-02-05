# Copyright (C) 2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2017  Chris Lalancette <clalancette@gmail.com>

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

import oz.OzException

os_dict = {
    'Fedora': 'Fedora',
    'FedoraCore': 'FedoraCore',
    'FC': 'FedoraCore',
    'RedHatEnterpriseLinux-2.1': 'RHEL_2_1',
    'RHEL-2.1': 'RHEL_2_1',
    'RedHatEnterpriseLinux-3': 'RHEL_3',
    'RHEL-3': 'RHEL_3',
    'CentOS-3': 'RHEL_3',
    'RedHatEnterpriseLinux-4': 'RHEL_4',
    'RHEL-4': 'RHEL_4',
    'CentOS-4': 'RHEL_4',
    'ScientificLinux-4': 'RHEL_4',
    'SL-4': 'RHEL_4',
    'RedHatEnterpriseLinux-5': 'RHEL_5',
    'RHEL-5': 'RHEL_5',
    'CentOS-5': 'RHEL_5',
    'OL-5': 'RHEL_5',
    'ScientificLinux-5': 'RHEL_5',
    'SL-5': 'RHEL_5',
    'ScientificLinuxCern-5': 'RHEL_5',
    'SLC-5': 'RHEL_5',
    'RedHatEnterpriseLinux-6': 'RHEL_6',
    'RHEL-6': 'RHEL_6',
    'CentOS-6': 'RHEL_6',
    'ScientificLinux-6': 'RHEL_6',
    'SL-6': 'RHEL_6',
    'ScientificLinuxCern-6': 'RHEL_6',
    'SLC-6': 'RHEL_6',
    'OracleEnterpriseLinux-6': 'RHEL_6',
    'OEL-6': 'RHEL_6',
    'OL-6': 'RHEL_6',
    'RHEL-7': 'RHEL_7',
    'CentOS-7': 'RHEL_7',
    'RHEL-8': 'RHEL_8',
    'CentOS-8': 'RHEL_8',
    'RHEL-9': 'RHEL_9',
    'CentOS-9': 'RHEL_9',
    'Ubuntu': 'Ubuntu',
    'Windows': 'Windows',
    'RedHatLinux': 'RHL',
    'RHL': 'RHL',
    'OpenSUSE': 'OpenSUSE',
    'Debian': 'Debian',
    'Mandrake': 'Mandrake',
    'Mandriva': 'Mandriva',
    'Mageia': 'Mageia',
    'FreeBSD': 'FreeBSD',
}


def guest_factory(tdl, config, auto, output_disk=None, netdev=None,
                  diskbus=None, macaddress=None):
    """
    Factory function return an appropriate Guest object based on the TDL.
    The arguments are:

    tdl    - The TDL object to be used.  The return object will be determined
             based on the distro and version from the TDL.
    config - A ConfigParser object that contains configuration.  If None is
             passed for the config, Oz defaults will be used.
    auto   - An unattended installation file to be used for the
             installation.  If None is passed for auto, then Oz will use
             a known-working unattended installation file.
    output_disk - An optional string argument specifying the path to the
                  disk to be written to.
    netdev - An optional string argument specifying the type of network device
             to be used during installation.  If specified, this will override
             the default that Oz uses.
    diskbus - An optional string argument specifying the type of disk device
              to be used during installation.  If specified, this will override
              the default that Oz uses.
    macaddress - An optional string argument specifying the MAC address to use
                 for the guest.
    """

    klass = None
    for name, importname in os_dict.items():
        if tdl.distro == name:
            # we found the matching module; import and call the get_class method
            module = __import__('oz.' + importname)
            klass = getattr(module, importname).get_class(tdl, config, auto,
                                                          output_disk, netdev,
                                                          diskbus, macaddress)
            break

    if klass is None:
        raise oz.OzException.OzException("Unsupported " + tdl.distro + " update " + tdl.update)

    return klass


def distrolist():
    """
    Function to print out a list of supported distributions.
    """
    strings = []
    for importname in os_dict.values():
        module = __import__('oz.' + importname)
        support = getattr(module, importname).get_supported_string()
        tmp = '   ' + support
        if tmp not in strings:
            strings.append(tmp)

    strings.sort()
    print('\n'.join(strings))
