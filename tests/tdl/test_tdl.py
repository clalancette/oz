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
    "test-43-persistent-repos.tdl": True,
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
    "test-58-disk-size-terabyte.tdl": True,
    "test-59-command-sorting.tdl": True,
}

def get_tdl(filename):
    # locate full path for tdl file
    tdl_prefix = ''
    for tdl_prefix in ['tests/tdl/', 'tdl/', '']:
        if os.path.isfile(tdl_prefix + filename):
            break
    if not os.path.isfile(tdl_prefix + filename):
        raise Exception('Unable to locate TDL: %s' % filename)
    tdl_file = tdl_prefix + filename

    # Grab TDL object
    tdl = validate_ozlib(tdl_file)
    return tdl

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

def test_persistent(filename='test-43-persistent-repos.tdl'):
    tdl = get_tdl(filename)
    test_name = os.path.splitext(filename,)[0]

    def assert_persistent_value(persistent, value):
        assert persistent == value, \
            "expected %s, got %s" % (value, persistent)

    for repo in list(tdl.repositories.values()):
        if repo.name.endswith('true'):
            yield '%s_%s' % (test_name, repo.name), assert_persistent_value, repo.persistent, True
        else:
            yield '%s_%s' % (test_name, repo.name), assert_persistent_value, repo.persistent, False

def test_command_sorting():
    tdl = get_tdl('test-59-command-sorting.tdl')

    assert tdl.commands[0].read() == 'echo "hello" > /tmp/foo'
    assert tdl.commands[1].read() == 'echo "there" > /tmp/foobar'
    assert tdl.commands[2].read() == 'echo "there" > /tmp/bar'

def test_command_mixed_positions():
    """
    Done as its own test as the code should throw but schema passes
    """
    with py.test.raises(oz.OzException.OzException):
        tdl = get_tdl("test-60-command-mix-positions-and-not.tdl")

def test_command_duplicate_positions():
    """
    Done as its own test as the code should throw but schema passes
    """
    with py.test.raises(oz.OzException.OzException):
        tdl = get_tdl("test-61-command-duplicate-position.tdl")

def test_repository_localhost():
    with py.test.raises(oz.OzException.OzException):
        tdl = get_tdl("test-62-repository-localhost.tdl")

def test_merge_packages():
    packages = """\
<packages>
  <package name="git"/>
</packages>
"""

    tdl = get_tdl("test-16-signed-repository.tdl")
    tdl.merge_packages(packages)

    assert len(tdl.packages) == 2
    for package in tdl.packages:
        assert package.name in ['git', 'chris']

def test_merge_packages_duplicates():
    packages = """\
<packages>
  <package name="git"/>
  <package name='chris'>
    <repository>myrepo</repository>
    <file>myfilename</file>
    <arguments>args</arguments>
  </package>
  <package name="git"/>
</packages>
"""

    tdl = get_tdl("test-16-signed-repository.tdl")
    tdl.merge_packages(packages)

    assert len(tdl.packages) == 2
    for package in tdl.packages:
        assert package.name in ['git', 'chris']


def test_merge_repositories():
    repos = """\
<repositories>
  <repository name="anotherrepo">
    <url>http://another/world</url>
  </repository>
</repositories>
"""
    tdl = get_tdl("test-16-signed-repository.tdl")
    tdl.merge_repositories(repos)
    assert len(tdl.repositories) == 2
    for repo in list(tdl.repositories.values()):
        assert repo.name in ['anotherrepo', 'myrepo']
