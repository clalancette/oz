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
Miscellaneous utility functions.
"""

try:
    from collections.abc import Callable
except ImportError:
    from collections import Callable
try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import errno
import fcntl
import ftplib
import gzip
import logging
import os
import random
import select
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time
import urllib

import lxml.etree

import monotonic

import requests


def generate_full_auto_path(relative):
    """
    Function to find the absolute path to an unattended installation file.
    """
    # all of the automated installation paths are installed to $pkg_path/auto,
    # so we just need to find it and generate the right path here
    if relative is None:
        raise Exception("The relative path cannot be None")

    pkg_path = os.path.dirname(__file__)
    return os.path.abspath(os.path.join(pkg_path, "auto", relative))


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

    if program is None:
        raise Exception("Invalid program name passed")

    fpath, fname_unused = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    raise Exception("Could not find %s" % (program))


def write_bytes_to_fd(fd, buf):
    """
    Function to write all bytes in "buf" to "fd".  This handles both EINTR
    and short writes.
    """
    size = len(buf)
    offset = 0
    while size > 0:
        try:
            bytes_written = os.write(fd, buf[offset:])
            offset += bytes_written
            size -= bytes_written
        except OSError as err:
            # python's os.write() can raise an exception on EINTR, which
            # according to the man page can happen if a signal was
            # received before any data was written.  Therefore, we don't
            # need to update destlen or size, but just retry
            if err.errno == errno.EINTR:
                continue
            raise

    return offset


def read_bytes_from_fd(fd, num):
    """
    Function to read and return bytes from fd.  This handles the EINTR situation
    where no bytes were read before a signal happened.
    """
    read_done = False
    while not read_done:
        try:
            ret = os.read(fd, num)
            read_done = True
        except OSError as err:
            # python's os.read() can raise an exception on EINTR, which
            # according to the man page can happen if a signal was
            # received before any data was read.  In this case we need to retry
            if err.errno == errno.EINTR:
                continue
            raise

    return ret


def copyfile_sparse(src, dest):
    """
    Function to copy a file sparsely if possible.  The logic here is
    all taken from coreutils cp, specifically the 'sparse_copy' function.
    """
    if src is None:
        raise Exception("Source of copy cannot be None")
    if dest is None:
        raise Exception("Destination of copy cannot be None")

    if not os.path.exists(src):
        raise Exception("Source '%s' does not exist" % (src))

    if os.path.exists(dest) and os.path.samefile(src, dest):
        raise Exception("Source '%s' and dest '%s' are the same file" % (src, dest))

    base = os.path.dirname(dest)
    if not os.path.exists(base):
        mkdir_p(base)

    src_fd = os.open(src, os.O_RDONLY)

    try:
        dest_fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)

        try:
            sb = os.fstat(src_fd)

            # See io_blksize() in coreutils for an explanation of why 32*1024
            buf_size = max(32 * 1024, sb.st_blksize)

            size = sb.st_size
            destlen = 0
            while size != 0:
                buf = read_bytes_from_fd(src_fd, min(buf_size, size))
                if not buf:
                    break

                buflen = len(buf)
                if buf == '\0' * buflen:
                    os.lseek(dest_fd, buflen, os.SEEK_CUR)
                else:
                    write_bytes_to_fd(dest_fd, buf)

                destlen += buflen
                size -= buflen

            os.ftruncate(dest_fd, destlen)

        finally:
            os.close(dest_fd)
    finally:
        os.close(src_fd)


def bsd_split(line, digest_type):
    """
    Function to split a BSD-style checksum line into a filename and
    checksum.
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
    Function to split a normal Linux checksum line into a filename and
    checksum.
    """
    digest_hex_bytes = digest_bits // 4
    min_digest_line_length = digest_hex_bytes + 2 + 1  # length of hex message digest + blank and binary indicator (2 bytes) + minimum file length (1 byte)

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

    current += 1

    filename = line[current:]
    if line[-1] == '\n':
        filename = line[current:-1]

    if escaped_filename:
        # FIXME: a \0 is not allowed in the sum file format, but
        # string_escape allows it.  We'd probably have to implement our
        # own codec to fix this
        if sys.version_info.major == 2:
            filename = filename.decode('string_escape')
        else:
            filename = filename.encode('utf-8').decode('unicode_escape')

    return hex_digest, filename


def get_sum_from_file(sumfile, file_to_find, digest_bits, digest_type):
    """
    Function to get a checksum digest out of a checksum file given a
    filename.
    """
    retval = None

    with open(sumfile, 'r') as f:
        for line in f:
            # remove any leading whitespace
            line = line.lstrip()

            # ignore blank lines
            if not line:
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
    Function to get a SHA256 checksum out of a checksum file given a
    filename.
    """
    return get_sum_from_file(sumfile, file_to_find, 256, "SHA256")


