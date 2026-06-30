#!/usr/bin/env python3
import os
import sys
import subprocess

# 1. Privileges check (Root required to configure system files and daemons)
if os.geteuid() != 0:
    print("❌ Error: Script must be run with root privileges!")
    print("👉 Use: sudo python3 deploy_valera.py")
    sys.exit(1)

print("🚀 Launching Canonical Deployment: Valera Mladshoy (Sarmat Edition)...")
print("📦 Target: BeagleBone Black + Topping DAC Bit-Perfect Streamer\n")

# 2. Complete liquidation of the potential competitor (MPD mixer)
print("🧹 Step 1: Disabling and masking MPD service...")
subprocess.run(["systemctl", "stop", "mpd"], stderr=subprocess.DEVNULL)
subprocess.run(["systemctl", "disable", "mpd"], stderr=subprocess.DEVNULL)

# CRITICAL CORRECTNESS NOTE: We use 'mask' instead of just 'disable'.
# 'disable' only removes symlinks from autostart, but any external trigger
# (like a Node.js script or UPnP network event) can wake MPD up again.
# 'mask' links the service to /dev/null, making it physically unlaunchable by the system.
subprocess.run(["systemctl", "mask", "mpd"], stderr=subprocess.DEVNULL)
print("✅ Competent MPD successfully buried in /dev/null.")

# 3. Global ALSA configuration
print("\n🎛️ Step 2: Routing ALSA system default to hardware device (hw:1,0)...")
asound_content = """pcm.!default {
    type hw
    card 1
    device 0
}

ctl.!default {
    type hw
    card 1
}
"""
with open("/etc/asound.conf", "w") as f:
    f.write(asound_content)
print("✅ ALSA sound parameters fixed in /etc/asound.conf.")

# 4. Cleanup old messy workarounds
print("\n🔥 Step 3: Cleaning up legacy AI-generated systemd overrides...")
old_override_dir = "/etc/systemd/system/gmediarender.service.d"
if os.path.exists(old_override_dir):
    subprocess.run(["rm", "-rf", old_override_dir])
    print("✅ Legacy dirty overrides purged from the disk.")
else:
    print("✅ No hidden overrides found, system is clean.")

# 5. Writing the official configuration file
print("\n📝 Step 4: Writing official configuration to /etc/default/gmediarender...")

# CRITICAL QUOTING AND CORRECTNESS RULES:
# 1. NO SYSTEMD OVERRIDES: We do NOT inject custom ExecStart into systemd units.
#    Instead, we use the official configuration file designated by the package maintainers.
# 2. QUOTE ACCURACY: Notice the DAEMON_ARGS formatting below.
#    - Outer quotes MUST be double quotes: "..."
#    - Inner argument values (like the endpoint name) MUST be wrapped in single quotes: '...'
#    - Mixing this up breaks the SysV/systemd environment parser and crashes the daemon.
config_content = """# /etc/default/gmediarender
# Canonical configuration file for gmediarender

# Allow the init script to start the daemon
ENABLED=1

# Run as root for direct hardware access and proper realtime priorities
USER=root

# EXPLICIT ARGUMENTS ENGINE:
# -f 'Beaglebone Topping' -> The precise friendly name seen by foobar2000 / BubbleUPnP
# -d                      -> Run as a background daemon process
# --gst-audio-sink=...     -> Canonical GStreamer syntax for direct ALSA rendering
DAEMON_ARGS="-f 'Beaglebone Topping' -d --gst-audio-sink=alsasink"
"""

with open("/etc/default/gmediarender", "w") as f:
    f.write(config_content)
print("✅ Canonical environment config successfully updated.")

# 6. Reloading init system and igniting Valera
print("\n🔄 Step 5: Reloading systemd manager and restarting streamer daemon...")
subprocess.run(["systemctl", "daemon-reload"])
subprocess.run(["systemctl", "enable", "gmediarender"], stderr=subprocess.DEVNULL)
subprocess.run(["systemctl", "restart", "gmediarender"])

# 7. Final automated health check
print("\n📊 Step 6: Auditing deployment health status...")
result = subprocess.run(["systemctl", "is-active", "gmediarender"], capture_output=True, text=True)

if result.stdout.strip() == "active":
    print("\n🎉 GOAL!!! Valera Mladshoy successfully deployed to production!")
    print("📡 Device 'Beaglebone Topping' is up, clean, and locked on target.")
    print("🎵 Direct your foobar2000 stream here and enjoy bit-perfect heavy metal!")
else:
    print("\n🤔 Warning: Configuration applied, but daemon failed to ignite.")
    print("👉 Run manually to check logs: sudo systemctl status gmediarender")