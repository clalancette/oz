install
text
url --url REPLACE_ME
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
part / --fstype ext3 --size=1024 --grow --ondisk=hda
part swap --size 768 --grow --maxsize=1536 --ondisk=hda
reboot

%packages
@ Network Support
@ Network Managed Workstation
@ Utilities
nc
wget
