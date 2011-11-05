#!/usr/bin/python

import sys
import os
import random

try:
    import libxml2
except ImportError:
    print 'Unable to import libxml2.  Is libxml2-python installed?'
    sys.exit(1)

try:
    import py.test
except ImportError:
    print 'Unable to import py.test.  Is py.test installed?'
    sys.exit(1)

# Find oz
prefix = '.'
for i in range(0,3):
    if os.path.isdir(os.path.join(prefix, 'oz')):
        sys.path.insert(0, prefix)
        break
    else:
        prefix = '../' + prefix

try:
    import oz.ozutil
except ImportError:
    print 'Unable to import oz.  Is oz installed?'
    sys.exit(1)

# test oz.ozutil.generate_full_auto_path
def test_auto():
    oz.ozutil.generate_full_auto_path('fedora-14-jeos.ks')

def test_auto_none():
    with py.test.raises(Exception):
        oz.ozutil.generate_full_auto_path(None)

# test oz.ozutil.executable_exists
def test_exe_exists_bin_true():
    oz.ozutil.executable_exists('/bin/true')

def test_exe_exists_foo():
    with py.test.raises(Exception):
        oz.ozutil.executable_exists('foo')

def test_exe_exists_full_foo():
    with py.test.raises(Exception):
        oz.ozutil.executable_exists('/bin/foo')

def test_exe_exists_not_x():
    with py.test.raises(Exception):
        oz.ozutil.executable_exists('/etc/hosts')

def test_exe_exists_relative_false():
    oz.ozutil.executable_exists('false')

def test_exe_exists_none():
    with py.test.raises(Exception):
        oz.ozutil.executable_exists(None)

# test oz.ozutil.copyfile_sparse
def test_copy_sparse_none_src():
    with py.test.raises(Exception):
        oz.ozutil.copyfile_sparse(None, None)

def test_copy_sparse_none_dst(tmpdir):
    fullname = os.path.join(str(tmpdir), 'src')
    open(fullname, 'w').write('src')
    with py.test.raises(Exception):
        oz.ozutil.copyfile_sparse(fullname, None)

def test_copy_sparse_bad_src_mode(tmpdir):
    fullname = os.path.join(str(tmpdir), 'writeonly')
    open(fullname, 'w').write('writeonly')
    os.chmod(fullname, 0000)
    # because copyfile_sparse uses os.open() instead of open(), it throws an
    # OSError
    with py.test.raises(OSError):
        oz.ozutil.copyfile_sparse(fullname, 'output')

def test_copy_sparse_bad_dst_mode(tmpdir):
    srcname = os.path.join(str(tmpdir), 'src')
    open(srcname, 'w').write('src')
    dstname = os.path.join(str(tmpdir), 'dst')
    open(dstname, 'w').write('dst')
    os.chmod(dstname, 0444)
    with py.test.raises(OSError):
        oz.ozutil.copyfile_sparse(srcname, dstname)

def test_copy_sparse_zero_size_src(tmpdir):
    srcname = os.path.join(str(tmpdir), 'src')
    fd = open(srcname, 'w')
    fd.close()
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)

def test_copy_sparse_small_src(tmpdir):
    srcname = os.path.join(str(tmpdir), 'src')
    open(srcname, 'w').write('src')
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)

def test_copy_sparse_one_block_src(tmpdir):
    infd = open('/dev/urandom', 'r')
    # we read 32*1024 to make sure we use one big buf_size block (see the
    # implementation of copyfile_sparse)
    data = infd.read(32*1024)
    infd.close

    srcname = os.path.join(str(tmpdir), 'src')
    outfd = open(srcname, 'w')
    outfd.write(data)
    outfd.close()
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)

def test_copy_sparse_many_blocks_src(tmpdir):
    infd = open('/dev/urandom', 'r')
    # we read 32*1024 to make sure we use one big buf_size block (see the
    # implementation of copyfile_sparse)
    data = infd.read(32*1024*10)
    infd.close

    srcname = os.path.join(str(tmpdir), 'src')
    outfd = open(srcname, 'w')
    outfd.write(data)
    outfd.close()
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)

def test_copy_sparse_zero_blocks(tmpdir):
    infd = open('/dev/urandom', 'r')
    # we read 32*1024 to make sure we use one big buf_size block (see the
    # implementation of copyfile_sparse)
    data1 = infd.read(32*1024)
    data2 = infd.read(32*1024)
    infd.close

    srcname = os.path.join(str(tmpdir), 'src')
    outfd = open(srcname, 'w')
    outfd.write(data1)
    outfd.write('\0'*32*1024)
    outfd.write(data2)
    outfd.close()
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)

# test oz.ozutil.string_to_bool
def test_stb_no():
    for nletter in ['n', 'N']:
        for oletter in ['o', 'O']:
            curr = nletter+oletter
            yield ('bool-'+curr, oz.ozutil.string_to_bool, curr)

