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

Amended 2026-11-19: the unit no longer restarts the daemon in a loop. With
`Restart=always` and the DAC unplugged, gmediarender died on the missing ALSA
device and systemd raised it again every 5 seconds, for as long as the cable
was out. It is bound to the card's device unit instead: systemd stops the
service when the card goes and a udev rule starts it when the card comes back.
Nothing polls anything (ADR-003).

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
UDEV_RULE = "/etc/udev/rules.d/90-gmediarender.rules"
FRIENDLY_NAME = "BeagleBone"


def run(args, **kw):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, **kw)


def card_device_unit(index):
    """The systemd device unit of card `index`, or None.

    systemd names a device unit after its sysfs path, escaped. There is no
    shorter alias to lean on: /dev/snd/* nodes carry no systemd tag, so
    dev-snd-pcmC1D0p.device exists but stays inactive and would bind the
    service to a unit that never comes up.
    """
    path = "/sys/class/sound/card%d" % index
    if not os.path.exists(path):
        return None
    out = run(["systemd-escape", "-p", "--suffix=device",
               os.path.realpath(path)]).stdout.strip()
    return out or None


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
#    The service is bound to the card instead of being restarted on a timer:
#    without the card there is nothing for alsasink to open, and a daemon that
#    dies and respawns every 5 seconds is noise on a box built to be quiet.
print("\n📝 Step 5: writing %s" % UNIT_PATH)
device = card_device_unit(card)
if device:
    print("   bound to %s" % device)
    binding = "BindsTo=%s\nAfter=%s\n" % (device, device)
else:
    # Without the device unit the binding would be a guess; a service that is
    # not restarted at all is still better than one that respawns forever.
    print("   ⚠️  no device unit for card %d: the service will not be bound to it" % card)
    binding = ""
with open(UNIT_PATH, "w") as fh:
    fh.write("""[Unit]
Description=GMediaRender UPnP Renderer
After=network-online.target sound.target
Wants=network-online.target
%s
[Service]
Type=simple
ExecStart=/usr/bin/gmediarender -f "%s" -o gst --gstout-audiosink=alsasink
Restart=no
User=root

[Install]
WantedBy=multi-user.target
""" % (binding, FRIENDLY_NAME))
print("✅ Unit written.")

# 5b. The way back. BindsTo stops the service when the card goes; starting it
#     again when the card returns is udev's job, on the event itself.
print("\n🔌 Step 5b: writing %s" % UDEV_RULE)
with open(UDEV_RULE, "w") as fh:
    fh.write('# The renderer follows the sound card: no polling, no restart loop.\n'
             'SUBSYSTEM=="sound", ACTION=="add", KERNEL=="card*", '
             'ENV{SYSTEMD_WANTS}+="gmediarender.service"\n')
run(["udevadm", "control", "--reload-rules"])
print("✅ udev rule written.")

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