def string_to_bool(instr):
    """
    Function to take a string and determine whether it is True, Yes, False,
    or No.  It takes a single argument, which is the string to examine.

    Returns True if instr is "Yes" or "True", False if instr is "No"
    or "False", and None otherwise.
    """
    if instr is None:
        raise Exception("Input string was None!")
    lower = instr.lower()
    if lower == 'no' or lower == 'false':
        return False
    if lower == 'yes' or lower == 'true':
        return True
    return None


def generate_macaddress():
    """
    Function to generate a random MAC address.
    """
    mac = [0x52, 0x54, 0x00, random.randint(0x00, 0xff),
           random.randint(0x00, 0xff), random.randint(0x00, 0xff)]
    return ':'.join(["%02x" % x for x in mac])


class SubprocessException(Exception):
    """
    Class for subprocess exceptions.  In addition to a error message, it
    also has a retcode member that has the returncode from the command.
    """
    def __init__(self, msg, retcode):
        Exception.__init__(self, msg)
        self.retcode = retcode


def subprocess_check_output(*popenargs, **kwargs):
    """
    Function to call a subprocess and gather the output.
    """
    if 'stdout' in kwargs:
        raise ValueError('stdout argument not allowed, it will be overridden.')
    if 'stderr' in kwargs:
        raise ValueError('stderr argument not allowed, it will be overridden.')

    printfn = None
    if 'printfn' in kwargs:
        printfn = kwargs['printfn']
        del kwargs['printfn']

    executable_exists(popenargs[0][0])

    process = subprocess.Popen(stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               *popenargs, **kwargs)

    poller = select.poll()
    select_POLLIN_POLLPRI = select.POLLIN | select.POLLPRI
    poller.register(process.stdout.fileno(), select_POLLIN_POLLPRI)
    poller.register(process.stderr.fileno(), select_POLLIN_POLLPRI)

    stdout = ''
    stderr = ''
    retcode = process.poll()
    while retcode is None:
        start = time.time()
        try:
            ready = poller.poll(1000)
        except select.error as e:
            if e.args[0] == errno.EINTR:
                continue
            raise

        for fd, mode in ready:
            if mode & select_POLLIN_POLLPRI:
                data = os.read(fd, 4096)
                if not data:
                    poller.unregister(fd)
                else:
                    data = data.decode('utf-8')
                    if printfn is not None:
                        printfn(data)
                    if fd == process.stdout.fileno():
                        stdout += data
                    else:
                        stderr += data
            else:
                # Ignore hang up or errors.
                poller.unregister(fd)

        end = time.time()
        if (end - start) < 1:
            time.sleep(1 - (end - start))
        retcode = process.poll()

    tmpout, tmperr = process.communicate()

    tmpout = tmpout.decode('utf-8')
    tmperr = tmperr.decode('utf-8')

    stdout += tmpout
    stderr += tmperr
    if printfn is not None:
        printfn(tmperr)
        printfn(tmpout)

    if retcode:
        cmd = str(popenargs)
        output = stderr + stdout
        if isinstance(output, bytes):
            output = output.decode()
        raise SubprocessException("'%s' failed(%d): %s" % (cmd, retcode, output), retcode)

    return (stdout, stderr, retcode)


