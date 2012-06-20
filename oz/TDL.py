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
Template Description Language (TDL)
"""

import libxml2
import base64
import urlparse

import oz.ozutil
import oz.OzException

def _xml_get_value(doc, xmlstring, component, optional=False):
    """
    Function to get the contents from an XML node.  It takes 4 arguments:

    doc       - The libxml2 document to get a value from.
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
    res = doc.xpathEval(xmlstring)
    if len(res) == 1:
        return res[0].getContent()
    elif len(res) == 0:
        if optional:
            return None
        else:
            raise oz.OzException.OzException("Failed to find %s in TDL" % (component))
    else:
        raise oz.OzException.OzException("Expected 0 or 1 %s in TDL, saw %d" % (component, len(res)))

class Repository(object):
    """
    Class that represents a single repository to be used for installing
    packages.  Objects of this type contain 3 pieces of information:

    name       - The name of this repository.
    url        - The URL of this repository.
    (all remaining properties are optional with defaults in parentheses)
    signed     - Whether this repository is signed (no)
    persistent - Whether this repository should remain in the final
                 image (yes)
    clientcert - An SSL client certificate to access protected content -
                 e.g. pulp repos (None)
    clientkey  - An SSL client key to access protected content - e.g. pulp
                 repos (None)
    cacert     - A CA cert to be used to validate an https repository (None)
    sslverify  - Whether yum should check the server cert against known CA
                 certs (no)
    """
    def __init__(self, name, url, signed, persistent, clientcert, clientkey,
                 cacert, sslverify):
        self.name = name
        self.url = url
        self.signed = signed
        self.persistent = persistent
        self.clientcert = clientcert
        self.clientkey = clientkey
        self.cacert = cacert
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
        self.doc = None

        self.doc = libxml2.parseDoc(xmlstring)

        template = self.doc.xpathEval('/template')
        if len(template) != 1:
            raise oz.OzException.OzException("Expected 1 template section in TDL, saw %d" % (len(template)))
        self.version = template[0].prop('version')

        if self.version:
            self._validate_tdl_version()

        self.name = _xml_get_value(self.doc, '/template/name', 'template name')

        self.distro = _xml_get_value(self.doc, '/template/os/name', 'OS name')

        self.update = _xml_get_value(self.doc, '/template/os/version',
                                     'OS version')

        self.arch = _xml_get_value(self.doc, '/template/os/arch',
                                   'OS architecture')
        if self.arch != "i386" and self.arch != "x86_64":
            raise oz.OzException.OzException("Architecture must be one of 'i386' or 'x86_64'")

        self.key = _xml_get_value(self.doc, '/template/os/key', 'OS key',
                                  optional=True)
        # key is not required, so it is not fatal if it is None

        self.description = _xml_get_value(self.doc, '/template/description',
                                          'description', optional=True)
        # description is not required, so it is not fatal if it is None

        install = self.doc.xpathEval('/template/os/install')
        if len(install) != 1:
            raise oz.OzException.OzException("Expected 1 OS install section in TDL, saw %d" % (len(install)))
        self.installtype = install[0].prop('type')
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
        packageslist = self.doc.xpathEval('/template/packages/package')
        self._add_packages(packageslist)

        self.files = {}
        for afile in self.doc.xpathEval('/template/files/file'):
            name = afile.prop('name')
            if name is None:
                raise oz.OzException.OzException("File without a name was given")
            contenttype = afile.prop('type')
            if contenttype is None:
                contenttype = 'raw'

            content = afile.getContent().strip()
            if contenttype == 'raw':
                self.files[name] = content
            elif contenttype == 'base64':
                if len(content) == 0:
                    self.files[name] = ""
                else:
                    self.files[name] = base64.b64decode(content)
            else:
                raise oz.OzException.OzException("File type for %s must be 'raw' or 'base64'" % (name))

        self.repositories = {}
        repositorieslist = self.doc.xpathEval('/template/repositories/repository')
        self._add_repositories(repositorieslist)

        self.commands = {}
        for command in self.doc.xpathEval('/template/commands/command'):
            name = command.prop('name')
            if name is None:
                raise oz.OzException.OzException("Command without a name was given")
            contenttype = command.prop('type')
            if contenttype is None:
                contenttype = 'raw'

            content = command.getContent().strip()
            if contenttype == 'raw':
                self.commands[name] = content
            elif contenttype == 'base64':
                if len(content) == 0:
                    raise oz.OzException.OzException("Empty commands are not allowed")
                else:
                    self.commands[name] = base64.b64decode(content)
            else:
                raise oz.OzException.OzException("File type for %s must be 'raw' or 'base64'" % (name))

        self.disksize = _xml_get_value(self.doc, '/template/disk/size',
                                       'disk size', optional=True)

    def merge_packages(self, packages):
        """
        Method to merge additional packages into an existing TDL.  The
        packages argument should be a properly structured <packages/> string
        as explained in the TDL documentation.  If a package with the same
        name is in the existing TDL and in packages, the value in packages
        overrides.
        """
        packsdoc = libxml2.parseDoc(packages)
        packslist = packsdoc.xpathEval('/packages/package')
        self._add_packages(packslist, True)

    def _add_packages(self, packslist, remove_duplicates = False):
        """
        Internal method to add the list of libxml2 nodes from packslist into
        the self.packages array.  If remove_duplicates is False (the default),
        then a package that is listed both in packslist and in the initial
        TDL is listed twice.  If it is set to True, then a package that is
        listed both in packslist and the initial TDL is listed only once,
        from the packslist.
        """
        for package in packslist:
            # package name
            name = package.prop('name')

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
                for package in filter(lambda package: package.name == name,
                                      self.packages):
                    self.packages.remove(package)

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
        reposdoc = libxml2.parseDoc(repos)
        reposlist = reposdoc.xpathEval('/repositories/repository')
        self._add_repositories(reposlist)

    def _add_repositories(self, reposlist):
        """
        Internal method to add the list of libxml2 nodes from reposlist into
        the self.repositories dictionary.
        """
        def _get_optional_repo_bool(repo, name, default='no'):
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
            name = repo.prop('name')
            if name is None:
                raise oz.OzException.OzException("Repository without a name was given")
            url = _xml_get_value(repo, 'url', 'repository url')

            if urlparse.urlparse(url)[1] in ["localhost", "127.0.0.1",
                                             "localhost.localdomain"]:
                raise oz.OzException.OzException("Repositories cannot be localhost, since they must be reachable from the guest operating system")

            signed = _get_optional_repo_bool(repo, 'signed')

            persist = _get_optional_repo_bool(repo, 'persisted', default='yes')

            sslverify = _get_optional_repo_bool(repo, 'sslverify')

            clientcert = _xml_get_value(repo, 'clientcert', 'clientcert',
                                        optional=True)
            if clientcert:
                clientcert = clientcert.strip()

            clientkey = _xml_get_value(repo, 'clientkey', 'clientkey',
                                       optional=True)
            if clientkey:
                clientkey = clientkey.strip()

            if clientkey and not clientcert:
                raise oz.OzException.OzException("You cannot specify a clientkey without a clientcert")

            cacert = _xml_get_value(repo, 'cacert', 'cacert', optional=True)
            if cacert:
                cacert = cacert.strip()

            if sslverify and not cacert:
                raise oz.OzException.OzException("If sslverify is true you must also provide a ca cert")

            # no need to delete - if the name matches we just overwrite here
            self.repositories[name] = Repository(name, url, signed, persist,
                                                 clientcert, clientkey, cacert,
                                                 sslverify)

    # I declare we will use a 2 element version string with a dot
    # This allows simple comparison by conversion to float
    schema_version = "1.0"

    def _validate_tdl_version(self):
        """
        Internal method to validate that we support the TDL version.
        """
        if float(self.version) > float(self.schema_version):
            raise oz.OzException.OzException("TDL version (%s) is higher than our known version (%s)" % (self.version, self.schema_version))

    def __del__(self):
        if self.doc is not None:
            self.doc.freeDoc()
