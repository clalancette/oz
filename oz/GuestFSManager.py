# Copyright (C) 2017  Chris Lalancette <clalancette@gmail.com>

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
Helper class for managing a GuestFS connection
"""

import functools
import logging

import guestfs

import lxml.etree

import oz.OzException


class GuestFS(object):
    '''
    A wrapper class over guestfs to make some common operations easier.
    '''
    def __init__(self, input_disk, input_disk_type):
        self.log = logging.getLogger(__name__)

        self.g_handle = guestfs.GuestFS(python_return_dict=True)

        self.log.debug("Adding disk image %s", input_disk)
        # NOTE: we use "add_drive_opts" here so we can specify the type
        # of the diskimage.  Otherwise it might be possible for an attacker
        # to fool libguestfs with a specially-crafted diskimage that looks
        # like a qcow2 disk (thanks to rjones for the tip)
        self.g_handle.add_drive_opts(input_disk, format=input_disk_type)

        self.log.debug("Launching guestfs")
        self.g_handle.launch()

    def create_msdos_partition_table(self):
        '''
        A method to create a new msdos partition table on a disk.
        '''
        devices = self.g_handle.list_devices()
        self.g_handle.part_init(devices[0], "msdos")
        self.g_handle.part_add(devices[0], 'p', 1, 2)

    def mount_partitions(self):
        '''
        A method to mount existing partitions on a disk inside of guestfs.
        '''
        self.log.debug("Inspecting guest OS")
        roots = self.g_handle.inspect_os()

        if not roots:
            raise oz.OzException.OzException("No operating systems found on the disk")

        self.log.debug("Getting mountpoints")
        already_mounted = {}
        for root in roots:
            self.log.debug("Root device: %s", root)

            # the problem here is that the list of mountpoints returned by
            # inspect_get_mountpoints is in no particular order.  So if the
            # diskimage contains /usr and /usr/local on different devices,
            # but /usr/local happened to come first in the listing, the
            # devices would get mapped improperly.  The clever solution here is
            # to sort the mount paths by length; this will ensure that they
            # are mounted in the right order.  Thanks to rjones for the hint,
            # and the example code that comes from the libguestfs.org python
            # example page.
            mps = self.g_handle.inspect_get_mountpoints(root)

            for device in sorted(mps.keys(), key=len):
                try:
                    # Here we check to see if the device was already mounted.
                    # If it was, we skip over this mountpoint and go to the
                    # next one.  This can happen, for instance, on btrfs volumes
                    # with snapshots.  In that case, we'll always take the
                    # "original" backing filesystem, and not the snapshots,
                    # which seems to work in practice.
                    if already_mounted[device] == mps[device]:
                        continue
                except KeyError:
                    # If we got a KeyError exception, we know that we haven't
                    # yet mounted this filesystem, so continue on.
                    pass

                try:
                    self.g_handle.mount_options('', mps[device], device)
                    already_mounted[device] = mps[device]
                except Exception:
                    if device == '/':
                        # If we cannot mount root, we may as well give up
                        raise
                    else:
                        # some custom guests may have fstab content with
                        # "nofail" as a mount option.  For example, images
                        # built for EC2 with ephemeral mappings.  These
                        # fail at this point.  Allow things to continue.
                        # Profound failures will trigger later on during
                        # the process.
                        self.log.warning("Unable to mount (%s) on (%s) - trying to continue", mps[device], device)

    def remove_if_exists(self, path):
        """
        Method to remove a file if it exists in the disk image.
        """
        if self.g_handle.exists(path):
            self.g_handle.rm_rf(path)

    def move_if_exists(self, orig_path, replace_path):
        """
        Method to move a file if it exists in the disk image.
        """
        if self.g_handle.exists(orig_path):
            self.g_handle.mv(orig_path, replace_path)

    def path_backup(self, orig):
        """
        Method to backup a file in the disk image.
        """
        self.move_if_exists(orig, orig + ".ozbackup")

    def path_restore(self, orig):
        """
        Method to restore a backup file in the disk image.
        """
        backup = orig + ".ozbackup"
        self.remove_if_exists(orig)
        self.move_if_exists(backup, orig)

    def exists(self, filename):
        '''
        A passthrough method for the guestfs functionality of "exists".
        '''
        return self.g_handle.exists(filename)

    def rm(self, filename):
        '''
        A passthrough method for the guestfs functionality of "rm".
        '''
        return self.g_handle.rm(filename)

    def glob_expand(self, glob):
        '''
        A passthrough method for the guestfs functionality of "glob_expand".
        '''
        return self.g_handle.glob_expand(glob)

    def mkdir(self, directory):
        '''
        A passthrough method for the guestfs functionality of "mkdir".
        '''
        return self.g_handle.mkdir(directory)

    def ln_sf(self, src, dst):
        '''
        A passthrough method for the guestfs functionality of "ln_sf".
        '''
        return self.g_handle.ln_sf(src, dst)

    def chmod(self, mode, fname):
        '''
        A passthrough method for the guestfs functionality of "chmod".
        '''
        return self.g_handle.chmod(mode, fname)

    def cat(self, fname):
        '''
        A passthrough method for the guestfs functionality of "cat".
        '''
        return self.g_handle.cat(fname)

    def upload(self, src, dest):
        '''
        A passthrough method for the guestfs functionalityh of "upload".
        '''
        return self.g_handle.upload(src, dest)

    def cleanup(self):
        '''
        A method to cleanup after finishing with a guestfs handle.
        '''
        self.log.info("Cleaning up guestfs handle")
        self.log.debug("Syncing")
        self.g_handle.sync()

        self.log.debug("Unmounting all")
        self.g_handle.umount_all()
        self.g_handle.kill_subprocess()
        self.g_handle.close()


def GuestFSLibvirtFactory(libvirt_xml, libvirt_conn):
    '''
    A factory function for getting a GuestFS object from a libvirt XML and a connection.
    '''
    log = logging.getLogger(__name__)

    input_doc = lxml.etree.fromstring(libvirt_xml)
    namenode = input_doc.xpath('/domain/name')
    if len(namenode) != 1:
        raise oz.OzException.OzException("invalid libvirt XML with no name")
    input_name = namenode[0].text
    disks = input_doc.xpath('/domain/devices/disk')
    if len(disks) != 1:
        log.warning("Oz given a libvirt domain with more than 1 disk; using the first one parsed")
    source = disks[0].xpath('source')
    if len(source) != 1:
        raise oz.OzException.OzException("invalid <disk> entry without a source")
    input_disk = source[0].get('file')
    driver = disks[0].xpath('driver')
    if not driver:
        input_disk_type = 'raw'
    elif len(driver) == 1:
        input_disk_type = driver[0].get('type')
    else:
        raise oz.OzException.OzException("invalid <disk> entry without a driver")

    for domid in libvirt_conn.listDomainsID():
        try:
            doc = lxml.etree.fromstring(libvirt_conn.lookupByID(domid).XMLDesc(0))
        except Exception:
            log.debug("Could not get XML for domain ID (%s) - it may have disappeared (continuing)",
                      domid)
            continue

        namenode = doc.xpath('/domain/name')
        if len(namenode) != 1:
            # hm, odd, a domain without a name?
            raise oz.OzException.OzException("Saw a domain without a name, something weird is going on")
        if input_name == namenode[0].text:
            raise oz.OzException.OzException("Cannot setup ICICLE generation on a running guest")
        disks = doc.xpath('/domain/devices/disk')
        if len(disks) < 1:
            # odd, a domain without a disk, but don't worry about it
            continue
        for guestdisk in disks:
            for source in guestdisk.xpath("source"):
                # FIXME: this will only work for files; we can make it work
                # for other things by following something like:
                # http://git.annexia.org/?p=libguestfs.git;a=blob;f=src/virt.c;h=2c6be3c6a2392ab8242d1f4cee9c0d1445844385;hb=HEAD#l169
                filename = str(source.get('file'))
                if filename == input_disk:
                    raise oz.OzException.OzException("Cannot setup ICICLE generation on a running disk")

    return GuestFS(input_disk, input_disk_type)
