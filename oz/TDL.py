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
Template Description Language (TDL)
"""

import base64
import os
import re
import sys
import tempfile
try:
    import urllib.parse as urlparse
except ImportError:
    import urlparse

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

import lxml.etree

import oz.OzException
import oz.ozutil


def _xml_get_value(doc, xmlstring, component, optional=False):
    """
    Function to get the contents from an XML node.  It takes 4 arguments:

    doc       - The lxml.etree document to get a value from.
    xmlstring - The XPath string to use.
    component - A string representing which TDL component is being
                looked for (used in error reporting).
    optional  - A boolean describing whether this XML node is allowed to be
                absent or not.  If optional is True and the node is absent,
                None is returned.  If optional is False and the node is
                absent, an exception is raised.  (default: False)

    Returns the content of the XML node if found, None if the node is not
    found and optional is True.
    """
    res = doc.xpath(xmlstring)
    if len(res) == 1:
        return res[0].text
    elif not res:
        if optional:
            return None
        else:
            raise oz.OzException.OzException("Failed to find %s in TDL" % (component))
    else:
        raise oz.OzException.OzException("Expected 0 or 1 %s in TDL, saw %d" % (component, len(res)))


def data_from_type(name, contenttype, content):
    '''
    A function to get data out of some content, possibly decoding it depending
    on the content type.  This function understands three types of content:
    raw (where no decoding is necessary), base64 (where the data needs to be
    base64 decoded), and url (where the data needs to be downloaded).  Because
    the data might be large, all data is sent to file handle, which is returned
    from the function.
    '''

    out = tempfile.NamedTemporaryFile()
    if contenttype == 'raw':
        out.write(content.encode('utf-8'))
    elif contenttype == 'base64':
        if sys.version_info.major == 2:
            out.write(base64.decodestring(content))
        else:
            out.write(base64.decodebytes(content.encode('utf-8')))
    elif contenttype == 'url':
        url = urlparse.urlparse(content)
        if url.scheme == "file":
            with open(url.netloc + url.path) as f:
                outstr = "".join(f.readlines())
                out.write(outstr.encode('utf-8'))
        else:
            oz.ozutil.http_download_file(content, out.fileno(), False, None)
    else:
        raise oz.OzException.OzException("Type for %s must be 'raw', 'url' or 'base64'" % (name))

    # make sure the data is flushed to disk for uses of the file through
    # the name
    out.flush()
    out.seek(0)

    return out


class Repository(object):
    """
    Class that represents a single repository to be used for installing
    packages.  Objects of this type contain 3 pieces of information:

    name       - The name of this repository.
    url        - The URL of this repository.
    signed     - Whether this repository is signed
    persisted  - Whether this repository should remain in the final image
    sslverify  - Whether SSL certificates should be verified
    """
    def __init__(self, name, url, signed, persisted, sslverify):
        self.name = name
        self.url = url
        self.signed = signed
        self.persisted = persisted
        self.sslverify = sslverify


class Package(object):
    """
    Class that represents a single package to be installed.
    Objects of this type contain 4 pieces of information:

    name     - The name of the package.
    repo     - The repository that this package comes from (optional).
    filename - The filename that contains this package (optional).
    args     - Arguments necessary to install this package (optional).
    """
    def __init__(self, name, repo, filename, args):
        self.name = name
        self.repo = repo
        self.filename = filename
        self.args = args


class ISOExtra(object):
    """
    Class that represents an extra element to add to an installation ISO.
    Objects of this type contain 3 pieces of information:

    element_type - "file" or "directory"
    source       - A source URL for the element.
    destination  - A relative destination for the element.
    """
    def __init__(self, element_type, source, destination):
        self.element_type = element_type
        self.source = source
        self.destination = destination


class TDL(object):
    """
    Class that represents a parsed piece of TDL XML.  Objects of this kind
    contain 10 pieces of information:

    name         - The name assigned to this TDL.
    distro       - The type of operating system this TDL represents.
    update       - The version of the operating system this TDL represents.
    arch         - The architecture of the operating system this TDL
                   represents. Currently this must be one of "i386" or
                   "x86_64".
    key          - The installation key necessary to install this operating
                   system (optional).
    description  - A free-form description of this TDL (optional).
    installtype  - The method to be used to install this operating system.
                   Currently this must be one of "url" or "iso".
    packages     - A list of Package objects describing the packages to be
                   installed on the operating system.  This list may be
                   empty.
    repositories - A dictionary of Repository objects describing the
                   repositories to be searched to find packages.  The
                   dictionary is indexed by repository name.  This
                   dictionary may be empty.
    files        - A dictionary of file contents to be added to the
                   operating system.  The dictionary is indexed by filename.
    commands     - A dictionary of commands to run inside the guest VM.  The
                   dictionary is indexed by commands.  This dictionary may
                   be empty.
    """
    def __init__(self, xmlstring, rootpw_required=False):
        # open the XML document
        tree = lxml.etree.parse(StringIO(xmlstring))
        tree.xinclude()
        self.doc = tree.getroot()

        # then validate the schema
        relaxng = lxml.etree.RelaxNG(file=os.path.join(os.path.dirname(__file__),
                                                       'tdl.rng'))
        valid = relaxng.validate(self.doc)
        if not valid:
            errstr = "\nXML schema validation failed:\n"
            for error in relaxng.error_log:
                errstr += "\tline %s: %s\n" % (error.line, error.message)
            raise oz.OzException.OzException(errstr)

        template = self.doc.xpath('/template')
        if len(template) != 1:
            raise oz.OzException.OzException("Expected 1 template section in TDL, saw %d" % (len(template)))
        self.version = template[0].get('version')

        if self.version:
            self._validate_tdl_version()

        self.name = _xml_get_value(self.doc, '/template/name', 'template name')

        self.distro = _xml_get_value(self.doc, '/template/os/name', 'OS name')

        self.update = _xml_get_value(self.doc, '/template/os/version',
                                     'OS version')

        self.arch = _xml_get_value(self.doc, '/template/os/arch',
                                   'OS architecture')
        if self.arch not in ["i386", "x86_64", "ppc64", "ppc64le", "aarch64", "armv7l", "s390x"]:
            raise oz.OzException.OzException("Architecture must be one of 'i386, x86_64, ppc64, ppc64le, armv7l, aarch64, or s390x'")

        self.key = _xml_get_value(self.doc, '/template/os/key', 'OS key',
                                  optional=True)
        # key is not required, so it is not fatal if it is None

        self.description = _xml_get_value(self.doc, '/template/description',
                                          'description', optional=True)
        # description is not required, so it is not fatal if it is None

        install = self.doc.xpath('/template/os/install')
        if len(install) != 1:
            raise oz.OzException.OzException("Expected 1 OS install section in TDL, saw %d" % (len(install)))
        self.installtype = install[0].get('type')
        if self.installtype is None:
            raise oz.OzException.OzException("Failed to find OS install type in TDL")

        # we only support md5/sha1/sha256 sums for ISO install types.  However,
        # we make sure the instance variables are set to None for both types
        # so code lower down in the stack doesn't have to care about the ISO
        # vs. URL install type distinction, and can just check whether or not
        # these URLs are None
        self.iso_md5_url = None
        self.iso_sha1_url = None
        self.iso_sha256_url = None

        if self.installtype == "url":
            self.url = _xml_get_value(self.doc, '/template/os/install/url',
                                      'OS install URL')
        elif self.installtype == "iso":
            self.iso = _xml_get_value(self.doc, '/template/os/install/iso',
                                      'OS install ISO')
            self.iso_md5_url = _xml_get_value(self.doc,
                                              '/template/os/install/md5sum',
                                              'OS install ISO MD5SUM',
                                              optional=True)
            self.iso_sha1_url = _xml_get_value(self.doc,
                                               '/template/os/install/sha1sum',
                                               'OS install ISO SHA1SUM',
                                               optional=True)
            self.iso_sha256_url = _xml_get_value(self.doc,
                                                 '/template/os/install/sha256sum',
                                                 'OS install ISO SHA256SUM',
                                                 optional=True)
            # only one of md5, sha1, or sha256 can be specified; raise an error
            # if multiple are
            if (self.iso_md5_url and self.iso_sha1_url) or (self.iso_md5_url and self.iso_sha256_url) or (self.iso_sha1_url and self.iso_sha256_url):
                raise oz.OzException.OzException("Only one of <md5sum>, <sha1sum>, and <sha256sum> can be specified")
        else:
            raise oz.OzException.OzException("Unknown install type " + self.installtype + " in TDL")

        self.rootpw = _xml_get_value(self.doc, '/template/os/rootpw',
                                     "root/Administrator password",
                                     optional=not rootpw_required)

        self.packages = []
        self._add_packages(self.doc.xpath('/template/packages/package'))

        self.files = {}
        for afile in self.doc.xpath('/template/files/file'):
            name = afile.get('name')
            if name is None:
                raise oz.OzException.OzException("File without a name was given")
            contenttype = afile.get('type')
            if contenttype is None:
                contenttype = 'raw'

            content = afile.text
            if content:
                content = content.strip()
            else:
                content = ''
            self.files[name] = data_from_type(name, contenttype, content)

        self.isoextras = self._add_isoextras('/template/os/install/extras/directory',
                                             'directory')
        self.isoextras += self._add_isoextras('/template/os/install/extras/file',
                                              'file')

        self.repositories = {}
        self._add_repositories(self.doc.xpath('/template/repositories/repository'))

        self.commands = self._parse_commands('/template/commands')
        self.precommands = self._parse_commands('/template/precommands')

        self.disksize = self._parse_disksize()

        self.icicle_extra_cmd = _xml_get_value(self.doc,
                                               '/template/os/icicle/extra_command',
                                               "extra icicle command",
                                               optional=True)

        self.kernel_param = _xml_get_value(self.doc,
                                           '/template/os/kernelparam',
                                           'custom kernel parameter',
                                           optional=True)

    def _parse_disksize(self):
        """
        Internal method to parse the disk size out of the TDL.
        """
        size = _xml_get_value(self.doc, '/template/disk/size', 'disk size',
                              optional=True)
        if size is None:
            # if it wasn't specified, return None; the Guest object will assign
            # a sensible default
            return None

        # drop spaces and downcase
        size = size.replace(" ", "").lower()
        # isolate digits
        number = ""
        suffix = ""
        for (idx, char) in enumerate(size):
            if char.isdigit():
                number += char
            else:
                suffix = size[idx:]
                break

        if not suffix:
            # for backwards compatibility, we assume GiB when there is no suffix
            suffix = "gib"

        # also for backwards compatibility with an earlier attempt to support
        # suffixes, treat "T" and "G" as "TiB" and "GiB"
        units = {"b": 1, "g": 2**30, "t": 2**40}
        tenscale = 3
        twoscale = 10
        for (i, pref) in enumerate(("k", "m", "g", "t", "p", "e", "z", "y"), start=1):
            # this is giving us {"gib": 2 ** 30, "gb": 10 ** 9}, etc
            units[pref + "b"] = (10 ** (i*tenscale))
            units[pref + "ib"] = (2 ** (i*twoscale))

        factor = units.get(suffix)
        if not number or not factor:
            raise oz.OzException.OzException(
                "Invalid disk size; it must be specified as an integer size with an optional SI or IEC unit suffix, e.g. '10TB' or '16GiB'"
            )

        return str(int(number) * factor)

    def _parse_commands(self, xpath):
        """
        Internal method to parse the commands XML and put it into order.  This
        order can either be via parse order (implicit) or by using the
        'position' attribute in the commands XML (explicit).  Note that the two
        cannot be mixed; if position is specified on one node, it must be
        specified on all of them.  Conversely, if position is *not* specified
        on one node, it must *not* be specified on any of them.  Also note that
        if explicit ordering is used, it must be strictly sequential, starting
        at 1, with no duplicate numbers.
        """
        tmp = []
        saw_position = False
        for command in self.doc.xpath(xpath + "/command"):
            name = command.get('name')
            if name is None:
                raise oz.OzException.OzException("Command without a name was given")
            contenttype = command.get('type')
            if contenttype is None:
                contenttype = 'raw'

            content = ""
            if command.text:
                content = command.text.strip()
            if not content:
                raise oz.OzException.OzException("Empty commands are not allowed")

            # since XML doesn't *guarantee* an order, the correct way to
            # specify a particular order of commands is to use the "position"
            # attribute.  For backwards compatibility, if the order is not
            # specified, we just use the parse order.  That being said, we do
            # not allow a mix of position attributes and implicit order.  If
            # you use the position attribute on one command, you must use it
            # on all commands, and vice-versa.

            position = command.get('position')
            if position is not None:
                saw_position = True
                position = int(position)

            fp = data_from_type(name, contenttype, content)
            tmp.append((position, fp))

        commands = []
        if not saw_position:
            for pos, fp in tmp:
                commands.append(fp)
        else:
            tmp.sort(key=lambda x: x[0])
            order = 1
            for pos, fp in tmp:
                if pos is None:
                    raise oz.OzException.OzException("All command elements must have a position (explicit order), or none of them may (implicit order)")
                elif pos != order:
                    # this handles both the case where there are duplicates and
                    # the case where there is a missing number
                    raise oz.OzException.OzException("Cannot have duplicate or sparse command position order!")
                order += 1
                commands.append(fp)

        return commands

    def merge_packages(self, packages):
        """
        Method to merge additional packages into an existing TDL.  The
        packages argument should be a properly structured <packages/> string
        as explained in the TDL documentation.  If a package with the same
        name is in the existing TDL and in packages, the value in packages
        overrides.
        """
        packsdoc = lxml.etree.fromstring(packages)
        packslist = packsdoc.xpath('/packages/package')
        self._add_packages(packslist, True)

    def _add_packages(self, packslist, remove_duplicates=False):
        """
        Internal method to add the list of lxml.etree nodes from packslist into
        the self.packages array.  If remove_duplicates is False (the default),
        then a package that is listed both in packslist and in the initial
        TDL is listed twice.  If it is set to True, then a package that is
        listed both in packslist and the initial TDL is listed only once,
        from the packslist.
        """
        for package in packslist:
            # package name
            name = package.get('name')

            if name is None:
                raise oz.OzException.OzException("Package without a name was given")

            # repository that the package lives in (optional)
            repo = _xml_get_value(package, 'repository',
                                  "package repository section", optional=True)

            # filename of the package (optional)
            filename = _xml_get_value(package, 'file', "package filename",
                                      optional=True)

            # arguments to install package (optional)
            args = _xml_get_value(package, 'arguments', "package arguments",
                                  optional=True)

            if remove_duplicates:
                # delete any existing packages with this name
                for p in [package for package in self.packages if package.name == name]:
                    self.packages.remove(p)

            # now add in our new package def
            self.packages.append(Package(name, repo, filename, args))

    def merge_repositories(self, repos):
        """
        Method to merge additional repositories into an existing TDL.  The
        repos argument should be a properly structured <repositories/>
        string as explained in the TDL documentation.  If a repository with
        the same name is in the existing TDL and in repos, the value in
        repos overrides.
        """
        reposdoc = lxml.etree.fromstring(repos)
        reposlist = reposdoc.xpath('/repositories/repository')
        self._add_repositories(reposlist)

    def _add_repositories(self, reposlist):
        """
        Internal method to add the list of lxml.etree nodes from reposlist into
        the self.repositories dictionary.
        """
        def _get_optional_repo_bool(repo, name, default):
            """
            Internal method to get an option boolean from a repo XML section.
            """
            xmlstr = _xml_get_value(repo, name, name, optional=True)
            if xmlstr is None:
                xmlstr = default

            val = oz.ozutil.string_to_bool(xmlstr)
            if val is None:
                raise oz.OzException.OzException("Repository %s property must be 'true', 'yes', 'false', or 'no'" % (name))
            return val

        for repo in reposlist:
            name = repo.get('name')
            if name is None:
                raise oz.OzException.OzException("Repository without a name was given")
            url = _xml_get_value(repo, 'url', 'repository url')

            if urlparse.urlparse(url)[1] in ["localhost", "127.0.0.1",
                                             "localhost.localdomain"]:
                raise oz.OzException.OzException("Repositories cannot be localhost, since they must be reachable from the guest operating system")

            signed = _get_optional_repo_bool(repo, 'signed', 'no')

            persist = _get_optional_repo_bool(repo, 'persisted', 'yes')

            sslverify = _get_optional_repo_bool(repo, 'sslverify', 'no')

            # no need to delete - if the name matches we just overwrite here
            self.repositories[name] = Repository(name, url, signed, persist,
                                                 sslverify)

    def _add_isoextras(self, extraspath, element_type):
        """
        Internal method to add the list of extra ISO elements from the specified
        XML path into the self.isoextras list.
        """
        isoextras = []
        extraslist = self.doc.xpath(extraspath)
        if self.installtype != 'iso' and extraslist:
            raise oz.OzException.OzException("Extra ISO data can only be used with iso install type")

        for extra in extraslist:
            source = extra.get('source')
            if source is None:
                raise oz.OzException.OzException("Extra ISO element without a source was given")
            destination = extra.get('destination')
            if destination is None:
                raise oz.OzException.OzException("Extra ISO element without a destination was given")

            isoextras.append(ISOExtra(element_type, source, destination))

        return isoextras

    # I declare we will use a 2 element version string with a dot
    # This allows simple comparison by conversion to float
    schema_version = "1.0"

    def _validate_tdl_version(self):
        """
        Internal method to validate that we support the TDL version.
        """
        if float(self.version) > float(self.schema_version):
            raise oz.OzException.OzException("TDL version (%s) is higher than our known version (%s)" % (self.version, self.schema_version))
