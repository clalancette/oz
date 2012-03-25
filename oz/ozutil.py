# Copyright (C) 2010,2011,2012  Chris Lalancette <clalance@redhat.com>

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

def generate_full_auto_path(relative):
    """
    Function to find the absolute path to an unattended installation file.
    """
    # all of the automated installation paths are installed to $pkg_path/auto,
    # so we just need to find it and generate the right path here
    if relative is None:
        raise Exception, "The relative path cannot be None"

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
        raise Exception, "Invalid program name passed"

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
    if src is None:
        raise Exception, "Source of copy cannot be None"
    if dest is None:
        raise Exception, "Destination of copy cannot be None"

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
        raise Exception, "Input string was None!"
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
    return ':'.join(map(lambda x:"%02x" % x, mac))

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
        raise Exception, "Path cannot be None"

    try:
        os.makedirs(path)
    except OSError, err:
        if err.errno != errno.EEXIST or not os.path.isdir(path):
            raise

def copy_modify_file(inname, outname, subfunc):
    """
    Function to copy a file from inname to outname, passing each line
    through subfunc first.  subfunc is expected to be a method that takes
    a single argument in (the next line), and returns a string to be
    written to the output file after modification (if any).
    """
    if inname is None:
        raise Exception, "input filename is None"
    if outname is None:
        raise Exception, "output filename is None"
    if subfunc is None:
        raise Exception, "subfunction is None"
    if not callable(subfunc):
        raise Exception, "subfunction is not callable"

    infile = open(inname, 'r')
    outfile = open(outname, 'w')

    for line in infile.xreadlines():
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
        raise Exception, "input dictionary was None"
    if outputfile is None:
        raise Exception, "output file was None"

    outf = open(outputfile, "w")

    try:
        for inputfile, destfile in inputdict.items():
            st = os.stat(inputfile)

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
            inf = open(inputfile, 'r')
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
        raise Exception, "Configuration parameter '%s' must be True, Yes, False, or No" % (key)

    return retval

def rmtree_and_sync(directory):
    shutil.rmtree(directory)
    # after we do the rmtree, there are usually a lot of metadata updates
    # pending.  This can cause the next steps (especially the steps where
    # libvirt is launching the guest) to fail, just because they timeout.  To
    # try to workaround this, fsync the directory, which will cause us to wait
    # until those updates have made it to disk.  Note that this cannot save us
    # if the system is extremely busy for other reasons, but at least the
    # problem won't be self-inflicted.
    fd = os.open(os.path.dirname(directory), os.O_RDONLY)
    os.fsync(fd)
    os.close(fd)
