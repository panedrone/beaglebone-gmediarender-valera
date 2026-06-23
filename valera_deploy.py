#!/usr/bin/env python3
import os
import sys
import subprocess

# Root check - we need privileges to tame the systemd hound
if os.geteuid() != 0:
    print("❌ Error: Script must be run with root privileges! Try: sudo python3 valera_deploy.py")
    sys.exit(1)

print("🚀 Launching Production Deployment: Valera Mladshoy Core Core Core...")
print("📦 Target: BeagleBone Black + Topping DAC Bit-Perfect Streamer")

# 1. Kill and disable the monopoly MPD daemon
print("\n🧹 Step 1: Disabling and stopping greedy MPD service...")
subprocess.run(["systemctl", "stop", "mpd"], stderr=subprocess.DEVNULL)
subprocess.run(["systemctl", "disable", "mpd"], stderr=subprocess.DEVNULL)

# 2. Overwrite ALSA configuration globally
print("\n🎛️ Step 2: Routing ALSA system default to Topping hardware (hw:1,0)...")
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

# 3. Create a clean, native systemd service unit
print("\n⚙️ Step 3: Purging old configuration and injecting native systemd unit...")
service_content = """[Unit]
Description=GMediaRender Daemon (Valera Mladshoy Edition)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/gmediarender -f "BeagleBone Topping" -o gst --gstout-audiosink=alsasink
Restart=always

[Install]
WantedBy=multi-user.target
"""
with open("/lib/systemd/system/gmediarender.service", "w") as f:
    f.write(service_content)

# 4. Trigger systemd reload, enable and ignite the daemon
print("\n🔄 Step 4: Reloading systemd manager and enabling startup symlinks...")
subprocess.run(["systemctl", "daemon-reload"])
subprocess.run(["systemctl", "enable", "gmediarender"])
subprocess.run(["systemctl", "restart", "gmediarender"])

# 5. Execute final health check
print("\n📊 Step 5: Validating deployment health status...")
result = subprocess.run(["systemctl", "is-active", "gmediarender"], capture_output=True, text=True)

if result.stdout.strip() == "active":
    print("\n🎉 GOAL!!! Valera Mladshoy has been successfully put into mass production!")
    print("📡 Device 'BeagleBone Topping' is fully operational and locked on target.")
    print("🎵 Set foobar2000 output to 32-bit and crank up the heavy metal stream!")
else:
    print("\n🤔 Warning: Service injection succeeded, but daemon failed to ignite.")
    print("👉 Check output logs manually via: sudo systemctl status gmediarender")