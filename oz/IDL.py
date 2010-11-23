# Copyright (C) 2010  Chris Lalancette <clalance@redhat.com>

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

def get_value(doc, xmlstring):
    res = doc.xpathEval(xmlstring)
    if len(res) != 1:
        return None
    return res[0].getContent()

class IDL(object):
    def __init__(self, filename):
        self.doc = None
        self.doc = libxml2.parseFile(filename)

        self._distro = get_value(self.doc, '/image/os/name')
        if self._distro is None:
            raise Exception, "Failed to find OS name in IDL"

        self._update = get_value(self.doc, '/image/os/version')
        if self._update is None:
            raise Exception, "Failed to find OS version in IDL"

        self._arch = get_value(self.doc, '/image/os/arch')
        if self._arch is None:
            raise Exception, "Failed to find OS architecture in IDL"

        self._key = get_value(self.doc, '/image/os/key')
        # key is not required, so it is not fatal if it is None

        install = self.doc.xpathEval('/image/os/install')
        if len(install) != 1:
            raise Exception, "Failed to find OS install in IDL"
        if not install[0].hasProp('type'):
            raise Exception, "Failed to find OS install type in IDL"
        self._installtype = install[0].prop('type')
        if self._installtype == "url":
            self._url = get_value(self.doc, '/image/os/install/url')
            if self._url is None:
                raise Exception, "Failed to find OS install URL in IDL"
        elif self._installtype == "iso":
            self._iso = get_value(self.doc, '/image/os/install/iso')
            if self._iso is None:
                raise Exception, "Failed to find OS install ISO in IDL"
        else:
            raise Exception, "Unknown install type " + self._installtype + " in IDL"

        services = self.doc.xpathEval('/image/services')
        # there may be 0 or 1 <services> elements

        if len(services) == 0:
            self._services = "<services/>"
        elif len(services) == 1:
            self._services = str(services[0])
        else:
            raise Exception, "Invalid number of services, expected 0 or 1"

        self._packages = []
        for package in self.doc.xpathEval('/image/packages/package'):
            self._packages.append(package.prop('name'))

    def __del__(self):
        if self.doc is not None:
            self.doc.freeDoc()

    def distro(self):
        return self._distro
    def update(self):
        return self._update
    def arch(self):
        return self._arch
    def url(self):
        return self._url
    def iso(self):
        return self._iso
    def key(self):
        return self._key
    def installtype(self):
        return self._installtype
    def services(self):
        return self._services
    def packages(self):
        return self._packages
