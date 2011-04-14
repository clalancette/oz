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

import libxml2
import base64

import OzException

def get_value(doc, xmlstring, component, optional=False):
    res = doc.xpathEval(xmlstring)
    if len(res) == 1:
        return res[0].getContent()
    elif len(res) == 0:
        if optional:
            return None
        else:
            raise OzException.OzException("Failed to find %s in TDL" % (component))
    else:
        raise OzException.OzException("Expected 0 or 1 %s in TDL, saw %d" % (component, len(res)))

class Repository(object):
    def __init__(self, name, url, signed):
        self.name = name
        self.url = url
        self.signed = signed

class Package(object):
    def __init__(self, name, repo, filename, args):
        self.name = name
        self.repo = repo
        self.filename = filename
        self.args = args

def string_to_bool(instr, component):
    lower = instr.lower()
    if lower == 'no' or lower == 'false':
        return False
    if lower == 'yes' or lower == 'true':
        return True
    raise OzException.OzException("%s property must be 'true', 'yes', 'false', or' no'" % (component))

class TDL(object):
    def __init__(self, xmlstring):
        self.doc = None

        self.doc = libxml2.parseDoc(xmlstring)

        self.name = get_value(self.doc, '/template/name', 'template name')

        self.distro = get_value(self.doc, '/template/os/name', 'OS name')

        self.update = get_value(self.doc, '/template/os/version', 'OS version')

        self.arch = get_value(self.doc, '/template/os/arch', 'OS architecture')
        if self.arch != "i386" and self.arch != "x86_64":
            raise OzException.OzException("Architecture must be one of 'i386' or 'x86_64'")

        self.key = get_value(self.doc, '/template/os/key', 'OS key',
                             optional=True)
        # key is not required, so it is not fatal if it is None

        self.description = get_value(self.doc, '/template/description',
                                     'description', optional=True)
        # description is not required, so it is not fatal if it is None

        install = self.doc.xpathEval('/template/os/install')
        if len(install) != 1:
            raise OzException.OzException("Expected 1 OS install section in TDL, saw %d" % (len(install)))
        self.installtype = install[0].prop('type')
        if self.installtype is None:
            raise OzException.OzException("Failed to find OS install type in TDL")
        if self.installtype == "url":
            self.url = get_value(self.doc, '/template/os/install/url',
                                 'OS install URL')
        elif self.installtype == "iso":
            self.iso = get_value(self.doc, '/template/os/install/iso',
                                 'OS install ISO')
        else:
            raise OzException.OzException("Unknown install type " + self.installtype + " in TDL")

        self.rootpw = get_value(self.doc, '/template/os/rootpw',
                                "root/Administrator password", optional=True)

        self.packages = []
        for package in self.doc.xpathEval('/template/packages/package'):
            # package name
            name = package.prop('name')
            if name is None:
                raise OzException.OzException("Package without a name was given")

            # repository that the package lives in (optional)
            repo = get_value(package, 'repository',
                             "package repository section", optional=True)

            # filename of the package (optional)
            filename = get_value(package, 'file', "package filename",
                                 optional=True)

            # arguments to install package (optional)
            args = get_value(package, 'arguments', "package arguments",
                             optional=True)

            self.packages.append(Package(name, repo, filename, args))

        self.files = {}
        for afile in self.doc.xpathEval('/template/files/file'):
            name = afile.prop('name')
            if name is None:
                raise OzException.OzException("File without a name was given")
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
                raise OzException.OzException("File type for %s must be 'raw' or 'base64'" % (name))

        self.repositories = {}
        for repo in self.doc.xpathEval('/template/repositories/repository'):
            name = repo.prop('name')
            if name is None:
                raise OzException.OzException("Repository without a name was given")
            url = get_value(repo, 'url', 'repository url')

            signstr = get_value(repo, 'signed', 'signed', optional=True)
            if signstr is None:
                signstr = 'no'

            signed = string_to_bool(signstr, "Repository signed")

            self.repositories[name] = Repository(name, url, signed)

    def __del__(self):
        if self.doc is not None:
            self.doc.freeDoc()
