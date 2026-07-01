#!/usr/bin/env python3
import os
import sys
import subprocess

# 1. Privileges check (Root required to configure system files and daemons)
if os.geteuid() != 0:
    print("❌ Error: Script must be run with root privileges!")
    print("👉 Use: sudo python3 valera_deploy.py")
    sys.exit(1)

print("🚀 Launching Canonical Deployment: Valera Mladshoy (Sarmat Edition)...")
print("📦 Target: BeagleBone Green + Topping DAC Bit-Perfect Streamer\n")

# 2. Complete liquidation of the potential competitor (MPD mixer)
print("🧹 Step 1: Disabling and masking MPD service...")
subprocess.run(["systemctl", "stop", "mpd"], stderr=subprocess.DEVNULL)
subprocess.run(["systemctl", "disable", "mpd"], stderr=subprocess.DEVNULL)

# 'mask' links the service to /dev/null, making it physically unlaunchable by the system.
# 'disable' only removes symlinks from autostart, but any external trigger
# (like a Node.js script or UPnP network event) can wake MPD up again.
subprocess.run(["systemctl", "mask", "mpd"], stderr=subprocess.DEVNULL)
print("✅ MPD successfully buried in /dev/null.")

# 3. Global ALSA configuration
print("\n🎛️  Step 2: Routing ALSA system default to hardware device (hw:1,0)...")
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
print("✅ ALSA routing fixed in /etc/asound.conf.")

# 4. Cleanup old overrides
print("\n🔥 Step 3: Cleaning up legacy systemd overrides...")
old_override_dir = "/etc/systemd/system/gmediarender.service.d"
if os.path.exists(old_override_dir):
    subprocess.run(["rm", "-rf", old_override_dir])
    print("✅ Legacy overrides purged.")
else:
    print("✅ No legacy overrides found.")

# 5. Writing canonical systemd unit
print("\n📝 Step 4: Writing canonical systemd unit to /lib/systemd/system/gmediarender.service...")

unit_content = """[Unit]
Description=GMediaRender UPnP Renderer
After=network.target alsa-utils.service

[Service]
Type=simple
ExecStart=/usr/bin/gmediarender -f "BeagleBone Topping" -o gst --gstout-audiosink=alsasink
Restart=always
RestartSec=5
User=root
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""

with open("/lib/systemd/system/gmediarender.service", "w") as f:
    f.write(unit_content)
print("✅ Canonical systemd unit written.")

# 6. Reloading init system and igniting Valera
print("\n🔄 Step 5: Reloading systemd and restarting streamer daemon...")
subprocess.run(["systemctl", "daemon-reload"])
subprocess.run(["systemctl", "enable", "gmediarender.service"], stderr=subprocess.DEVNULL)
subprocess.run(["systemctl", "restart", "gmediarender"])

# 7. Final automated health check
print("\n📊 Step 6: Auditing deployment health status...")
result = subprocess.run(["systemctl", "is-active", "gmediarender"], capture_output=True, text=True)

if result.stdout.strip() == "active":
    print("\n🎉 GOAL!!! Valera Mladshoy successfully deployed to production!")
    print("📡 Device 'BeagleBone Topping' is up, clean, and locked on target.")
    print("🎵 Direct your foobar2000 stream here and enjoy bit-perfect heavy metal!")
else:
    print("\n🤔 Warning: Configuration applied, but daemon failed to ignite.")
    print("👉 Run manually to check logs: sudo systemctl status gmediarender")
