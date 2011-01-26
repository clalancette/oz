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

import Guest

def get_value(doc, xmlstring):
    res = doc.xpathEval(xmlstring)
    if len(res) != 1:
        return None
    return res[0].getContent()

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
            # we allow empty content so that you can "touch" files
            self.files[name] = afile.getContent().strip()

    def __del__(self):
        if self.doc is not None:
            self.doc.freeDoc()
