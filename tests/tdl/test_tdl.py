#!/usr/bin/python

import sys
import os

try:
    import lxml.etree
except ImportError:
    print('Unable to import lxml.  Is python-lxml installed?')
    sys.exit(1)

try:
    import py.test
except ImportError:
    print('Unable to import py.test.  Is py.test installed?')
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
}

# Validate oz handling of tdl file
def validate_ozlib(tdl_file):
    xmldata = open(tdl_file, 'r').read()
    return oz.TDL.TDL(xmldata)

# Validate schema
def validate_schema(tdl_file):

    # Locate relaxng schema
    rng_file = None
    for tryme in ['../../oz/tdl.rng',
                  '../oz/tdl.rng',
                  'oz/tdl.rng',
                  'tdl.rng',]:
        if os.path.isfile(tryme):
            rng_file = tryme
            break

    if rng_file is None:
        raise Exception('RelaxNG schema file not found: tdl.rng')

    relaxng = lxml.etree.RelaxNG(file=rng_file)
    xml = open(tdl_file, 'r')
    doc = lxml.etree.parse(xml)
    xml.close()

    valid = relaxng.validate(doc)
    if not valid:
        errstr = "\n%s XML schema validation failed:\n" % (tdl_file)
        for error in relaxng.error_log:
            errstr += "\tline %s: %s\n" % (error.line, error.message)
        raise Exception(errstr)

# Test generator that iterates over all .tdl files
def test():

    # Define a helper to expect an exception
    def handle_exception(func, *args):
        with py.test.raises(Exception):
            func(*args)

    # Sanity check to see if any tests are unaccounted for in the config file
    for (tdl, expected_pass) in list(tests.items()):

        # locate full path for tdl file
        tdl_prefix = ''
        for tdl_prefix in ['tests/tdl/', 'tdl/', '']:
            if os.path.isfile(tdl_prefix + tdl):
                break
        tdl_file = tdl_prefix + tdl
        test_name = os.path.splitext(tdl,)[0]

        # Generate a unique unittest test for each validate_* method
        for tst in (validate_ozlib, validate_schema, ):
            # We need a unique method name
            unique_name = test_name + tst.__name__

            # Are we expecting the test to fail?
            if expected_pass:
                yield '%s_%s' % (test_name, tst.__name__), tst, tdl_file
            else:
                yield '%s_%s' % (test_name, tst.__name__), handle_exception,\
                    tst, tdl_file

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
