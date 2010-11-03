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
            # httpd redirects don't work, so make sure we have a / at the end
            if self._url[-1] != '/':
                self._url = self._url + '/'
        elif self._installtype == "iso":
            self._iso = get_value(self.doc, '/image/os/install/iso')
            if self._iso is None:
                raise Exception, "Failed to find OS install ISO in IDL"
        else:
            raise Exception, "Unknown install type " + self._installtype + " in IDL"

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
