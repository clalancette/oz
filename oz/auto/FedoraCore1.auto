install
text
keyboard us
lang en_US.UTF-8
langsupport --default en_US.UTF-8 en_US.UTF-8
mouse generic3ps/2 --device psaux
skipx
network --device eth0 --bootproto dhcp
rootpw %ROOTPW%
firewall --disabled
authconfig --enableshadow --enablemd5
timezone --utc America/New_York
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr yes
clearpart --all --drives=hda

part /boot --fstype ext3 --size=200 --ondisk=hda
part pv.2 --size=1 --grow --ondisk=hda
volgroup VolGroup00 --pesize=32768 pv.2
logvol swap --fstype swap --name=LogVol01 --vgname=VolGroup00 --size=768 --grow --maxsize=1536
logvol / --fstype ext3 --name=LogVol00 --vgname=VolGroup00 --size=1024 --grow
reboot

%packages
@base

%post
