# Copyright (C) 2013  Chris Lalancette <clalancette@gmail.com>

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

"""
Linux-specific utility functions.
"""

import re

def get_default_runlevel(g_handle):
    """
    Function to determine the default runlevel based on the /etc/inittab.
    """
    runlevel = "3"
    if g_handle.exists('/etc/inittab'):
        lines = g_handle.cat('/etc/inittab').split("\n")
        for line in lines:
            if re.match('id:', line):
                runlevel = line.split(':')[1]
                break

    return runlevel
