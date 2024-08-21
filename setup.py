from distutils.core import setup, Command
from distutils.command.sdist import sdist as _sdist
import subprocess
import time

VERSION = '0.19.0'
RELEASE = '0'

datafiles = [('share/man/man1', ['man/oz-install.1', 'man/oz-generate-icicle.1',
                                 'man/oz-customize.1',
                                 'man/oz-cleanup-cache.1']),
             ('share/man/man5', ['man/oz-examples.5'])
             ]

class sdist(_sdist):
    """ custom sdist command, to prep oz.spec file for inclusion """

    def run(self):
        global VERSION
        global RELEASE

        # Create a development release string for later use
        git_head = subprocess.Popen("git log -1 --pretty=format:%h",
                                    shell=True,
                                    stdout=subprocess.PIPE).communicate()[0].strip()
        date = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        git_release = "%sgit%s" % (date, git_head.decode())

        # Expand macros in oz.spec.in and create oz.spec
        spec_in = open('oz.spec.in', 'r')
        spec = open('oz.spec', 'w')
        for line in spec_in.readlines():
            if "@VERSION@" in line:
                line = line.replace("@VERSION@", VERSION)
            elif "@RELEASE@" in line:
                # If development release, include date+githash in %{release}
                if RELEASE.startswith('0'):
                    RELEASE += '.' + git_release
                line = line.replace("@RELEASE@", RELEASE)
            spec.write(line)
        spec_in.close()
        spec.close()

        # Run parent constructor
        _sdist.run(self)

class pytest(Command):
    user_options = []
    def initialize_options(self): pass
    def finalize_options(self): pass
    def run(self):
        try:
            errno = subprocess.call('py.test-3 tests --verbose --tb=short --junitxml=tests/results.xml'.split())
        except OSError as e:
            if e.errno == 2:
                raise OSError(2, "No such file or directory: py.test")
            raise
        raise SystemExit(errno)

setup(name='oz',
      version=VERSION,
      description='Oz automated installer',
      author='Chris Lalancette',
      author_email='clalancette@gmail.com',
      license='LGPLv2',
      url='http://github.com/clalancette/oz',
      package_dir={'oz': 'oz'},
      package_data={'oz': ['auto/*', '*.rng']},
      packages=['oz'],
      scripts=['oz-install', 'oz-generate-icicle', 'oz-customize',
               'oz-cleanup-cache'],
      cmdclass={'sdist': sdist,
                'test' : pytest },
      data_files = datafiles,
      )
