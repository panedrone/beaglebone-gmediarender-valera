# beaglebone-gmediarender-valera

### Key Steps & Engineering Solutions:

1. **Base Image & Internal Memory Storage:** Built on a standard, field-tested **Debian** distribution deployed directly
   onto the industrial onboard eMMC flash memory, completely eliminating fragile MicroSD-card dependencies and
   contact-wear jitter.
2. **Hardware Binding (Direct Bus/I2S):** The UPnP/DLNA stream is delivered directly via GStreamer pass-through (
   `-o gst --gstout-audiosink=alsasink`) hardcoded to routing (`hw:1,0`), completely bypassing unnecessary software
   resamplers.
3. **Lifting Digital Constraints:** The endpoint initializes strictly at 100% volume (`--initial-volume=100`) at the
   daemon level to maintain an absolute bit-perfect stream over the network.
4. **Uncompromising Power Supply:** Ditching noisy switched-mode power supplies and dirty mains in favor of a pure
   analog source (powerbank). This revealed true micro-dynamics, eliminated jitter, and achieved crystal-clear sound
   staging that outperforms commercial Hi-End streamers.

|                 1. Embedded Board                 |                       2. Media App                        |                          3. Endpoint                          |
|:-------------------------------------------------:|:---------------------------------------------------------:|:-------------------------------------------------------------:|
| ![BeagleBone-Green.png](img/BeagleBone-Green.png) | ![valera-in-foobar2000.png](img/valera-in-foobar2000.png) | ![valera-in-topping-mx3s.png](img/valera-in-topping-mx3s.png) |

## Summary: Engineer's Log (Valera Jr. Bare-Metal Streamer)

An uncompromising audiophile streamer based on BeagleBone, deployed following industrial hardware standards. The
architecture entirely eliminates proprietary shells, redundant software conversions, and marketing crutches (such as
esoteric cables or uncontrolled sample-rate conversions).

## Accessing the Board

Connect power via your pure analog power source and log into the stable onboard eMMC environment via SSH:

```bash
ssh root@beaglebone.local

```

*(Direct root access is enabled; default password is `temppwd` if not changed).*

## Installation & Deployment

1. **Create the deployment script** on your BeagleBone:

```bash
nano valera_deploy.py

```

*(Paste the updated Python code into the file and save via Ctrl+O, Enter, Ctrl+X)*

2. **Grant execution permissions:**

```bash
chmod +x valera_deploy.py

```

3. **Execute the automation pipeline:**

```bash
sudo ./valera_deploy.py

```

When the log outputs the final **🎉 GOAL!!!**, the service is locked, loaded, armed in autostart (as an override
drop-in), and waiting for your media stream.

## foobar2000 Configuration

1. Navigate to `Preferences -> Playback -> Output -> Devices` and choose **Topping Endpoint**.
2. Set the output bit depth strictly to **32-bit** to ensure clean DSF container passing.
3. Fire up your heavy metal stream and enjoy pure hardware rendering.

## Hardware Maintenance Note

* **24/7 eMMC Operation:** This is an industrial embedded setup using solid internal flash. Power consumption is < 2W in
  peak. It is designed to run continuously without reboots.
* **Battery DC Power Option:** For an ultra-clean, noise-free DC source, run the hardware from a powerbank. Ensure the
  powerbank features a "low-current/always-on" mode to prevent automated sleep intervals during track changes.
* **Graceful Power Off:** Never pull the live power cord. Press the physical **POWER** button on the BeagleBone board
  for 1-2 seconds. The system will safely unmount filesystems from eMMC and shut down.

|            Valera             |                  htop                   | Mercyful Fate in here! an absolute bit-perfect, bare-metal pass-through! |
|:-----------------------------:|:---------------------------------------:|:------------------------------------------------------------------------:|
| ![mascot.png](img/mascot.png) | ![valera-htop.png](img/valera-htop.png) |   ![photo_2026-06-24_23-09-03.jpg](img/photo_2026-06-24_23-09-03.jpg)    |
