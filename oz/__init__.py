"""
Class for automated operating system installation.

Oz is a set of classes to do automated operating system installation.  It
has built-in knowledge of the proper things to do for each of the supported
operating systems, so the data that the user must provide is very minimal.
This data is supplied in the form of an XML document that describes what
type of operating system is to be installed and where to get the
installation media.  Oz handles the rest.

The simplest Oz program (without error handling or any advanced features)
would look something like:

import oz.TDL
import oz.GuestFactory

tdl_xml = \"\"\"
<template>
  <name>f13jeos</name>
  <os>
    <name>Fedora</name>
    <version>13</version>
    <arch>x86_64</arch>
    <install type='url'>
      <url>http://download.fedoraproject.org/pub/fedora/linux/releases/13/Fedora/x86_64/os/</url>
    </install>
  </os>
  <description>Fedora 13</description>
</template>
\"\"\"

tdl = oz.TDL.TDL(tdl_xml)
guest = oz.GuestFactory.guest_factory(tdl, None, None)
guest.generate_install_media()
guest.generate_diskimage()
guest.install()
"""
