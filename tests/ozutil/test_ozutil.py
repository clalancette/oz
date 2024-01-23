#!/usr/bin/python

import sys
import os

try:
    import pytest
except ImportError:
    print('Unable to import pytest.  Is pytest installed?')
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
    print('Unable to import oz.  Is oz installed?')
    sys.exit(1)

# test oz.ozutil.generate_full_auto_path
def test_auto():
    assert(oz.ozutil.generate_full_auto_path('fedora-14-jeos.ks') == os.path.realpath(os.path.join(prefix, 'oz', 'auto', 'fedora-14-jeos.ks')))

def test_auto_none():
    with pytest.raises(Exception):
        oz.ozutil.generate_full_auto_path(None)

# test oz.ozutil.executable_exists
def test_exe_exists_bin_ls():
    assert(oz.ozutil.executable_exists('/bin/ls'))

def test_exe_exists_foo():
    with pytest.raises(Exception):
        oz.ozutil.executable_exists('foo')

def test_exe_exists_full_foo():
    with pytest.raises(Exception):
        oz.ozutil.executable_exists('/bin/foo')

def test_exe_exists_not_x():
    with pytest.raises(Exception):
        oz.ozutil.executable_exists('/etc/hosts')

def test_exe_exists_relative_false():
    assert(oz.ozutil.executable_exists('false'))

def test_exe_exists_none():
    with pytest.raises(Exception):
        oz.ozutil.executable_exists(None)

# test oz.ozutil.copyfile_sparse
def test_copy_sparse_none_src():
    with pytest.raises(Exception):
        oz.ozutil.copyfile_sparse(None, None)

def test_copy_sparse_none_dst(tmpdir):
    fullname = os.path.join(str(tmpdir), 'src')
    open(fullname, 'w').write('src')
    with pytest.raises(Exception):
        oz.ozutil.copyfile_sparse(fullname, None)

def test_copy_sparse_bad_src_mode(tmpdir):
    if os.geteuid() == 0:
        # this test won't work as root, since root can copy any mode files
        return
    fullname = os.path.join(str(tmpdir), 'writeonly')
    open(fullname, 'w').write('writeonly')
    os.chmod(fullname, 0000)
    # because copyfile_sparse uses os.open() instead of open(), it throws an
    # OSError
    with pytest.raises(OSError):
        oz.ozutil.copyfile_sparse(fullname, 'output')

def test_copy_sparse_bad_dst_mode(tmpdir):
    if os.geteuid() == 0:
        # this test won't work as root, since root can copy any mode files
        return
    srcname = os.path.join(str(tmpdir), 'src')
    open(srcname, 'w').write('src')
    dstname = os.path.join(str(tmpdir), 'dst')
    open(dstname, 'w').write('dst')
    os.chmod(dstname, 0o444)
    with pytest.raises(OSError):
        oz.ozutil.copyfile_sparse(srcname, dstname)

def test_copy_sparse_zero_size_src(tmpdir):
    srcname = os.path.join(str(tmpdir), 'src')
    fd = open(srcname, 'w')
    fd.close()
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)
    assert(os.stat(dstname).st_size == 0)

def test_copy_sparse_small_src(tmpdir):
    srcname = os.path.join(str(tmpdir), 'src')
    open(srcname, 'w').write('src')
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)
    assert(os.stat(dstname).st_size == 3)

def test_copy_sparse_one_block_src(tmpdir):
    with open('/dev/urandom', 'rb') as infd:
        # we read 32*1024 to make sure we use one big buf_size block (see the
        # implementation of copyfile_sparse)
        data = infd.read(32*1024)

    srcname = os.path.join(str(tmpdir), 'src')
    with open(srcname, 'wb') as outfd:
        outfd.write(data)
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)
    assert(os.stat(dstname).st_size == 32*1024)

def test_copy_sparse_many_blocks_src(tmpdir):
    with open('/dev/urandom', 'rb') as infd:
        # we read 32*1024 to make sure we use one big buf_size block (see the
        # implementation of copyfile_sparse)
        data = infd.read(32*1024*10)

    srcname = os.path.join(str(tmpdir), 'src')
    with open(srcname, 'wb') as outfd:
        outfd.write(data)
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)
    assert(os.stat(dstname).st_size == 32*1024*10)

