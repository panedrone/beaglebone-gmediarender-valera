# beaglebone-gmediarender-valera

|                 1. Embedded Board                 |                       2. Media App                        |                          3. Endpoint                          |
|:-------------------------------------------------:|:---------------------------------------------------------:|:-------------------------------------------------------------:|
| ![BeagleBone-Green.png](img/BeagleBone-Green.png) | ![valera-in-foobar2000.png](img/valera-in-foobar2000.png) | ![valera-in-topping-mx3s.png](img/valera-in-topping-mx3s.png) |

## Summary: Engineer's Log (Valera Jr. Bare-Metal Streamer)

An uncompromising audiophile streamer based on BeagleBone, deployed following industrial hardware standards. The
architecture entirely eliminates proprietary shells, redundant software conversions, and marketing crutches (such as USB
transports or esoteric cables).

### Key Steps & Engineering Solutions:

1. **Base Image:** Built on a standard, field-tested **Debian** distribution suitable for BeagleBone boards.
2. **Hardware Binding (Direct Bus/I2S):** The UPnP/DLNA stream is delivered directly to the sound subsystem (ALSA) via
   hardcoded routing (`hw:1,0`), completely bypassing unnecessary software mixers and GStreamer abstraction layers.
3. **Lifting Digital Constraints:** The hardware mixer was pushed to 100% output (`0.00dB`, `Playback 15`) using
   `amixer`, then permanently persisted to non-volatile memory via `alsactl store` to prevent any volume resets upon
   daemon or system reboots.
4. **Uncompromising Power Supply:** Ditching noisy switched-mode power supplies and dirty mains in favor of a pure
   analog source (powerbank). This revealed true micro-dynamics, eliminated jitter, and achieved crystal-clear sound
   staging that outperforms commercial Hi-End streamers.
5. **Architectural Monolith (Optional):** For maximum long-term reliability, the workflow supports a low-level system
   migration from fragile MicroSD cards to the industrial onboard eMMC flash memory.

### 1. Downloading and Flashing the Base Image to a microSD Card

1. Download the latest official Debian image for BeagleBone from
   the [BeagleBoard Latest Images](https://www.google.com/search?q=https://beagleboard.org/latest-images) page. Look for
   an IoT or Flasher image (e.g., `bone-debian-...-iot-armhf.img.xz`).
2. Flash the downloaded image onto a microSD card using [BalenaEtcher](https://etcher.balena.io/) or the `dd` command in
   your terminal:

```bash
sudo dd if=/path/to/debian-image.img of=/dev/sdX bs=4M status=progress conv=fsync
```

*(Replace `/dev/sdX` with your actual SD card drive letter).*

### 2. Booting and Running the System from SD

1. Insert the prepared microSD card into the BeagleBone.
2. Connect power (e.g., via your pure analog power source). The board will boot directly from the SD card.
3. Access the board via SSH:

```bash
ssh debian@beaglebone.local
```

*(Default password is `temppwd` if not changed).*

### 3. (Optional / Industrial Hardcore) Flashing the Image to Internal eMMC

If you want to burn the image directly to the onboard eMMC flash memory and get rid of the MicroSD card dependencies,
follow these hardware and software steps:

**Method A: Using the `enable-beagle-flasher` service (Newer Debian kernels like 5.10+)**

1. Boot the board from your microSD card.
2. Open the `/boot/uEnv.txt` file using a text editor (e.g., `sudo nano /boot/uEnv.txt`).
3. Find the line referring to `beagle-flasher` or the eMMC flasher and uncomment it (remove the `#` at the beginning),
   or add the flasher override depending on the kernel version documentation found in
   the [BeagleBoard eMMC Flashing Guide](https://www.google.com/search?q=https://docs.beagleboard.org/latest/boards/beaglebone/ai/ch06.html).
4. Save the file and reboot the board. The system will automatically flash itself to the eMMC.

**Method B: Hardware Boot Button Trigger (Classic approach)**

1. Power off the board entirely and insert the microSD card.
2. Press and hold the **Boot button (S2)** (located near the SD card slot).
3. Plug in the power cable while keeping the button pressed.
4. Wait until all 4 User LEDs light up solidly, then release the button.
5. The LEDs will start chasing/flashing sequentially, indicating the eMMC is being programmed from the SD card.
6. Wait for the LEDs to turn off or stop flashing entirely (this can take up to 10–15 minutes).
7. Unplug the power, **remove the microSD card** from the slot, and plug the power back in. The board will now boot
   purely from its internal eMMC memory.

## Installation & Deployment

1. **Create the deployment script** on your BeagleBone:

```bash
   nano valera_deploy.py
```

*(Paste the pure Python code into the file and save via Ctrl+O, Enter, Ctrl+X)*

2. **Grant execution permissions:**

```bash
chmod +x valera_deploy.py
```

3. **Execute the automation pipeline:**

```bash
sudo ./valera_deploy.py
```

When the log outputs the final **🎉 GOAL!!!**, the service is locked, loaded, armed in autostart, and waiting for your
media stream.

## foobar2000 Configuration

1. Navigate to `Preferences -> Playback -> Output -> Devices` and choose **BeagleBone Topping**.
2. Set the output bit depth strictly to **32-bit** to ensure clean DSF container passing.
3. Fire up your heavy metal stream and enjoy pure hardware rendering.

## Hardware Maintenance Note

* **24/7 Operation:** This is an industrial embedded setup. Power consumption is < 2W in peak. It is designed to run
  continuously without reboots.
* **Battery DC Power Option:** For an ultra-clean, noise-free DC source, run the hardware from a powerbank. Ensure the
  powerbank features a "low-current/always-on" mode to prevent automated sleep intervals during track changes.
* **Graceful Power Off:** Never pull the live power cord. Press the physical **POWER** button on the BeagleBone board
  for 1-2 seconds. The system will safely unmount filesystems and shut down.


