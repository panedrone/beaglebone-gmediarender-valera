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
was out. Now it is `Restart=no` and a udev rule starts the service when a
sound card appears: the daemon dies once with the card and comes back with it,
and nothing polls anything (ADR-003).

The same day the first attempt at this also wrote `BindsTo=` the card's device
unit, and that broke the renderer within the hour: the device unit's name
carries the USB interface number, so swapping the RAW-HA1's direct USB
connection for the Amanero card (1-1:1.0 -> 1-1:1.1) left systemd refusing to
start the service at all, with "Dependency failed". The binding is gone; the
udev rule never needed it.

Amended again later the same day: a second udev rule stops the service when
the card goes away. "The daemon dies with its card" turned out to be true only
while the card is open and playing - with a PCM left open after a stream ran
out, gmediarender survived the unplug holding a dead handle, and the USB
isochronous stream ran on at ~8200 interrupts/s for three hours with nothing
playing. Taking the service down on the remove event releases the handle.

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
CARD_GONE_HELPER = "/usr/local/sbin/gmediarender-card-gone"
FRIENDLY_NAME = "BeagleBone"


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
#    `Restart=no` and nothing else: without the card there is nothing for
#    alsasink to open, so the daemon dies once and stays down instead of being
#    respawned every 5 seconds. Going down and coming back are both the udev
#    rules below.
print("\n📝 Step 5: writing %s" % UNIT_PATH)
with open(UNIT_PATH, "w") as fh:
    fh.write("""[Unit]
Description=GMediaRender UPnP Renderer
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/gmediarender -f "%s" -o gst --gstout-audiosink=alsasink
Restart=no
User=root

[Install]
WantedBy=multi-user.target
""" % FRIENDLY_NAME)
print("✅ Unit written.")

# 5b. The way back: a card appearing starts the service, on the event itself.
print("\n🔌 Step 5b: writing %s" % UDEV_RULE)
with open(UDEV_RULE, "w") as fh:
    fh.write('# The renderer follows the sound card: no polling, no restart loop.\n'
             'SUBSYSTEM=="sound", ACTION=="add", KERNEL=="card*", '
             'ENV{SYSTEMD_WANTS}+="gmediarender.service"\n'
             '# ...and when it leaves, the daemon is rebuilt only if it is holding a\n'
             '# sound device - see the helper. Not stopped and not restarted blindly:\n'
             '# the DAC also comes and goes when the amplifier is switched between its\n'
             '# USB and coaxial inputs, and the renderer must stay in the list.\n'
             'SUBSYSTEM=="sound", ACTION=="remove", KERNEL=="card*", '
             'RUN+="%s"\n' % CARD_GONE_HELPER)
run(["udevadm", "control", "--reload-rules"])
print("✅ udev rule written.")

# 5c. What the remove rule runs. The whole point is the condition: a card
#     leaving is routine - the amplifier re-enumerates its USB input every time
#     the remote switches inputs - and a renderer rebuilt on every such event
#     drops out of the control point's list for ten seconds, which is exactly
#     when somebody is reaching for it. The daemon only needs rebuilding when
#     it is still holding a sound device, because that handle is now dead and
#     the USB isochronous stream runs on at 8000 interrupts/s behind it.
print("\n🧯 Step 5c: writing %s" % CARD_GONE_HELPER)
with open(CARD_GONE_HELPER, "w") as fh:
    fh.write("""#!/bin/sh
# Run from udev when a sound card leaves the bus. Keep it quick: udev kills a
# slow RUN+=.
pid=$(/bin/systemctl show -p MainPID --value gmediarender.service 2>/dev/null)
[ -n "$pid" ] && [ "$pid" != 0 ] || exit 0
for fd in /proc/"$pid"/fd/*; do
    case "$(readlink "$fd" 2>/dev/null)" in
        /dev/snd/*) exec /bin/systemctl --no-block restart gmediarender.service ;;
    esac
done
exit 0
""")
os.chmod(CARD_GONE_HELPER, 0o755)
print("✅ Helper written.")

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