def test_copy_sparse_zero_blocks(tmpdir):
    with open('/dev/urandom', 'rb') as infd:
        # we read 32*1024 to make sure we use one big buf_size block (see the
        # implementation of copyfile_sparse)
        data1 = infd.read(32*1024)
        data2 = infd.read(32*1024)

    srcname = os.path.join(str(tmpdir), 'src')
    with open(srcname, 'wb') as outfd:
        outfd.write(data1)
        outfd.write(b'\0'*32*1024)
        outfd.write(data2)
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)
    assert(os.stat(dstname).st_size == 32*1024*3)

def test_copy_sparse_src_not_exists(tmpdir):
    srcname = os.path.join(str(tmpdir), 'src')
    dstname = os.path.join(str(tmpdir), 'dst')
    open(dstname, 'w').write('dst')
    with pytest.raises(Exception):
        oz.ozutil.copyfile_sparse(srcname, dstname)

def test_copy_sparse_dest_not_exists(tmpdir):
    srcname = os.path.join(str(tmpdir), 'src')
    open(srcname, 'w').write('src')
    dstname = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copyfile_sparse(srcname, dstname)
    assert(os.stat(dstname).st_size == 3)

def test_copy_sparse_src_is_dir(tmpdir):
    dstname = os.path.join(str(tmpdir), 'dst')
    open(dstname, 'w').write('dst')
    with pytest.raises(Exception):
        oz.ozutil.copyfile_sparse(tmpdir, dstname)

def test_copy_sparse_dst_is_dir(tmpdir):
    srcname = os.path.join(str(tmpdir), 'src')
    open(srcname, 'w').write('src')
    with pytest.raises(Exception):
        oz.ozutil.copyfile_sparse(srcname, tmpdir)

# test oz.ozutil.string_to_bool
def test_stb_no():
    for nletter in ['n', 'N']:
        for oletter in ['o', 'O']:
            curr = nletter+oletter
            assert(oz.ozutil.string_to_bool(curr) == False)

def test_stb_false():
    for fletter in ['f', 'F']:
        for aletter in ['a', 'A']:
            for lletter in ['l', 'L']:
                for sletter in ['s', 'S']:
                    for eletter in ['e', 'E']:
                        curr = fletter+aletter+lletter+sletter+eletter
                        assert(oz.ozutil.string_to_bool(curr) == False)

def test_stb_yes():
    for yletter in ['y', 'Y']:
        for eletter in ['e', 'E']:
            for sletter in ['s', 'S']:
                curr = yletter+eletter+sletter
                assert(oz.ozutil.string_to_bool(curr) == True)

def test_stb_true():
    for tletter in ['t', 'T']:
        for rletter in ['r', 'R']:
            for uletter in ['u', 'U']:
                for eletter in ['e', 'E']:
                    curr = tletter+rletter+uletter+eletter
                    assert(oz.ozutil.string_to_bool(curr) == True)

def test_stb_none():
    with pytest.raises(Exception):
        oz.ozutil.string_to_bool(None)


def test_stb_invalid():
    assert(oz.ozutil.string_to_bool('foobar') is None)

# test oz.ozutil.generate_macaddress
def test_genmac():
    mac = oz.ozutil.generate_macaddress()
    assert(type(mac) == str)
    assert(len(mac) == 17)

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
    with pytest.raises(OSError):
        oz.ozutil.mkdir_p(fullname)

def test_mkdir_p_none():
    with pytest.raises(Exception):
        oz.ozutil.mkdir_p(None)

def test_mkdir_p_empty_string():
    oz.ozutil.mkdir_p('')

# test oz.ozutil.copy_modify_file
def test_copy_modify_none_src():
    with pytest.raises(Exception):
        oz.ozutil.copy_modify_file(None, None, None)

def test_copy_modify_none_dst(tmpdir):
    fullname = os.path.join(str(tmpdir), 'src')
    open(fullname, 'w').write('src')
    with pytest.raises(Exception):
        oz.ozutil.copy_modify_file(fullname, None, None)

def test_copy_modify_none_subfunc(tmpdir):
    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('src')
    dst = os.path.join(str(tmpdir), 'dst')
    with pytest.raises(Exception):
        oz.ozutil.copy_modify_file(src, dst, None)

def test_copy_modify_bad_src_mode(tmpdir):
    if os.geteuid() == 0:
        # this test won't work as root, since root can copy any mode files
        return
    def sub(line):
        return line
    fullname = os.path.join(str(tmpdir), 'writeonly')
    open(fullname, 'w').write('writeonly')
    os.chmod(fullname, 0000)
    dst = os.path.join(str(tmpdir), 'dst')
    with pytest.raises(IOError):
        oz.ozutil.copy_modify_file(fullname, dst, sub)

