# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>
# Copyright (C) 2012,2013  Chris Lalancette <clalancette@gmail.com>

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
import random
import subprocess
import tempfile
import errno
import stat
import shutil
import pycurl
import gzip
try:
    import configparser
except ImportError:
    import ConfigParser as configparser
import collections
import ftplib
import struct

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

    fpath, fname = os.path.split(program)
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
        dest_fd = os.open(dest, os.O_WRONLY|os.O_CREAT|os.O_TRUNC)

        try:
            sb = os.fstat(src_fd)

            # See io_blksize() in coreutils for an explanation of why 32*1024
            buf_size = max(32*1024, sb.st_blksize)

            size = sb.st_size
            destlen = 0
            while size != 0:
                buf = read_bytes_from_fd(src_fd, min(buf_size, size))
                if len(buf) == 0:
                    break

                buflen = len(buf)
                if buf == '\0'*buflen:
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
    Function to get a checksum digest out of a checksum file given a
    filename.
    """
    retval = None

    f = open(sumfile, 'r')
    for line in f:
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

    executable_exists(popenargs[0][0])

    # NOTE: it is very, very important that we use temporary files for
    # collecting stdout and stderr here.  There is a nasty bug in python
    # subprocess; if your process produces more than 64k of data on an fd that
    # is using subprocess.PIPE, the whole thing will hang. To avoid this, we
    # use temporary fds to capture the data
    stdouttmp = tempfile.TemporaryFile()
    stderrtmp = tempfile.TemporaryFile()

    process = subprocess.Popen(stdout=stdouttmp, stderr=stderrtmp, *popenargs,
                               **kwargs)
    process.communicate()
    retcode = process.poll()

    stdouttmp.seek(0, 0)
    stdout = stdouttmp.read()
    stdouttmp.close()

    stderrtmp.seek(0, 0)
    stderr = stderrtmp.read()
    stderrtmp.close()

    if retcode:
        cmd = ' '.join(*popenargs)
        raise SubprocessException("'%s' failed(%d): %s" % (cmd, retcode, stderr), retcode)
    return (stdout, stderr, retcode)

def ssh_execute_command(guestaddr, sshprivkey, command, timeout=10,
                        tunnels=None):
    """
    Function to execute a command on the guest using SSH and return the
    output.
    """
    # ServerAliveInterval protects against NAT firewall timeouts
    # on long-running commands with no output
    #
    # PasswordAuthentication=no prevents us from falling back to
    # keyboard-interactive password prompting
    #
    # -F /dev/null makes sure that we don't use the global or per-user
    # configuration files

    cmd = ["ssh", "-i", sshprivkey,
           "-F", "/dev/null",
           "-o", "ServerAliveInterval=30",
           "-o", "StrictHostKeyChecking=no",
           "-o", "ConnectTimeout=" + str(timeout),
           "-o", "UserKnownHostsFile=/dev/null",
           "-o", "PasswordAuthentication=no"]

    if tunnels:
        for host in tunnels:
            for port in tunnels[host]:
                cmd.append("-R %s:%s:%s" % (tunnels[host][port], host, port))

    cmd.extend( ["root@" + guestaddr, command] )

    return subprocess_check_output(cmd)

def scp_copy_file(guestaddr, sshprivkey, file_to_upload, destination,
                  timeout=10):
    """
    Function to upload a file to the guest using scp.
    """
    ssh_execute_command(guestaddr, sshprivkey,
                        "mkdir -p " + os.path.dirname(destination), timeout)

    # ServerAliveInterval protects against NAT firewall timeouts
    # on long-running commands with no output
    #
    # PasswordAuthentication=no prevents us from falling back to
    # keyboard-interactive password prompting
    #
    # -F /dev/null makes sure that we don't use the global or per-user
    # configuration files
    return subprocess_check_output(["scp", "-i", sshprivkey,
                                    "-F", "/dev/null",
                                    "-o", "ServerAliveInterval=30",
                                    "-o", "StrictHostKeyChecking=no",
                                    "-o", "ConnectTimeout=" + str(timeout),
                                    "-o", "UserKnownHostsFile=/dev/null",
                                    "-o", "PasswordAuthentication=no",
                                    file_to_upload,
                                    "root@" + guestaddr + ":" + destination])

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
    except shutil.WindowsError:
        # can't copy file access times on Windows
        pass
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
    if not isinstance(subfunc, collections.Callable):
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
            outf.write("\x00"*(4 - ((110+len(stripped)) % 4)))

            # now write the data from the input file
            outf.writelines(inf)
            inf.close()

            # we now need to write out NUL byte(s) to make it a multiple of 4.
            # note that unlike the name, we do *not* have to have any NUL bytes,
            # so if it is already aligned on 4 bytes do nothing
            remainder = st[stat.ST_SIZE] % 4
            if remainder != 0:
                outf.write("\x00"*(4 - remainder))

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
        outf.write("\x00"*(512 - (outf.tell() % 512)))
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
    else:
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

def rmtree_and_sync(directory):
    """
    Function to remove a directory tree and do an fsync afterwards.  Because
    the removal of the directory tree can cause a lot of metadata updates, it
    can cause a lot of disk activity.  By doing the fsync, we ensure that any
    metadata updates caused by us will not cause subsequent steps to fail.  This
    cannot help if the system is otherwise very busy, but it does ensure that
    the problem is not self-inflicted.
    """
    shutil.rmtree(directory)
    fd = os.open(os.path.dirname(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def parse_config(config_file):
    """
    Function to parse the configuration file.  If the passed in config_file is
    None, then the default configuration file is used.
    """
    if config_file is None:
        if os.geteuid() == 0:
            config_file = "/etc/oz/oz.cfg"
        else:
            config_file = "~/.oz/oz.cfg"
    # if config_file was not None on input, then it was provided by the caller
    # and we use that instead

    config_file = os.path.expanduser(config_file)

    config = configparser.SafeConfigParser()
    if os.access(config_file, os.F_OK):
        config.read(config_file)

    return config

def default_output_dir():
    """
    Function to get the default path to the output directory.
    """
    if os.geteuid() == 0:
        directory = "/var/lib/libvirt/images"
    else:
        directory = "~/.oz/images"

    return os.path.expanduser(directory)

def default_data_dir():
    """
    Function to get the default path to the data directory.
    """
    if os.geteuid() == 0:
        directory = "/var/lib/oz"
    else:
        directory = "~/.oz"

    return os.path.expanduser(directory)

def default_sshprivkey():
    """
    Function to get the default path to the SSH private key.
    """
    if os.geteuid() == 0:
        directory = "/etc/oz/id_rsa-icicle-gen"
    else:
        directory = "~/.oz/id_rsa-icicle-gen"

    return os.path.expanduser(directory)

def default_screenshot_dir(data_dir):
    """
    Function to get the default path to the screenshot directory. The directory is
    generated relative to the given data directory.
    """
    return os.path.join(data_dir, "screenshots")

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
    info = {}
    def _header(buf):
        """
        Internal function that is called back from pycurl perform() for
        header data.
        """
        buf = buf.strip()
        if len(buf) == 0:
            return

        split = buf.split(':')
        if len(split) < 2:
            # not a valid header; skip
            return
        key = split[0].strip()
        value = split[1].strip()
        info[key] = value

    def _data(buf):
        """
        Empty function that is called back from pycurl perform() for body data.
        """
        pass

    c = pycurl.Curl()
    c.setopt(c.URL, url)
    c.setopt(c.NOBODY, True)
    c.setopt(c.HEADERFUNCTION, _header)
    c.setopt(c.HEADER, True)
    c.setopt(c.WRITEFUNCTION, _data)
    if redirect:
        c.setopt(c.FOLLOWLOCATION, True)
    c.perform()
    info['HTTP-Code'] = c.getinfo(c.HTTP_CODE)
    if info['HTTP-Code'] == 0:
        # if this was a file:/// URL, then the HTTP_CODE returned 0.
        # set it to 200 to be compatible with http
        info['HTTP-Code'] = 200
    if not redirect:
        info['Redirect-URL'] = c.getinfo(c.REDIRECT_URL)

    c.close()

    return info

def http_download_file(url, fd, show_progress, logger):
    """
    Function to download a file from url to file descriptor fd.
    """
    class Progress(object):
        """
        Internal class to represent progress on the connection.  This is only
        required so that we have somewhere to store the "last_mb" variable
        that is not global.
        """
        def __init__(self):
            self.last_mb = -1

        def progress(self, down_total, down_current, up_total, up_current):
            """
            Function that is called back from the pycurl perform() method to
            update the progress information.
            """
            if down_total == 0:
                return
            current_mb = int(down_current) / 10485760
            if current_mb > self.last_mb or down_current == down_total:
                self.last_mb = current_mb
                logger.debug("%dkB of %dkB" % (down_current/1024, down_total/1024))

    def _data(buf):
        """
        Function that is called back from the pycurl perform() method to
        actually write data to disk.
        """
        write_bytes_to_fd(fd, buf)

    progress = Progress()
    c = pycurl.Curl()
    c.setopt(c.URL, url)
    c.setopt(c.CONNECTTIMEOUT, 5)
    c.setopt(c.WRITEFUNCTION, _data)
    c.setopt(c.FOLLOWLOCATION, 1)
    if show_progress:
        c.setopt(c.NOPROGRESS, 0)
        c.setopt(c.PROGRESSFUNCTION, progress.progress)
    c.perform()
    c.close()

def ftp_download_directory(server, username, password, basepath, destination):
    """
    Function to recursively download an entire directory structure over FTP.
    """
    ftp = ftplib.FTP(server)
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
    f = open(inputfile, 'rb')
    gzf = gzip.GzipFile(outputfile, mode=outputmode)
    gzf.writelines(f)
    gzf.close()
    f.close()

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
    qcow_struct = ">IIQIIQIIQQIIQ" # > means big-endian
    qcow_magic = 0x514649FB # 'Q' 'F' 'I' 0xFB

    f = open(filename,"r")
    pack = f.read(struct.calcsize(qcow_struct))
    f.close()

    unpack = struct.unpack(qcow_struct, pack)

    if unpack[0] == qcow_magic:
        return unpack[5]
    else:
        return None
