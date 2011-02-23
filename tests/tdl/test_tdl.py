import oz.TDL
import sys

if len(sys.argv) != 2:
    print "Usage: test_tdl.py <tdl>"
    sys.exit(1)

tdl = oz.TDL.TDL(open(sys.argv[1], 'r').read())
