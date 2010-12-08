install
text
keyboard us
lang en_US
mouse generic3ps/2 --device psaux
skipx
network --bootproto dhcp
rootpw ozrootpw
auth --useshadow --enablemd5
timezone --utc America/New_York
lilo --location mbr --linear
zerombr yes
clearpart --all --drives=hda

part /boot --size=200
part / --size=1024 --grow
part swap --size 768 --grow --maxsize=1536
reboot

%packages
python
nc
wget
telnet
