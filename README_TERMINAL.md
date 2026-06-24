# BeagleBone GMediaRender: Advanced Terminal & Diagnostic Operations

A collection of low-level terminal commands for deep system diagnostics, bus monitoring, and process control of the
Valera Jr. audiophile bare-metal streamer.

## 1. Process & Daemon Management

To tame the systemd hound and manage the rendering endpoint directly:

* **Check live daemon status:**
```bash
  sudo systemctl status gmediarender

```

* **Force immediate restart (applying overrides):**

```bash
sudo systemctl restart gmediarender

```

* **Wipe fail-states and clear journal anomalies:**

```bash
sudo systemctl reset-failed gmediarender

```

* **Total daemon termination:**

```bash
sudo systemctl stop gmediarender

```

## 2. Low-Level Hardware & ALSA Diagnostics

Verify that the bit-perfect stream reaches the physical layer without resampling or software mixing.

* **List active audio hardware interfaces and subdevices:**

```bash
aplay -l

```

* **Inspect stream routing directly from the kernel ring buffer:**

```bash
dmesg | grep -i alsa

```

* **Verify live process memory and active command-line arguments:**

```bash
ps aux | grep gmediarender

```

* **Real-time system journal tracking (stderr/stdout output):**

```bash
journalctl -u gmediarender.service -f --no-tail

```

## 3. Network & End-Point Visibility

Ensure the UPnP/DLNA endpoint advertises itself properly across the local network segment.

* **Check active network sockets and port binding (UPnP port 8200):**

```bash
sudo ss -tulpn | grep gmediarender

```

* **Ping the board locally to verify zero-latency connection:**

```bash
ping -c 4 beaglebone.local

```

## 4. Industrial Storage Health (eMMC / SD Card)

Monitor the physical integrity of the boot medium acquired from local sources.

* **Check available disk space and partition table mapping:**

```bash
df -h

```

    Filesystem      Size  Used Avail Use% Mounted on
    udev            215M     0  215M   0% /dev
    tmpfs            49M  5.3M   44M  11% /run
    /dev/mmcblk1p1  3.5G  3.1G  230M  94% /
    tmpfs           242M     0  242M   0% /dev/shm
    tmpfs           5.0M  4.0K  5.0M   1% /run/lock
    tmpfs           242M     0  242M   0% /sys/fs/cgroup
    tmpfs            49M     0   49M   0% /run/user/0
 

* **Inspect free RAM and system load average (ensuring < 0.1 during playback):**

```bash
htop

```

*(Install via `sudo apt install htop` if missing).*

