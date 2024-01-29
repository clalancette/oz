#!/usr/bin/python

import sys
import os

try:
    import lxml.etree
except ImportError:
    print('Unable to import lxml.  Is python-lxml installed?')
    sys.exit(1)

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
    import oz
    import oz.TDL
except ImportError:
    print('Unable to import oz.  Is oz installed?')
    sys.exit(1)

# the tests dictionary lists all of the test we will run.  The key for the
# dictionary is the filename of the test, and the value is whether the test
# is expected to succeed (True) or not (False)
tests = {
    "test-01-simple-iso.tdl": True,
    "test-02-simple-url.tdl": True,
    "test-03-empty-template.tdl": False,
    "test-04-no-os.tdl": False,
    "test-05-no-name.tdl": False,
    "test-06-simple-iso-description.tdl": True,
    "test-07-packages-no-package.tdl": True,
    "test-08-repositories-no-repository.tdl": True,
    "test-09-os-invalid-arch.tdl": False,
    "test-10-os-invalid-install-type.tdl": False,
    "test-11-description-packages-repositories.tdl": True,
    "test-12-os-no-name.tdl": False,
    "test-13-os-no-version.tdl": False,
    "test-14-os-no-arch.tdl": False,
    "test-15-os-no-install.tdl": False,
    "test-16-signed-repository.tdl": True,
    "test-17-repo-invalid-signed.tdl": False,
    "test-18-rootpw.tdl": True,
    "test-19-key.tdl": True,
    "test-20-multiple-install.tdl": False,
    "test-21-missing-install-type.tdl": False,
    "test-22-md5sum.tdl": True,
    "test-23-sha1sum.tdl": True,
    "test-24-sha256sum.tdl": True,
    "test-25-md5sum-and-sha1sum.tdl": False,
    "test-26-md5sum-and-sha256sum.tdl": False,
    "test-27-sha1sum-and-sha256sum.tdl": False,
    "test-28-package-no-name.tdl": False,
    "test-29-files.tdl": True,
    "test-30-file-no-name.tdl": False,
    "test-31-file-raw-type.tdl": True,
    "test-32-file-base64-type.tdl": True,
    "test-33-file-invalid-type.tdl": False,
    "test-34-file-invalid-base64.tdl": False,
    "test-35-repository-no-name.tdl": False,
    "test-36-repository-no-url.tdl": False,
    "test-37-command.tdl": True,
    "test-38-command-no-name.tdl": False,
    "test-39-command-raw-type.tdl": True,
    "test-40-command-base64-type.tdl": True,
    "test-41-command-bogus-base64.tdl": False,
    "test-42-command-bogus-type.tdl": False,
    "test-43-persisted-repos.tdl": True,
    "test-44-version.tdl": True,
    "test-45-bogus-version.tdl": False,
    "test-46-duplicate-name.tdl": False,
    "test-47-invalid-template.tdl": False,
    "test-48-file-empty-base64.tdl": True,
    "test-49-file-empty-raw.tdl": True,
    "test-50-command-base64-empty.tdl": False,
    "test-51-disk-size.tdl": True,
    "test-52-command-file-url.tdl": True,
    "test-53-command-http-url.tdl": True,
    "test-54-files-file-url.tdl": True,
    "test-55-files-http-url.tdl": True,
    "test-56-invalid-disk-size.tdl": False,
    "test-57-invalid-disk-size.tdl": False,
    "test-58-disk-size-tebibyte-compat.tdl": True,
    "test-59-command-sorting.tdl": True,
    "test-63-disk-size-exbibyte.tdl": True,
    "test-64-disk-size-zettabyte.tdl": True,
    "test-65-disk-size-byte.tdl": True,
}

# Test that iterates over all .tdl files
def test_all():
    for (tdl, expected_pass) in list(tests.items()):

        # locate full path for tdl file
        tdl_prefix = ''
        for tdl_prefix in ['tests/tdl/', 'tdl/', '']:
            if os.path.isfile(tdl_prefix + tdl):
                break
        tdl_file = tdl_prefix + tdl
        test_name = os.path.splitext(tdl,)[0]

        # Test if the TDL class will parse it.
        print("Testing %s" % (tdl_file))
        with open(tdl_file, 'r') as infp:
            try:
                oz.TDL.TDL(infp.read())
                if not expected_pass:
                    assert(False)
            except Exception:
                if expected_pass:
                    raise

'''
def test_persisted(tdl='test-43-persisted-repos.tdl'):
    # locate full path for tdl file
    tdl_prefix = ''
    for tdl_prefix in ['tests/tdl/', 'tdl/', '']:
        if os.path.isfile(tdl_prefix + tdl):
            break
    if not os.path.isfile(tdl_prefix + tdl):
        raise Exception('Unable to locate TDL: %s' % tdl)
    tdl_file = tdl_prefix + tdl
    test_name = os.path.splitext(tdl,)[0]

    # Grab TDL object
    tdl = validate_ozlib(tdl_file)

    def assert_persisted_value(persisted, value):
        assert persisted == value, \
            "expected %s, got %s" % (value, persisted)

    for repo in list(tdl.repositories.values()):
        if repo.name.endswith('true'):
            yield '%s_%s' % (test_name, repo.name), assert_persisted_value, repo.persisted, True
        else:
            yield '%s_%s' % (test_name, repo.name), assert_persisted_value, repo.persisted, False
'''
