install
text
keyboard us
lang en_US.UTF-8
skipx
network --device eth0 --bootproto dhcp
rootpw --iscrypted $1$0q7k23Sr$aKkhNCvyxvwmc5DoVi28k.
firewall --disabled
authconfig --enableshadow --enablemd5
selinux --permissive
timezone --utc America/New_York
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr yes
clearpart --all --drives=vda

part /boot --fstype ext3 --size=200 --ondisk=vda
part pv.2 --size=1 --grow --ondisk=vda
volgroup VolGroup00 --pesize=32768 pv.2
logvol swap --fstype swap --name=LogVol01 --vgname=VolGroup00 --size=768 --grow --maxsize=1536
logvol / --fstype ext3 --name=LogVol00 --vgname=VolGroup00 --size=1024 --grow
reboot

%packages
@admin-tools
@base
@core
@editors
@hardware-support
@text-internet
gpgme
gnupg2
gok
nc
wget

%post