def mkdir_p(path):
    """
    Function to make a directory and all intermediate directories as
    necessary.  The functionality differs from os.makedirs slightly, in
    that this function does *not* raise an error if the directory already
    exists.
    """
    if path is None:
        raise Exception("Path cannot be None")

    if path == '':
        # this can happen if the user did something like call os.path.dirname()
        # on a file without directories.  Since os.makedirs throws an exception
        # in that case, check for it here and allow it.
        return

    try:
        os.makedirs(path)
    except OSError as err:
        if err.errno != errno.EEXIST or not os.path.isdir(path):
            raise


def copytree_merge(src, dst, symlinks=False, ignore=None):
    """
    Function to copy an entire directory recursively. The functionality
    differs from shutil.copytree, in that this function does *not* raise
    an exception if the directory already exists.
    It is based on: http://docs.python.org/2.7/library/shutil.html#copytree-example
    """
    names = os.listdir(src)
    if ignore is not None:
        ignored_names = ignore(src, names)
    else:
        ignored_names = set()

    mkdir_p(dst)
    errors = []
    for name in names:
        if name in ignored_names:
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree_merge(srcname, dstname, symlinks, ignore)
            else:
                shutil.copy2(srcname, dstname)
            # FIXME: What about devices, sockets etc.?
        except (IOError, os.error) as why:
            errors.append((srcname, dstname, str(why)))
        # catch the Error from the recursive copytree so that we can
        # continue with other files
        except shutil.Error as err:
            errors.extend(err.args[0])
    try:
        shutil.copystat(src, dst)
    except OSError as why:
        errors.extend((src, dst, str(why)))
    if errors:
        raise shutil.Error(errors)


def copy_modify_file(inname, outname, subfunc):
    """
    Function to copy a file from inname to outname, passing each line
    through subfunc first.  subfunc is expected to be a method that takes
    a single argument in (the next line), and returns a string to be
    written to the output file after modification (if any).
    """
    if inname is None:
        raise Exception("input filename is None")
    if outname is None:
        raise Exception("output filename is None")
    if subfunc is None:
        raise Exception("subfunction is None")
    if not isinstance(subfunc, Callable):
        raise Exception("subfunction is not callable")

    infile = open(inname, 'r')
    outfile = open(outname, 'w')

    for line in infile:
        outfile.write(subfunc(line))

    infile.close()
    outfile.close()


