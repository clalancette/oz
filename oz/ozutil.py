# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

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
Miscellaneous utility functions.
"""

import os
import socket
import fcntl
import struct
import random

def generate_full_auto_path(relative):
    """
    Function to find the absolute path to an unattended installation file.
    """
    # all of the automated installation paths are installed to $pkg_path/auto,
    # so we just need to find it and generate the right path here
    pkg_path = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(pkg_path, "auto", relative))

def generate_full_guesttools_path(relative):
    """
    Function to find the absolute path to a guest tools executable.
    """
    pkg_path = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(pkg_path, "guesttools", relative))

def executable_exists(program):
    """
    Function to find out whether an executable exists in the PATH
    of the user.  If so, the absolute path to the executable is returned.
    If not, an exception is raised.
    """
    def is_exe(fpath):
        """
        Helper method to check if a file exists and is executable
        """
        return os.path.exists(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    raise Exception, "Could not find %s" % (program)

def copyfile_sparse(src, dest):
    """
    Function to copy a file sparsely if possible.  The logic here is
    all taken from coreutils cp, specifically the 'sparse_copy' function.
    """
    src_fd = os.open(src, os.O_RDONLY)
    dest_fd = os.open(dest, os.O_WRONLY|os.O_CREAT|os.O_TRUNC)

    sb = os.fstat(src_fd)

    # See io_blksize() in coreutils for an explanation of why 32*1024
    buf_size = max(32*1024, sb.st_blksize)

    size = sb.st_size
    destlen = 0
    while size != 0:
        buf = os.read(src_fd, min(buf_size, size))
        if len(buf) == 0:
            break

        buflen = len(buf)
        if buf == '\0'*buflen:
            os.lseek(dest_fd, buflen, os.SEEK_CUR)
        else:
            # FIXME: check out the python implementation of write, we might have
            # to handle EINTR here
            os.write(dest_fd, buf)

        destlen += len(buf)
        size -= len(buf)

    os.ftruncate(dest_fd, destlen)

    os.close(src_fd)
    os.close(dest_fd)

def bsd_split(line, digest_type):
    """
    Function to split a BSD-style checksum line into a filename and checksum.
    """
    current = len(digest_type)

    if line[current] == ' ':
        current += 1

    if line[current] != '(':
        return None, None

    current += 1

    # find end of filename.  The BSD 'md5' and 'sha1' commands do not escape
    # filenames, so search backwards for the last ')'
    file_end = line.rfind(')')
    if file_end == -1:
        # could not find the ending ), fail
        return None, None

    filename = line[current:file_end]

    line = line[(file_end + 1):]
    line = line.lstrip()

    if line[0] != '=':
        return None, None

    line = line[1:]

    line = line.lstrip()
    if line[-1] == '\n':
        line = line[:-1]

    return line, filename

def sum_split(line, digest_bits):
    """
    Function to split a normal Linux checksum line into a filename and checksum.
    """
    digest_hex_bytes = digest_bits / 4
    min_digest_line_length = digest_hex_bytes + 2 + 1 # length of hex message digest + blank and binary indicator (2 bytes) + minimum file length (1 byte)

    min_length = min_digest_line_length
    if line[0] == '\\':
        min_length = min_length + 1
    if len(line) < min_length:
        # if the line is too short, skip it
        return None, None

    if line[0] == '\\':
        current = digest_hex_bytes + 1
        hex_digest = line[1:current]
        escaped_filename = True
    else:
        current = digest_hex_bytes
        hex_digest = line[0:current]
        escaped_filename = False

    # if the digest is not immediately followed by a white space, it is an
    # error
    if line[current] != ' ' and line[current] != '\t':
        return None, None

    current += 1
    # if the whitespace is not immediately followed by another space or a *,
    # it is an error
    if line[current] != ' ' and line[current] != '*':
        return None, None

    if line[current] == '*':
        binary = True

    current += 1

    if line[-1] == '\n':
        filename = line[current:-1]
    else:
        filename = line[current:]

    if escaped_filename:
        # FIXME: a \0 is not allowed in the sum file format, but
        # string_escape allows it.  We'd probably have to implement our
        # own codec to fix this
        filename = filename.decode('string_escape')

    return hex_digest, filename

def get_sum_from_file(sumfile, file_to_find, digest_bits, digest_type):
    """
    Function to get a checksum digest out of a checksum file given a filename.
    """
    retval = None

    f = open(sumfile, 'r')
    for line in f.xreadlines():
        binary = False

        # remove any leading whitespace
        line = line.lstrip()

        # ignore blank lines
        if len(line) == 0:
            continue

        # ignore comment lines
        if line[0] == '#':
            continue

        if line.startswith(digest_type):
            # OK, if it starts with a string of ["MD5", "SHA1", "SHA256"], then
            # this is a BSD-style sumfile
            hex_digest, filename = bsd_split(line, digest_type)
        else:
            # regular sumfile
            hex_digest, filename = sum_split(line, digest_bits)

        if hex_digest is None or filename is None:
            continue

        if filename == file_to_find:
            retval = hex_digest
            break

    f.close()

    return retval

def get_md5sum_from_file(sumfile, file_to_find):
    """
    Function to get an MD5 checksum out of a checksum file given a filename.
    """
    return get_sum_from_file(sumfile, file_to_find, 128, "MD5")

def get_sha1sum_from_file(sumfile, file_to_find):
    """
    Function to get a SHA1 checksum out of a checksum file given a filename.
    """
    return get_sum_from_file(sumfile, file_to_find, 160, "SHA1")

def get_sha256sum_from_file(sumfile, file_to_find):
    """
    Function to get a SHA256 checksum out of a checksum file given a filename.
    """
    return get_sum_from_file(sumfile, file_to_find, 256, "SHA256")

def string_to_bool(instr):
    """
    Function to take a string and determine whether it is True, Yes, False,
    or No.  It takes a single argument, which is the string to examine.

    Returns True if instr is "Yes" or "True", False if instr is "No"
    or "False", and None otherwise.
    """
    lower = instr.lower()
    if lower == 'no' or lower == 'false':
        return False
    if lower == 'yes' or lower == 'true':
        return True
    return None

def get_ip_from_interface(ifname):
    """
    Function to take an interface name and discover the IPv4 address that is
    connected with that interface.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # 0x8915 is SIOCGIFADDR
    ipaddr = socket.inet_ntoa(fcntl.ioctl(s.fileno(), 0x8915,
                                          struct.pack('256s',
                                                      ifname[:15]))[20:24])

    s.close()

    return ipaddr

def generate_macaddress():
    """
    Function to generate a random MAC address.
    """
    mac = [0x52, 0x54, 0x00, random.randint(0x00, 0xff),
           random.randint(0x00, 0xff), random.randint(0x00, 0xff)]
    return ':'.join(map(lambda x:"%02x" % x, mac))
