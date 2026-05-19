#!/usr/bin/env bash
set -euo pipefail

sudo rm -fR /var/lib/rook

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y gdisk parted

wipe_all() {
    local device=$1
    echo "Device: ${device}"
    sudo sgdisk --zap-all "${device}"
    if [ "${device}" = "/dev/nvme1n1" ]; then
        sudo blkdiscard "${device}"
    else
        sudo dd if=/dev/zero of="${device}" bs=1M count=100 oflag=direct,dsync
    fi
    sudo partprobe "${device}"
}

for device in /dev/sd[a-z]; do
    wipe_all "${device}"
done

wipe_all /dev/nvme1n1

sudo reboot