def write_cpio(inputdict, outputfile):
    """
    Function to write a CPIO archive in the "New ASCII Format".  The
    inputlist is a dictionary of files to put in the archive, where the
    dictionary key is the path to the file on the local filesystem and the
    dictionary value is the location that the file should have in the cpio
    archive.  The outputfile is the location of the final cpio archive that
    will be written.
    """
    if inputdict is None:
        raise Exception("input dictionary was None")
    if outputfile is None:
        raise Exception("output file was None")

    outf = open(outputfile, "w")

    try:
        for inputfile, destfile in list(inputdict.items()):
            inf = open(inputfile, 'r')
            st = os.fstat(inf.fileno())

            # 070701 is the magic for new CPIO (newc in cpio parlance)
            outf.write("070701")
            # inode (really just needs to be unique)
            outf.write("%08x" % (st[stat.ST_INO]))
            # mode
            outf.write("%08x" % (st[stat.ST_MODE]))
            # uid is 0
            outf.write("00000000")
            # gid is 0
            outf.write("00000000")
            # nlink (always a single link for a single file)
            outf.write("00000001")
            # mtime
            outf.write("%08x" % (st[stat.ST_MTIME]))
            # filesize
            outf.write("%08x" % (st[stat.ST_SIZE]))
            # devmajor
            outf.write("%08x" % (os.major(st[stat.ST_DEV])))
            # dev minor
            outf.write("%08x" % (os.minor(st[stat.ST_DEV])))
            # rdevmajor (always 0)
            outf.write("00000000")
            # rdevminor (always 0)
            outf.write("00000000")
            # namesize (the length of the name plus 1 for the NUL padding)
            outf.write("%08x" % (len(destfile) + 1))
            # check (always 0)
            outf.write("00000000")
            # write the name of the inputfile minus the leading /
            stripped = destfile.lstrip('/')
            outf.write(stripped)

            # we now need to write sentinel NUL byte(s).  We need to make the
            # header (110 bytes) plus the filename, plus the sentinel a
            # multiple of 4 bytes.  Note that we always need at *least* one NUL,
            # so if it is exactly a multiple of 4 we need to write 4 NULs
            outf.write("\x00" * (4 - ((110 + len(stripped)) % 4)))

            # now write the data from the input file
            outf.writelines(inf)
            inf.close()

            # we now need to write out NUL byte(s) to make it a multiple of 4.
            # note that unlike the name, we do *not* have to have any NUL bytes,
            # so if it is already aligned on 4 bytes do nothing
            remainder = st[stat.ST_SIZE] % 4
            if remainder != 0:
                outf.write("\x00" * (4 - remainder))

        # now that we have written all of the file entries, write the trailer
        outf.write("070701")
        # zero inode
        outf.write("00000000")
        # zero mode
        outf.write("00000000")
        # zero uid
        outf.write("00000000")
        # zero gid
        outf.write("00000000")
        # one nlink
        outf.write("00000001")
        # zero mtime
        outf.write("00000000")
        # zero filesize
        outf.write("00000000")
        # zero devmajor
        outf.write("00000000")
        # zero devminor
        outf.write("00000000")
        # zero rdevmajor
        outf.write("00000000")
        # zero rdevminor
        outf.write("00000000")
        # 0xB namesize
        outf.write("0000000B")
        # zero check
        outf.write("00000000")
        # trailer
        outf.write("TRAILER!!!")

        # finally, we need to pad to the closest 512 bytes
        outf.write("\x00" * (512 - (outf.tell() % 512)))
    except:
        os.unlink(outputfile)
        raise

    outf.close()


def config_get_key(config, section, key, default):
    """
    Function to retrieve config parameters out of the config file.
    """
    if config is not None and config.has_section(section) and config.has_option(section, key):
        return config.get(section, key)
    return default


def config_get_boolean_key(config, section, key, default):
    """
    Function to retrieve boolean config parameters out of the config file.
    """
    value = config_get_key(config, section, key, None)
    if value is None:
        return default

    retval = string_to_bool(value)
    if retval is None:
        raise Exception("Configuration parameter '%s' must be True, Yes, False, or No" % (key))

    return retval


def config_get_path(config, section, key, default):
    """
    Function to get an user-expanded path out of the config file at
    the passed in section and key.  If the value is not in the config
    file, then the default value is returned.  If the expanded path is
    not absolute, an error is raised.
    """
    path = os.path.expanduser(config_get_key(config, section, key, default))
    if not os.path.isabs(path):
        raise Exception("Config key '%s' must have an absolute path" % (key))
    return path


