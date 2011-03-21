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

import RedHat
import OzException

class RHEL21Guest(RedHat.RedHatFDGuest):
    def __init__(self, tdl, config, auto):
        RedHat.RedHatFDGuest.__init__(self, tdl, config, auto,
                                      "rhel-2.1-jeos.ks", "pcnet")

def get_class(tdl, config, auto):
    if tdl.update in ["GOLD", "U2", "U3", "U4", "U5", "U6"]:
        return RHEL21Guest(tdl, config, auto)
    raise OzException.OzException("Unsupported RHEL-2.1 update " + tdl.update)
