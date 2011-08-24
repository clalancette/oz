install
text
url --url REPLACE_ME
keyboard us
lang en_US
mouse generic3ps/2 --device psaux
skipx
network --device eth0 --bootproto dhcp
rootpw %ROOTPW%
firewall --disabled
auth --useshadow --enablemd5
timezone --utc America/New_York
lilo --location mbr --linear
zerombr yes
clearpart --all --drives=hda

part /boot --size=200 --ondisk=hda
part / --size=1024 --grow --ondisk=hda
part swap --size 768 --grow --maxsize=1536 --ondisk=hda
reboot

%packages
python
openssh
openssh-server
nc
wget
