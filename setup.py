from distutils.core import setup, Extension, Command
from distutils.command.sdist import sdist as _sdist
import os

VERSION = '0.7.0'

datafiles = [('share/man/man1', ['man/oz-install.1', 'man/oz-customize.1',
                                 'man/oz-generate-icicle.1',
                                 'man/oz-cleanup-cache.1'])
             ]

class sdist(_sdist):
    """ custom sdist command, to prep oz.spec file for inclusion """

    def run(self):
        cmd = (""" sed -e "s/@VERSION@/%s/g" < oz.spec.in """ %
               VERSION) + " > oz.spec"
        os.system(cmd)

        _sdist.run(self)

class pytest(Command):
    user_options = []
    def initialize_options(self): pass
    def finalize_options(self): pass
    def run(self):
        import subprocess
        errno = subprocess.call('py.test tests --verbose --tb=short --junitxml=tests/results.xml'.split())
        raise SystemExit(errno)

setup(name='oz',
      version=VERSION,
      description='Oz automated installer',
      author='Chris Lalancette',
      author_email='clalance@redhat.com',
      license='LGPLv2',
      url='http://aeolusproject.org/oz.html',
      package_dir={'oz': 'oz'},
      package_data={'oz': ['auto/*']},
      packages=['oz'],
      scripts=['oz-install', 'oz-generate-icicle', 'oz-customize',
               'oz-cleanup-cache'],
      cmdclass={'sdist': sdist,
                'test' : pytest },
      data_files = datafiles,
      )