def test_copy_modify_empty_file(tmpdir):
    def sub(line):
        return line
    src = os.path.join(str(tmpdir), 'src')
    f = open(src, 'w')
    f.close()
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copy_modify_file(src, dst, sub)
    assert(os.stat(dst).st_size == 0)

def test_copy_modify_file(tmpdir):
    def sub(line):
        return line
    src = os.path.join(str(tmpdir), 'src')
    with open(src, 'w') as f:
        f.write("this is a line in the file\n")
        f.write("this is another line in the file\n")
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.copy_modify_file(src, dst, sub)
    assert(os.stat(dst).st_size == 60)

# test oz.ozutil.write_cpio
def test_write_cpio_none_input():
    with pytest.raises(Exception):
        oz.ozutil.write_cpio(None, None)

def test_write_cpio_none_output():
    with pytest.raises(Exception):
        oz.ozutil.write_cpio({}, None)

def test_write_cpio_empty_dict(tmpdir):
    dst = os.path.join(str(tmpdir), 'dst')
    oz.ozutil.write_cpio({}, dst)

def test_write_cpio_existing_file(tmpdir):
    if os.geteuid() == 0:
        # this test won't work as root, since root can copy any mode files
        return
    dst = os.path.join(str(tmpdir), 'dst')
    open(dst, 'w').write('hello')
    os.chmod(dst, 0000)
    with pytest.raises(IOError):
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
    if os.geteuid() == 0:
        # this test won't work as root, since root can copy any mode files
        return
    src = os.path.join(str(tmpdir), 'src')
    open(src, 'w').write('src')
    os.chmod(src, 0000)
    dst = os.path.join(str(tmpdir), 'dst')
    with pytest.raises(IOError):
        oz.ozutil.write_cpio({src: 'src'}, dst)

def test_md5sum_regular(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('# this is a comment line, followed by a blank line\n\n6e812e782e52b536c0307bb26b3c244e *Fedora-11-i386-DVD.iso\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_sha1sum_regular(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('6e812e782e52b536c0307bb26b3c244e1c42b644 *Fedora-11-i386-DVD.iso\n')

    oz.ozutil.get_sha1sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_sha256sum_regular(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('6e812e782e52b536c0307bb26b3c244e1c42b644235f5a4b242786b1ef375358 *Fedora-11-i386-DVD.iso\n')

    oz.ozutil.get_sha256sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_bsd(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('MD5 (Fedora-11-i386-DVD.iso)=6e812e782e52b536c0307bb26b3c244e1c42b644235f5a4b242786b1ef375358\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_bsd_no_start_paren(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        # if BSD is missing a paren, we don't raise an exception, just ignore and
        # continue
        f.write('MD5 Fedora-11-i386-DVD.iso)=6e812e782e52b536c0307bb26b3c244e1c42b644235f5a4b242786b1ef375358\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_bsd_no_end_paren(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        # if BSD is missing a paren, we don't raise an exception, just ignore and
        # continue
        f.write('MD5 (Fedora-11-i386-DVD.iso=6e812e782e52b536c0307bb26b3c244e1c42b644235f5a4b242786b1ef375358\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_bsd_no_equal(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        # if BSD is missing a paren, we don't raise an exception, just ignore and
        # continue
        f.write('MD5 (Fedora-11-i386-DVD.iso) 6e812e782e52b536c0307bb26b3c244e1c42b644235f5a4b242786b1ef375358\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_regular_escaped(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('\\6e812e782e52b536c0307bb26b3c244e *Fedora-11-i386-DVD.iso\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_regular_too_short(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('6e *F\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_regular_no_star(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('6e812e782e52b536c0307bb26b3c244e Fedora-11-i386-DVD.iso\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_regular_no_newline(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('6e812e782e52b536c0307bb26b3c244e *Fedora-11-i386-DVD.iso')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')

def test_md5sum_regular_no_space(tmpdir):
    src = os.path.join(str(tmpdir), 'md5sum')
    with open(src, 'w') as f:
        f.write('6e812e782e52b536c0307bb26b3c244e_*Fedora-11-i386-DVD.iso\n')

    oz.ozutil.get_md5sum_from_file(src, 'Fedora-11-i386-DVD.iso')
