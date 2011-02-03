# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import urlparse
import os

def generate_full_auto_path(relative):
    # all of the automated installation paths are installed to $pkg_path/auto,
    # so we just need to find it and generate the right path here
    pkg_path = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(pkg_path, "auto", relative))

def generate_full_guesttools_path(relative):
    pkg_path = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(pkg_path, "guesttools", relative))

# kind of a funny function.  When we are using URL based installs, we can't
# allow localhost URLs (since the URL is embedded into the installer, the
# install is guaranteed to fail with localhost URLs)
def deny_localhost(url):
    p = urlparse.urlparse(url)
    if p[1] == "localhost" or p[1] == "localhost.localdomain" or p[1] == "127.0.0.1":
        raise Exception, "Can not use localhost for an URL based install"

def executable_exists(program):
    def is_exe(fpath):
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

# a function to copy files sparsely.  The logic here is all taken from coreutils
# cp, specifically 'sparse_copy'
def copyfile_sparse(src, dest):
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