def rmtree_and_sync(directory):
    """
    Function to remove a directory tree and do an fsync afterwards.  Because
    the removal of the directory tree can cause a lot of metadata updates, it
    can cause a lot of disk activity.  By doing the fsync, we ensure that any
    metadata updates caused by us will not cause subsequent steps to fail.  This
    cannot help if the system is otherwise very busy, but it does ensure that
    the problem is not self-inflicted.
    """
    try:
        shutil.rmtree(directory)
        fd = os.open(os.path.dirname(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as err:
        if err.errno == 2:
            pass
        else:
            raise


def parse_config(config_file):
    """
    Function to parse the configuration file.  If the passed in config_file is
    None, then the default configuration file is used.
    """
    try:
        config = configparser.SafeConfigParser()
    except AttributeError:
        # SafeConfigParser was deprecated in Python 3.2
        config = configparser.ConfigParser()
    if config_file is not None:
        # If the config_file passed in is not None, then we want to try to read
        # that config file (after expanding it).  If that config file doesn't
        # exist, we want to throw an error (which is why we use readfp here).
        try:
            config.readfp(open(os.path.expanduser(config_file)))
        except AttributeError:
            # readfp was renamed to read_file in Python 3.2
            config.read_file(open(os.path.expanduser(config_file)))
    else:
        # The config file was not passed in, so we want to use one of the
        # defaults.  First we check to see if a ~/.oz/oz.cfg exists; if it does,
        # we use that.  Otherwise we fall back to the system-wide version in
        # /etc/oz/oz.cfg.  If neither of those exist, we don't throw an error
        # but instead let Oz pick sane defaults internally.
        parsed = config.read(os.path.expanduser("~/.oz/oz.cfg"))
        if not parsed and os.geteuid() == 0:
            config.read("/etc/oz/oz.cfg")

    return config


def default_output_dir():
    """
    Function to get the default path to the output directory.
    """
    if os.geteuid() == 0:
        return "/var/lib/libvirt/images"
    return "~/.oz/images"


def default_data_dir():
    """
    Function to get the default path to the data directory.
    """
    if os.geteuid() == 0:
        return "/var/lib/oz"
    return "~/.oz"


def default_sshprivkey():
    """
    Function to get the default path to the SSH private key.
    """
    if os.geteuid() == 0:
        return "/etc/oz/id_rsa-icicle-gen"
    return "~/.oz/id_rsa-icicle-gen"


def default_screenshot_dir():
    """
    Function to get the default path to the screenshot directory. The directory
    is generated relative to the default data directory.
    """
    return os.path.join(default_data_dir(), "screenshots")


class LocalFileAdapter(requests.adapters.BaseAdapter):
    '''
    This class implements an adapter for requests so we can properly deal with file://
    local files.
    '''
    @staticmethod
    def _chkpath(method, path):
        """Return an HTTP status for the given filesystem path."""
        if method.lower() in ('put', 'delete'):
            return 501, "Not Implemented"
        elif method.lower() not in ('get', 'head', 'post'):
            return 405, "Method Not Allowed"
        elif os.path.isdir(path):
            return 400, "Path Not A File"
        elif not os.path.isfile(path):
            return 404, "File Not Found"
        elif not os.access(path, os.R_OK):
            return 403, "Access Denied"
        return 200, "OK"

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        """Return the file specified by the given request

        @type req: C{PreparedRequest}
        @todo: Should I bother filling `response.headers` and processing
               If-Modified-Since and friends using `os.stat`?
        """
        if sys.version_info.major == 2:
            path = os.path.normcase(os.path.normpath(urllib.url2pathname(request.path_url)))  # pylint: disable=no-member
        else:
            path = os.path.normcase(os.path.normpath(urllib.request.url2pathname(request.path_url)))
        response = requests.Response()

        response.status_code, response.reason = self._chkpath(request.method, path)
        if response.status_code == 200 and request.method.lower() != 'head':
            try:
                response.raw = open(path, 'rb')
            except (OSError, IOError) as err:
                response.status_code = 500
                response.reason = str(err)

        if isinstance(request.url, bytes):
            response.url = request.url.decode('utf-8')
        else:
            response.url = request.url

        response.headers['Content-Length'] = os.path.getsize(path)
        response.headers['Accept-Ranges'] = 'bytes'
        response.headers['Redirect-URL'] = request.url
        response.request = request
        response.connection = self

        return response

    def close(self):
        pass


def http_get_header(url, redirect=True):
    """
    Function to get the HTTP headers from a URL.  The available headers will be
    returned in a dictionary.  If redirect=True (the default), then this
    function will automatically follow http redirects through to the final
    destination, entirely transparently to the caller.  If redirect=False, then
    this function will follow http redirects through to the final destination,
    and also store that information in the 'Redirect-URL' key.  Note that
    'Redirect-URL' will always be None in the redirect=True case, and may be
    None in the redirect=True case if no redirects were required.
    """
    with requests.Session() as requests_session:
        requests_session.mount('file://', LocalFileAdapter())
        response = requests_session.head(url, allow_redirects=redirect, stream=True, timeout=10)
        info = response.headers
        info['HTTP-Code'] = response.status_code
        if not redirect:
            info['Redirect-URL'] = response.headers.get('Location')
        else:
            info['Redirect-URL'] = None

    return info


def http_download_file(url, fd, show_progress, logger):
    """
    Function to download a file from url to file descriptor fd.
    """
    with requests.Session() as requests_session:
        requests_session.mount('file://', LocalFileAdapter())
        response = requests_session.get(url, stream=True, allow_redirects=True,
                                        headers={'Accept-Encoding': ''})
        file_size = int(response.headers.get('Content-Length'))
        chunk_size = 10 * 1024 * 1024
        done = 0
        for chunk in response.iter_content(chunk_size):
            write_bytes_to_fd(fd, chunk)
            done += len(chunk)
            if show_progress:
                logger.debug("%dkB of %dkB" % (done / 1024, file_size / 1024))


def ftp_download_directory(server, username, password, basepath, destination, port=None):
    """
    Function to recursively download an entire directory structure over FTP.
    """
    ftp = ftplib.FTP()
    ftp.connect(server, port)
    ftp.login(username, password)

    def _recursive_ftp_download(sourcepath):
        """
        Function to iterate and download a remote ftp folder
        """
        original_dir = ftp.pwd()
        try:
            ftp.cwd(sourcepath)
        except ftplib.error_perm:
            relativesourcepath = os.path.relpath(sourcepath, basepath)
            destinationpath = os.path.join(destination, relativesourcepath)
            if not os.path.exists(os.path.dirname(destinationpath)):
                os.makedirs(os.path.dirname(destinationpath))
            ftp.retrbinary("RETR " + sourcepath, open(destinationpath, "wb").write)
            return

        names = ftp.nlst()
        for name in names:
            _recursive_ftp_download(os.path.join(sourcepath, name))

        ftp.cwd(original_dir)

    _recursive_ftp_download(basepath)
    ftp.close()


def _gzip_file(inputfile, outputfile, outputmode):
    """
    Internal function to gzip the input file and place it in the outputfile.
    If the outputmode is 'ab', then the input file will be appended to the
    output file, and if the outputmode is 'wb' then the input file will be
    written over the output file.
    """
    with open(inputfile, 'rb') as f:
        gzf = gzip.GzipFile(outputfile, mode=outputmode)
        gzf.writelines(f)
        gzf.close()


def gzip_append(inputfile, outputfile):
    """
    Function to gzip and append the data from inputfile onto output file.
    """
    _gzip_file(inputfile, outputfile, 'ab')


def gzip_create(inputfile, outputfile):
    """
    Function to gzip the data from inputfile and place it into outputfile,
    overwriting any existing data in outputfile.
    """
    try:
        _gzip_file(inputfile, outputfile, 'wb')
    except:
        # since we created the output file, we should clean it up
        if os.access(outputfile, os.F_OK):
            os.unlink(outputfile)
        raise


def check_qcow_size(filename):
    """
    Function to detect if an image is in qcow format.  If it is, return the size
    of the underlying disk image.  If it isn't, return None.
    """

    # For interested parties, this is the QCOW header struct in C
    # struct qcow_header {
    #    uint32_t magic;
    #    uint32_t version;
    #    uint64_t backing_file_offset;
    #    uint32_t backing_file_size;
    #    uint32_t cluster_bits;
    #    uint64_t size; /* in bytes */
    #    uint32_t crypt_method;
    #    uint32_t l1_size;
    #    uint64_t l1_table_offset;
    #    uint64_t refcount_table_offset;
    #    uint32_t refcount_table_clusters;
    #    uint32_t nb_snapshots;
    #    uint64_t snapshots_offset;
    # };

    # And in Python struct format string-ese
    qcow_struct = ">IIQIIQIIQQIIQ"  # > means big-endian
    qcow_magic = 0x514649FB  # 'Q' 'F' 'I' 0xFB

    f = open(filename, "rb")
    pack = f.read(struct.calcsize(qcow_struct))
    f.close()

    unpack = struct.unpack(qcow_struct, pack)

    if unpack[0] == qcow_magic:
        return unpack[5]
    return None


def recursively_add_write_bit(inputdir):
    """
    Function to walk a directory tree, adding the write it to every file
    and directory.  This is mostly useful right before deleting a tree of
    files extracted from an ISO, since those were all read-only to begin
    with.
    """
    for dirpath, dirnames_unused, filenames in os.walk(inputdir):
        # If the path is a symlink, and it is an absolute symlink, this would
        # attempt to change the permissions of the *host* file, not the
        # file that is relative to here.  That is no good, and could be a
        # security problem if Oz is being run as root.  We skip all paths that
        # are symlinks; what they point to will be changed later on.
        if os.path.islink(dirpath):
            continue

        os.chmod(dirpath, os.stat(dirpath).st_mode | stat.S_IWUSR)
        for name in filenames:
            fullpath = os.path.join(dirpath, name)

            # we have the same guard for symlinks as above, for the same reason
            if os.path.islink(fullpath):
                continue

            try:
                # if there are broken symlinks in the ISO,
                # then the below might fail.  This probably
                # isn't fatal, so just allow it and go on
                os.chmod(fullpath, os.stat(fullpath).st_mode | stat.S_IWUSR)
            except OSError as err:
                if err.errno != errno.ENOENT:
                    raise


def find_uefi_firmware(arch):
    '''
    A function to find the UEFI firmware file that corresponds to a certain
    architecture.
    '''
    # Yuck.  Finding the UEFI firmware to start certain guests (like aarch64)
    # is a really nasty process.  While slightly out of date, this blog post
    # describes the mess: http://blog.wikichoon.com/2016/01/uefi-support-in-virt-install-and-virt.html
    # Here, we replicate what libguestfs is doing here, which is to essentially
    # hardcode paths where UEFI firmware can be found on popular distributions.
    # I verified that these files exist on both Fedora/RHEL and Ubuntu.
    # Hopefully there will be a nicer way to do this in the future.
    class UEFI(object):
        '''
        A private class to hold the path to the loader and the path to the
        NVRAM file.
        '''
        def __init__(self, loader, nvram):
            self.loader = loader
            self.nvram = nvram

        def exists(self):
            '''
            A method that returns True if both the loader and the NVRAM files
            exist, False otherwise.
            '''
            if os.path.exists(self.loader) and os.path.exists(self.nvram):
                return True
            return False

    if arch in ['i386', 'i486', 'i586', 'i686']:
        uefi_list = [UEFI('/usr/share/edk2.git/ovmf-ia32/OVMF_CODE-pure-efi.fd',
                          '/usr/share/edk2.git/ovmf-ia32/OVMF_VARS-pure-efi.fd')]
    elif arch in ['x86_64']:
        uefi_list = [UEFI('/usr/share/OVMF/OVMF_CODE.fd',
                          '/usr/share/OVMF/OVMF_VARS.fd'),
                     UEFI('/usr/share/edk2/ovmf/OVMF_CODE.fd',
                          '/usr/share/edk2/ovmf/OVMF_VARS.fd'),
                     UEFI('/usr/share/edk2.git/ovmf-x64/OVMF_CODE-pure-efi.fd',
                          '/usr/share/edk2.git/ovmf-x64/OVMF_VARS-pure-efi.fd')]
    elif arch in ['aarch64']:
        uefi_list = [UEFI('/usr/share/AAVMF/AAVMF_CODE.fd',
                          '/usr/share/AAVMF/AAVMF_VARS.fd'),
                     UEFI('/usr/share/edk2/aarch64/QEMU_EFI-pflash.raw',
                          '/usr/share/edk2/aarch64/vars-template-pflash.raw'),
                     UEFI('/usr/share/edk2.git/aarch64/QEMU_EFI-pflash.raw',
                          '/usr/share/edk2.git/aarch64/vars-template-pflash.raw')]
    elif arch in ['armv7l']:
        uefi_list = [UEFI('/usr/share/edk2/arm/QEMU_EFI-pflash.raw',
                          '/usr/share/edk2/arm/vars-template-pflash.raw')]
    else:
        raise Exception("Invalid arch for UEFI firmware")

    for uefi in uefi_list:
        if uefi.exists():
            return uefi.loader, uefi.nvram

    raise Exception("UEFI firmware is not installed!")


def open_locked_file(filename):
    """
    A function to open and lock a file.  Returns a file descriptor referencing
    the open and locked file.
    """
    outdir = os.path.dirname(filename)
    mkdir_p(outdir)

    fd = os.open(filename, os.O_RDWR | os.O_CREAT)

    try:
        fcntl.lockf(fd, fcntl.LOCK_EX)
    except:
        os.close(fd)
        raise

    return (fd, outdir)


def lxml_subelement(root, name, text=None, attributes=None):
    """
    Function to add a new element to an LXML tree, optionally include text
    and a dictionary of attributes.
    """
    tmp = lxml.etree.SubElement(root, name)
    if text is not None:
        tmp.text = text
    if attributes is not None:
        for k, v in attributes.items():
            tmp.set(k, v)
    return tmp


def timed_loop(max_time, cb, msg, cb_arg=None):
    '''
    A function to deal with waiting for an event to occur.  Given a
    maximum time to wait, a callback, and a message, it will wait until the maximum
    time for the event to occur.  Each time through the loop, it will do the following:

    1.  Check to see if it has been at least 10 seconds since it last logged.  If so, it
        will log right now.
    2.  Call the callback to check for the event.  If the callback returns True, the
        loop quits immediately.  If it returns False, go on to step 3.
    3.  Sleep for the portion of 1 second that was not taken up by the callback.

    If the event occurred (the callback returned True), then this function returns
    True.  If we timed out while waiting for the event to occur, this function returns
    False.
    '''
    log = logging.getLogger('%s' % (__name__))
    now = monotonic.monotonic()
    end = now + max_time
    next_print = now
    while now < end:
        now = monotonic.monotonic()
        if now >= next_print:
            left = int(end) - int(now)
            if left < 0:
                left = 0
            log.debug("%s, %d/%d", msg, left, max_time)
            next_print = now + 10

            if cb(cb_arg):
                return True

        # It's possible that the callback took longer than one second.
        # In that case, just skip our sleep altogether in an attempt to
        # catch up.
        sleep_time = 1.0 - (monotonic.monotonic() - now)
        if sleep_time > 0:
            # Otherwise, sleep for a time.  Note that we try to maintain
            # on our starting boundary, so we'll sleep less than a second
            # here almost always.
            time.sleep(sleep_time)

    return False


def get_free_port():
    """
    A function to find a free TCP port on the host.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Bind to port 0 which will use a free socket to listen to.
    sock.bind(("", 0))
    listen_port = sock.getsockname()[1]
    # Close the socket to free it up for libvirt
    sock.close()

    return listen_port


def sizeof_fmt(num, suffix="B"):
    """
    Give a convenient human-readable representation of a large size in
    bytes. Initially by Fred Cirera:
    https://web.archive.org/web/20111010015624/http://blogmag.net/blog/read/38/Print_human_readable_file_size
    edited by multiple contributors at:
    https://stackoverflow.com/questions/1094841
    Per Richard Fontana this is too trivial to be copyrightable, so
    there are no licensing concerns
    """
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Yi', suffix)
