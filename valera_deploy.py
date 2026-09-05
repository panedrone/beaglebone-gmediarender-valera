#!/usr/bin/env python3
"""Deploy the renderer.

Rewritten 2026-09-05 for the microSD system (Debian 13, kernel 5.10). The
previous version hardcoded `card 1` and wrote its unit into
/lib/systemd/system, both of which were right for the factory eMMC image and
wrong everywhere else:

  * the card index is not a constant. There is no onboard codec on this board,
    so the USB DAC takes whatever index is free - 1 on the factory image, 0 on
    a current one. A hardcoded index does not fail loudly; the renderer simply
    cannot open the device.
  * /lib/systemd/system belongs to dpkg. The old image shipped a packaged
    gmediarender.service that had to be overridden in place; the current
    package ships none, so the unit belongs in /etc/systemd/system where it
    will not be argued with on upgrade.

Run it with sudo. It detects the card, points ALSA straight at the hardware,
installs the unit and starts the daemon.
"""

import os
import re
import subprocess
import sys
import time

UNIT_PATH = "/etc/systemd/system/gmediarender.service"
LEGACY_UNIT = "/lib/systemd/system/gmediarender.service"
LEGACY_DROPIN = "/etc/systemd/system/gmediarender.service.d"
FRIENDLY_NAME = "BeagleBone SD"


def run(args, **kw):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, **kw)


def find_card():
    """The index of the first card that actually has a playback device."""
    try:
        with open("/proc/asound/cards") as fh:
            cards = fh.read()
    except IOError:
        return None, None
    for line in cards.splitlines():
        m = re.match(r"\s*(\d+)\s+\[(\S+)", line)
        if m and os.path.isdir("/proc/asound/card%s/pcm0p" % m.group(1)):
            return int(m.group(1)), m.group(2)
    return None, None


if os.geteuid() != 0:
    print("❌ Root required — the unit and /etc/asound.conf are not yours otherwise.")
    print("👉 sudo ./valera_deploy.py")
    sys.exit(1)

print("🚀 Deploying GMediaRender")

# 1. Which card. Everything below depends on getting this right, so it happens
#    first and stops the script if there is nothing to play to.
card, name = find_card()
if card is None:
    print("\n❌ No playback card found. Is the DAC plugged in and powered?")
    print("👉 Check with: aplay -l")
    sys.exit(1)
print("\n🔍 Step 1: found card %d (%s)" % (card, name))

# 2. MPD, only if it is actually there. On the current base image it is not
#    installed at all, and masking a package that does not exist is noise.
if run(["systemctl", "list-unit-files", "mpd.service"]).stdout.count("mpd.service"):
    print("\n🧹 Step 2: MPD present — stopping and masking it")
    for verb in ("stop", "disable", "mask"):
        run(["systemctl", verb, "mpd"])
    print("✅ MPD masked.")
else:
    print("\n🧹 Step 2: no MPD installed, nothing to mask.")

# 3. ALSA straight to the hardware. `type hw` and not `plug` or `dmix`: those
#    resample and mix, which is exactly what this box exists to avoid.
print("\n🎛️  Step 3: pointing ALSA default at hw:%d,0" % card)
with open("/etc/asound.conf", "w") as fh:
    fh.write("""pcm.!default {
    type hw
    card %d
    device 0
}

ctl.!default {
    type hw
    card %d
}
""" % (card, card))
print("✅ /etc/asound.conf written.")

# 4. Anything the old deployment left lying around. A stale unit in
#    /lib/systemd/system would win over ours on some systemd versions and there
#    is no reason to find that out the hard way.
print("\n🔥 Step 4: clearing legacy overrides")
removed = []
if os.path.isdir(LEGACY_DROPIN):
    run(["rm", "-rf", LEGACY_DROPIN]); removed.append(LEGACY_DROPIN)
if os.path.exists(LEGACY_UNIT):
    run(["rm", "-f", LEGACY_UNIT]); removed.append(LEGACY_UNIT)
print("✅ " + (", ".join(removed) if removed else "nothing stale found."))

# 5. The unit. No device in the flags — alsasink takes the default from
#    /etc/asound.conf, which is where the card index already lives.
print("\n📝 Step 5: writing %s" % UNIT_PATH)
with open(UNIT_PATH, "w") as fh:
    fh.write("""[Unit]
Description=GMediaRender UPnP Renderer
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/gmediarender -f "%s" -o gst --gstout-audiosink=alsasink
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
""" % FRIENDLY_NAME)
print("✅ Unit written.")

# 6. Go.
print("\n🔄 Step 6: reloading systemd and starting the daemon")
run(["systemctl", "daemon-reload"])
run(["systemctl", "enable", "gmediarender.service"])
run(["systemctl", "restart", "gmediarender"])
# libupnp needs a moment to bind before ss can see the port; asking too early
# reports a healthy daemon with no address, which reads like a fault.
time.sleep(3)


print("\n📊 Step 7: health check")
if run(["systemctl", "is-active", "gmediarender"]).stdout.strip() == "active":
    listen = ""
    for line in run(["ss", "-tulpn"]).stdout.splitlines():
        if "gmediarender" in line and "LISTEN" in line:
            listen = line.split()[4]
            break
    print("\n🎉 Up. '%s' is advertising%s." % (
        FRIENDLY_NAME, " on " + listen if listen else ""))
    print("🎵 Point foobar2000 at it.")
    print("\n👉 Worth confirming the chain actually delivers, not just that the")
    print("   daemon started:  sudo ./valera_rate_check.py")
else:
    print("\n🤔 Configuration applied but the daemon did not start.")
    print("👉 systemctl status gmediarender")
    print("👉 journalctl -u gmediarender -n 50 --no-pager")
    sys.exit(1)
