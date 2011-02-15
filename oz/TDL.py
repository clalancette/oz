# Copyright (C) 2010,2011  Chris Lalancette <clalance@redhat.com>

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import libxml2
import base64

import Guest

def get_value(doc, xmlstring):
    res = doc.xpathEval(xmlstring)
    if len(res) != 1:
        return None
    return res[0].getContent()

class Repository(object):
    def __init__(self, name, url, signed):
        self.name = name
        self.url = url
        self.signed = signed

class TDL(object):
    def __init__(self, xmlstring):
        self.doc = None

        self.doc = libxml2.parseDoc(xmlstring)

        self.name = get_value(self.doc, '/template/name')
        if self.name is None:
            raise Guest.OzException("Failed to find name of template in TDL")

        self.distro = get_value(self.doc, '/template/os/name')
        if self.distro is None:
            raise Guest.OzException("Failed to find OS name in TDL")

        self.update = get_value(self.doc, '/template/os/version')
        if self.update is None:
            raise Guest.OzException("Failed to find OS version in TDL")

        self.arch = get_value(self.doc, '/template/os/arch')
        if self.arch is None:
            raise Guest.OzException("Failed to find OS architecture in TDL")
        if self.arch != "i386" and self.arch != "x86_64":
            raise Guest.OzException("Architecture must be one of 'i386' or 'x86_64'")

        self.key = get_value(self.doc, '/template/os/key')
        # key is not required, so it is not fatal if it is None

        install = self.doc.xpathEval('/template/os/install')
        if len(install) != 1:
            raise Guest.OzException("Expected 1 OS install section in TDL, saw %d" % (len(install)))
        self.installtype = install[0].prop('type')
        if self.installtype is None:
            raise Guest.OzException("Failed to find OS install type in TDL")
        if self.installtype == "url":
            self.url = get_value(self.doc, '/template/os/install/url')
            if self.url is None:
                raise Guest.OzException("Failed to find OS install URL in TDL")
        elif self.installtype == "iso":
            self.iso = get_value(self.doc, '/template/os/install/iso')
            if self.iso is None:
                raise Guest.OzException("Failed to find OS install ISO in TDL")
        else:
            raise Guest.OzException("Unknown install type " + self.installtype + " in TDL")

        self.packages = []
        for package in self.doc.xpathEval('/template/packages/package'):
            name = package.prop('name')
            if name is None:
                raise Guest.OzException("Package without a name was given")
            self.packages.append(name)

        self.files = {}
        for afile in self.doc.xpathEval('/template/files/file'):
            name = afile.prop('name')
            if name is None:
                raise Guest.OzException("File without a name was given")
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
                raise Guest.OzException("File type for %s must be 'raw' or 'base64'" % (name))

        self.repositories = []
        for repo in self.doc.xpathEval('/template/repositories/repository'):
            name = repo.prop('name')
            if name is None:
                raise Guest.OzException("Repository without a name was given")
            url = repo.prop('url')
            if url is None:
                raise Guest.OzException("Repository without a url was given")
            signstr = repo.prop('signed')
            if signstr is None:
                signstr = 'no'
            if signstr.lower() == 'no' or signstr.lower() == 'false':
                signed = False
            elif signstr.lower() == 'yes' or signstr.lower() == 'true':
                signed = True
            else:
                raise Guest.OzException("Repository signed property must be 'true' or 'false'")
            self.repositories.append(Repository(name, url, signed))

    def __del__(self):
        if self.doc is not None:
            self.doc.freeDoc()