def test_stb_false():
    for fletter in ['f', 'F']:
        for aletter in ['a', 'A']:
            for lletter in ['l', 'L']:
                for sletter in ['s', 'S']:
                    for eletter in ['e', 'E']:
                        curr = fletter+aletter+lletter+sletter+eletter
                        yield ('bool-'+curr, oz.ozutil.string_to_bool, curr)

def test_stb_yes():
    for yletter in ['y', 'Y']:
        for eletter in ['e', 'E']:
            for sletter in ['s', 'S']:
                curr = yletter+eletter+sletter
                yield ('bool-'+curr, oz.ozutil.string_to_bool, curr)

def test_stb_true():
    for tletter in ['t', 'T']:
        for rletter in ['r', 'R']:
            for uletter in ['u', 'U']:
                for eletter in ['e', 'E']:
                    curr = tletter+rletter+uletter+eletter
                    yield ('bool-'+curr, oz.ozutil.string_to_bool, curr)

def test_stb_none():
    with py.test.raises(Exception):
        oz.ozutil.string_to_bool(None)


def test_stb_invalid():
    if oz.ozutil.string_to_bool('foobar') != None:
        raise Exception, "Expected None return from string_to_bool"

# test oz.ozutil.generate_macaddress
def test_genmac():
    oz.ozutil.generate_macaddress()

# test oz.ozutil.mkdir_p
def test_mkdir_p(tmpdir):
    fullname = os.path.join(str(tmpdir), 'foo')
    oz.ozutil.mkdir_p(fullname)

def test_mkdir_p_twice(tmpdir):
    fullname = os.path.join(str(tmpdir), 'foo')
    oz.ozutil.mkdir_p(fullname)
    oz.ozutil.mkdir_p(fullname)

def test_mkdir_p_file_exists(tmpdir):
    fullname = os.path.join(str(tmpdir), 'file_exists')
    open(fullname, 'w').write('file_exists')
    with py.test.raises(OSError):
        oz.ozutil.mkdir_p(fullname)

def test_mkdir_p_none():
    with py.test.raises(Exception):
        oz.ozutil.mkdir_p(None)

# test oz.ozutil.copy_modify_file
def test_copy_modify_none_src():
    with py.test.raises(Exception):
        oz.ozutil.copy_modify_file(None, None, None)

def test_copy_modify_none_dst(tmpdir):
    fullname = os.path.join(str(tmpdir), 'src')
    open(fullname, 'w').write('src')
    with py.test.raises(Exception):
        oz.ozutil.copy_modify_file(fullname, None, None)

def test_copy_modify_none_subfunc(tmpdir):
    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('src')
    dst = os.path.join(str(tmpdir), 'dst')
    with py.test.raises(Exception):
        oz.ozutil.copy_modify_file(src, dst, None)

def test_copy_modify_bad_src_mode(tmpdir):
    def sub(line):
        return line
    fullname = os.path.join(str(tmpdir), 'writeonly')
    open(fullname, 'w').write('writeonly')
    os.chmod(fullname, 0000)
    dst = os.path.join(str(tmpdir), 'dst')
    with py.test.raises(IOError):
        oz.ozutil.copy_modify_file(fullname, dst, sub)

def test_copy_modify_empty_file(tmpdir):
    def sub(line):
        return line
    src = os.path.join(str(tmpdir), 'src')
    f = open(src, 'w')
    f.close()
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copy_modify_file(src, dst, sub)

def test_copy_modify_file(tmpdir):
    def sub(line):
        return line
    src = os.path.join(str(tmpdir), 'src')
    f = open(src, 'w')
    f.write("this is a line in the file\n")
    f.write("this is another line in the file\n")
    f.close()
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copy_modify_file(src, dst, sub)

# test oz.ozutil.write_cpio
def test_write_cpio_none_input():
    with py.test.raises(Exception):
        oz.ozutil.write_cpio(None, None)

def test_write_cpio_none_output():
    with py.test.raises(Exception):
        oz.ozutil.write_cpio({}, None)

def test_write_cpio_empty_dict(tmpdir):
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.write_cpio({}, dst)

def test_write_cpio_existing_file(tmpdir):
    dst = os.path.join(str(tmpdir), 'dst')
    open(dst, 'w').write('hello')
    os.chmod(dst, 0000)
    with py.test.raises(IOError):
        oz.ozutil.write_cpio({}, dst)

def test_write_cpio_single_file(tmpdir):
    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('src')
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.write_cpio({src: 'src'}, dst)

def test_write_cpio_multiple_files(tmpdir):
    src1 = os.path.join(str(tmpdir), 'src1')
    open(src1, 'w').write('src1')
    src2 = os.path.join(str(tmpdir), 'src2')
    open(src2, 'w').write('src2')
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.write_cpio({src1: 'src1', src2: 'src2'}, dst)

def test_write_cpio_not_multiple_of_4(tmpdir):
    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('src')
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.write_cpio({src: 'src'}, dst)

def test_write_cpio_exception(tmpdir):
    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('src')
    os.chmod(src, 0000)
    dst = os.path.join(str(tmpdir), 'dst')
    with py.test.raises(IOError):
        oz.ozutil.write_cpio({src: 'src'}, dst)
