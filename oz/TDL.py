# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

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

import oz.OzException

def get_value(doc, xmlstring, component, optional=False):
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

    name   - The name of this repository.
    url    - The URL of this repository.
    signed - Whether this repository is signed (optional).
    """
    def __init__(self, name, url, signed):
        self.name = name
        self.url = url
        self.signed = signed

class Package(object):
    """
    Class that represents a single package to be installed.
    Objects of this type contain 4 pieces of information:

    name     - The name of the package.
    repo     - The repository that this package comes from (optional).
    filename - The filename that contains this package (optional).
    args     - Arguments necessary to install this package (optional).
    """
    def __init__(self, name, repo, filename, args, reboot):
        self.name = name
        self.repo = repo
        self.filename = filename
        self.args = args
        self.reboot = reboot

def string_to_bool(instr, component):
    """
    Function to take a string and determine whether it is True, Yes, False,
    or No.  It takes 2 arguments:

    instr     - The string to examine.
    component - A string representing which TDL component is being
                looked for (used in error reporting).

    Returns True if instr is "Yes" or "True", False if instr is "No"
    or "False", and raises an Exception otherwise.
    """
    lower = instr.lower()
    if lower == 'no' or lower == 'false':
        return False
    if lower == 'yes' or lower == 'true':
        return True
    raise oz.OzException.OzException("%s property must be 'true', 'yes', 'false', or' no'" % (component))

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
    """
    def __init__(self, xmlstring):
        self.doc = None

        self.doc = libxml2.parseDoc(xmlstring)

        self.name = get_value(self.doc, '/template/name', 'template name')

        self.distro = get_value(self.doc, '/template/os/name', 'OS name')

        self.update = get_value(self.doc, '/template/os/version', 'OS version')

        self.arch = get_value(self.doc, '/template/os/arch', 'OS architecture')
        if self.arch != "i386" and self.arch != "x86_64":
            raise oz.OzException.OzException("Architecture must be one of 'i386' or 'x86_64'")

        self.key = get_value(self.doc, '/template/os/key', 'OS key',
                             optional=True)
        # key is not required, so it is not fatal if it is None

        self.description = get_value(self.doc, '/template/description',
                                     'description', optional=True)
        # description is not required, so it is not fatal if it is None

        install = self.doc.xpathEval('/template/os/install')
        if len(install) != 1:
            raise oz.OzException.OzException("Expected 1 OS install section in TDL, saw %d" % (len(install)))
        self.installtype = install[0].prop('type')
        if self.installtype is None:
            raise oz.OzException.OzException("Failed to find OS install type in TDL")
        if self.installtype == "url":
            self.url = get_value(self.doc, '/template/os/install/url',
                                 'OS install URL')
        elif self.installtype == "iso":
            self.iso = get_value(self.doc, '/template/os/install/iso',
                                 'OS install ISO')
        else:
            raise oz.OzException.OzException("Unknown install type " + self.installtype + " in TDL")

        self.rootpw = get_value(self.doc, '/template/os/rootpw',
                                "root/Administrator password", optional=True)

        self.packages = []
        for package in self.doc.xpathEval('/template/packages/package'):
            # package name
            name = package.prop('name')
            if name is None:
                raise oz.OzException.OzException("Package without a name was given")

            # repository that the package lives in (optional)
            repo = get_value(package, 'repository',
                             "package repository section", optional=True)

            # filename of the package (optional)
            filename = get_value(package, 'file', "package filename",
                                 optional=True)

            # arguments to install package (optional)
            args = get_value(package, 'arguments', "package arguments",
                             optional=True)

            # does the package require reboot (optional)
            rebootstr = get_value(package,'reboot', "package reboot",
                                  optional=True)
            if rebootstr == None:
                rebootstr = 'no'

            reboot = string_to_bool(rebootstr, "Package reboot")

            self.packages.append(Package(name, repo, filename, args, reboot))

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
        for repo in self.doc.xpathEval('/template/repositories/repository'):
            name = repo.prop('name')
            if name is None:
                raise oz.OzException.OzException("Repository without a name was given")
            url = get_value(repo, 'url', 'repository url')

            signstr = get_value(repo, 'signed', 'signed', optional=True)
            if signstr is None:
                signstr = 'no'

            signed = string_to_bool(signstr, "Repository signed")

            self.repositories[name] = Repository(name, url, signed)

    def __del__(self):
        if self.doc is not None:
            self.doc.freeDoc()
