# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012-2018  Chris Lalancette <clalancette@gmail.com>

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
Fedora installation
"""

import os

import oz.OzException
import oz.RedHat
import oz.ozutil


class FedoraConfiguration(object):
    """
    The configuration class for Fedora.
    """
    def __init__(self, has_virtio_channel, use_yum, use_dev_cdrom_device,
                 createpart, directkernel, default_netdev, default_diskbus,
                 brokenisomethod, haverepo, useuefi=False):
        self._has_virtio_channel = has_virtio_channel
        self._use_yum = use_yum
        self._use_dev_cdrom_device = use_dev_cdrom_device
        self._createpart = createpart
        self._directkernel = directkernel
        self._default_netdev = default_netdev
        self._default_diskbus = default_diskbus
        self._brokenisomethod = brokenisomethod
        self._haverepo = haverepo
        self._useuefi = useuefi

    @property
    def has_virtio_channel(self):
        """
        Property method for whether this Fedora version has a virtio channel.
        """
        return self._has_virtio_channel

    @property
    def use_yum(self):
        """
        Property method for whether this Fedora version uses yum or dnf.
        """
        return self._use_yum

    @property
    def use_dev_cdrom_device(self):
        """
        Property method for whether this Fedora version uses /dev/cdrom on the
        kickstart command-line.
        """
        return self._use_dev_cdrom_device

    @property
    def createpart(self):
        """
        Property method for whether to create partitions before installation.
        """
        return self._createpart

    @property
    def directkernel(self):
        """
        Property method for whether this Fedora version supports direct kernel boot.
        """
        return self._directkernel

    @property
    def default_netdev(self):
        """
        Property method for the default netdev for this Fedora version.
        """
        return self._default_netdev

    @property
    def default_diskbus(self):
        """
        Property method for the default diskbus for this Fedora version.
        """
        return self._default_diskbus

    @property
    def brokenisomethod(self):
        """
        Property method for whether to add method to the anaconda install line.
        """
        return self._brokenisomethod

    @property
    def haverepo(self):
        """
        Property method for whether to use 'repo=' or 'method=' on the anaconda install line.
        """
        return self._haverepo

    @property
    def useuefi(self):
        """
        Property method for whether to default to using UEFI as firmware or legacy method.
        """
        return self._useuefi


version_to_config = {
    '30': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True, useuefi=True),
    '29': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '28': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '27': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '26': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '25': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '24': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '23': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '22': FedoraConfiguration(has_virtio_channel=True, use_yum=False,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '21': FedoraConfiguration(has_virtio_channel=True, use_yum=True,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '20': FedoraConfiguration(has_virtio_channel=True, use_yum=True,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '19': FedoraConfiguration(has_virtio_channel=True, use_yum=True,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=False,
                              haverepo=True),
    '18': FedoraConfiguration(has_virtio_channel=True, use_yum=True,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '17': FedoraConfiguration(has_virtio_channel=True, use_yum=True,
                              use_dev_cdrom_device=True, createpart=False,
                              directkernel=None, default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '16': FedoraConfiguration(has_virtio_channel=True, use_yum=True,
                              use_dev_cdrom_device=False, createpart=False,
                              directkernel=None, default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '15': FedoraConfiguration(has_virtio_channel=True, use_yum=True,
                              use_dev_cdrom_device=False, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '14': FedoraConfiguration(has_virtio_channel=True, use_yum=True,
                              use_dev_cdrom_device=False, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '13': FedoraConfiguration(has_virtio_channel=False, use_yum=True,
                              use_dev_cdrom_device=False, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '12': FedoraConfiguration(has_virtio_channel=False, use_yum=True,
                              use_dev_cdrom_device=False, createpart=True,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '11': FedoraConfiguration(has_virtio_channel=False, use_yum=True,
                              use_dev_cdrom_device=False, createpart=True,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '10': FedoraConfiguration(has_virtio_channel=False, use_yum=True,
                              use_dev_cdrom_device=False, createpart=False,
                              directkernel="cpio", default_netdev='virtio',
                              default_diskbus='virtio', brokenisomethod=True,
                              haverepo=True),
    '9': FedoraConfiguration(has_virtio_channel=False, use_yum=True,
                             use_dev_cdrom_device=False, createpart=False,
                             directkernel="cpio", default_netdev='virtio',
                             default_diskbus='virtio', brokenisomethod=False,
                             haverepo=True),
    '8': FedoraConfiguration(has_virtio_channel=False, use_yum=True,
                             use_dev_cdrom_device=False, createpart=False,
                             directkernel="cpio", default_netdev=None,
                             default_diskbus=None, brokenisomethod=False,
                             haverepo=False),
    '7': FedoraConfiguration(has_virtio_channel=False, use_yum=True,
                             use_dev_cdrom_device=False, createpart=False,
                             directkernel="cpio", default_netdev=None,
                             default_diskbus=None, brokenisomethod=False,
                             haverepo=False),
}


class FedoraGuest(oz.RedHat.RedHatLinuxCDYumGuest):
    """
    Class for Fedora 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, and 29 installation.
    """
    # Note that the 'brokenisomethod' and 'haverepo' parameters are completely
    # ignored now; we leave it in place for backwards API compatibility.
    def __init__(self, tdl, config, auto, nicmodel, haverepo, diskbus,  # pylint: disable=unused-argument
                 brokenisomethod, output_disk=None, macaddress=None,    # pylint: disable=unused-argument
                 assumed_update=None):
        if int(tdl.update) < 31:
            self.config = version_to_config[tdl.update]
        else:
            self.config = version_to_config["30"]
        if nicmodel is None:
            nicmodel = self.config.default_netdev
        if diskbus is None:
            diskbus = self.config.default_diskbus
        self.assumed_update = assumed_update

        # Prior to Fedora-22, we use yum; on F-22 and later, we use dnf.
        oz.RedHat.RedHatLinuxCDYumGuest.__init__(self, tdl, config, auto,
                                                 output_disk, nicmodel, diskbus,
                                                 True, True, self.config.directkernel,
                                                 macaddress, self.config.use_yum)

        if self.assumed_update is not None:
            self.log.warning("==== WARN: TDL contains Fedora update %s, which is newer than Oz knows about; pretending this is Fedora %s, but this may fail ====", tdl.update, assumed_update)

        if self.config.has_virtio_channel:
            self.virtio_channel_name = 'org.fedoraproject.anaconda.log.0'

    def _modify_iso(self):
        """
        Method to modify the ISO for autoinstallation.
        """
        self._copy_kickstart(os.path.join(self.iso_contents, "ks.cfg"))

        if self.config.use_dev_cdrom_device:
            initrdline = "  append initrd=initrd.img inst.ks=cdrom:/dev/cdrom:/ks.cfg"
        else:
            initrdline = "  append initrd=initrd.img inst.ks=cdrom:/ks.cfg"
        if self.tdl.installtype == "url":
            if self.config.haverepo:
                initrdline += " inst.repo="
            else:
                initrdline += " inst.method="
            initrdline += self.url
        else:
            # if the installtype is iso, then due to a bug in anaconda we leave
            # out the method completely
            if not self.config.brokenisomethod:
                initrdline += " inst.method=cdrom:/dev/cdrom"
        # don't write the kickstart to the image, or else initial-setup
        # will think a root password has been set:
        # https://bugzilla.redhat.com/show_bug.cgi?id=2015490
        initrdline += " inst.nosave=output_ks"
        self._modify_isolinux(initrdline)

    def generate_diskimage(self, size=10*1024*1024*1024, force=False):
        """
        Method to generate a diskimage.  By default, a blank diskimage of
        10 GiB will be created; the caller can override this with the size
        parameter, specified in bytes.  If force is False (the default), then
        a diskimage will not be created if a cached JEOS is found.  If
        force is True, a diskimage will be created regardless of whether a
        cached JEOS exists.  See the oz-install man page for more
        information about JEOS caching.
        """
        # If given a blank diskimage, Fedora 11/12 stops very early in
        # install with a message about losing all of your data on the
        # drive (it differs between them).
        #
        # To avoid that message, just create a partition table that spans
        # the entire disk
        return self._internal_generate_diskimage(size, force, self.config.createpart)

    def get_auto_path(self):
        """
        Method to create the correct path to the Fedora kickstart files.
        """
        # If we are doing our best with an unknown Fedora update, use the
        # newest known auto file; otherwise, do the usual thing.
        if self.assumed_update is not None:
            return oz.ozutil.generate_full_auto_path(self.tdl.distro + self.assumed_update + ".auto")
        return oz.ozutil.generate_full_auto_path(self.tdl.distro + self.tdl.update + ".auto")


def get_class(tdl, config, auto, output_disk=None, netdev=None, diskbus=None,
              macaddress=None):
    """
    Factory method for Fedora installs.
    """

    newest = sorted(version_to_config.keys(), key=int)[-1]
    if tdl.update == 'rawhide' or int(tdl.update) > int(newest):
        return FedoraGuest(tdl, config, auto, netdev, True, diskbus, False,
                           output_disk, macaddress, newest)

    if tdl.update in version_to_config.keys():
        return FedoraGuest(tdl, config, auto, netdev, True, diskbus, False,
                           output_disk, macaddress, None)


def get_supported_string():
    """
    Return supported versions as a string.
    """
    return "Fedora: " + ", ".join(sorted(version_to_config.keys(), key=int))
