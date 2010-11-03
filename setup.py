from distutils.core import setup, Extension
from distutils.command.sdist import sdist as _sdist
import os

VERSION = '0.0.4'

class sdist(_sdist):
    """ custom sdist command, to prep oz.spec file for inclusion """

    def run(self):
        cmd = (""" sed -e "s/@VERSION@/%s/g" < oz.spec.in """ %
               VERSION) + " > oz.spec"
        os.system(cmd)

        _sdist.run(self)

setup(name='oz',
      version=VERSION,
      description='Oz automated installer',
      author='Chris Lalancette',
      author_email='clalance@redhat.com',
      license='LGPLv2',
      url='http://deltacloud.org',
      package_dir={'oz': 'oz'},
      package_data={'oz': ['auto/*', 'guesttools/*']},
      packages=['oz'],
      scripts=['ozinstall', 'oz-generate-cdl'],
      cmdclass={'sdist': sdist},
      )
