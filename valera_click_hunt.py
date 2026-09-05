#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""valera_click_hunt.py - find what makes the bit-perfect stream click.

SUPERSEDED 2026-09-05. Read this before trusting anything it prints.

The fault this tool was written for turned out to be the kernel: the 2018
factory image mishandles the DAC's asynchronous feedback, delivers 0.33% fewer
frames than the device asks for, and starves its FIFO on a schedule. Nothing
this tool measures could have shown that, and four conclusions drawn with it -
FLAC, the HID interface, the bus bandwidth ceiling, the endpoint reservation -
were all wrong and are documented as withdrawn in the README.

The problem is the method, not the code. Marking clicks by ear gives a
per-minute count that ranged from 0 to 31 on an unchanged system, and a spread
that wide will confirm whatever you already believe. Three of its own
instruments also produced false positives: the tone generator clicked by
itself, the verdict column mislabelled chance as proof on every interrupted
run, and the network class correlated with clicks because the marker keystroke
IS the network traffic.

Use valera_rate_check.py instead. It compares the frames the host delivers
against the rate the device requests, runs on silence, needs no ears, and
answers in forty five seconds. Reach for this tool only for what it is
genuinely good at: attributing a fault you have ALREADY confirmed by
measurement to a specific layer.


Run this ON THE BOARD, as root, WHILE SOUND IS PLAYING - either through
gmediarender or through a bare `speaker-test -D hw:1,0`. It watches three
layers at once and prints one timeline:

  the ALSA ring   - state, buffer fill, avail_max high-water mark
  the USB layer   - host controller interrupt rate, the DAC's feedback value
  the machine     - per-process CPU, kernel log

A full ALSA ring does NOT prove the USB stream is clean: the ring sits above
the URB queue, so a missed isochronous slot clicks without the ring ever
noticing. That is why the USB series matter more than the buffer here.

Press Enter every time you hear a click. The marker lands in the same timeline,
so a click can be matched against what the board was doing at that moment.

    sudo ./valera_click_hunt.py             # 4 minutes, watch whatever plays
    sudo ./valera_click_hunt.py -s 600      # 10 minutes
    sudo ./valera_click_hunt.py --silence   # bisect: drive the DAC ourselves
    sudo ./valera_click_hunt.py --tone      # same, but an audible sine

--silence streams digital zeroes into hw:CARD,0 in S24_3LE - the exact format
and altsetting real playback uses - with no network, no UPnP and no GStreamer
in the path. A click against pure silence cannot come from the audio data, so
if it survives this, everything above ALSA is innocent and the fault is in the
USB layer, the cable or the DAC. --tone is the fallback for a DAC that mutes
on silence; it costs format fidelity (see the note in main). TURN THE
AMPLIFIER DOWN before using either.

Python 3.5 compatible (Debian 9 stretch ships 3.5): no f-strings, no text=.
"""

import os
import re
import sys
import math
import time
import signal
import struct
import threading
import subprocess

SAMPLE = 0.1          # PCM sampling period, seconds
SLOW_WINDOW = 1.0     # CPU / IRQ / feedback accounting window, seconds
DMESG_POLL = 5.0      # kernel log poll, seconds - a fork per poll, keep it rare
CPU_BUSY_TICKS = 12   # a process burning >12% of a core in the window is loud
CORRELATE = 2.0       # a click is "explained" by an event this close, seconds

CLK_TCK = 100
try:
    CLK_TCK = os.sysconf("SC_CLK_TCK")
except (ValueError, AttributeError, OSError):
    pass

XRUN_DEBUG = "/sys/module/snd_pcm/parameters/xrun_debug"
DMESG_RE = re.compile(r"^\[\s*(\d+\.\d+)\]\s*(.*)$")
FREQ_RE = re.compile(r"Momentary freq\s*=\s*(\d+)\s*Hz\s*\(([^)]*)\)")
CONTROLLER_RE = re.compile(r"at\s+usb-(\S+?)-\d")
NOISY_KERNEL = re.compile(
    r"xrun|underrun|overrun|cannot submit|urb|reset .*speed|"
    r"disconnect|usb \d+-\d+|musb|cpsw|mmc|hrtimer|clocksource",
    re.IGNORECASE)


def read_text(path):
    try:
        with open(path, "r") as f:
            return f.read()
    except (IOError, OSError):
        return None


def write_text(path, value):
    try:
        with open(path, "w") as f:
            f.write(value)
        return True
    except (IOError, OSError):
        return False


def run(cmd):
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True)
        return p.stdout
    except Exception:
        return ""


def parse_kv(text):
    out = {}
    if not text:
        return out
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def first_int(value):
    m = re.search(r"-?\d+", value or "")
    return int(m.group(0)) if m else None


def parse_feedback(text):
    """'0x5.8a41' -> samples per microframe as a float.

    USB high-speed async feedback is Q16.16: an integer part and a 16-bit
    fraction. Multiply by 8000 microframes/s to get the rate the DAC is
    actually asking the host to send.
    """
    text = (text or "").strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if "." not in text:
        return None
    whole, frac = text.split(".", 1)
    try:
        value = int(whole, 16)
        if frac:
            value += int(frac, 16) / float(16 ** len(frac))
    except ValueError:
        return None
    return value


def median(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    if n % 2:
        return float(s[n // 2])
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


def find_card(explicit):
    candidates = [explicit] if explicit is not None else list(range(0, 8))
    for idx in candidates:
        if os.path.exists("/proc/asound/card{0}/pcm0p/sub0/status".format(idx)):
            return idx
    return None


def find_usb_irq(card):
    """IRQ line of the host controller this DAC actually hangs off.

    The previous version of this tool watched musb-hdrc.0 - the gadget port,
    which has no cable in it and therefore no interrupts, ever. The name comes
    out of stream0: "TOPPING MX3s at usb-musb-hdrc.1-1, high speed".
    """
    wanted = None
    stream = read_text("/proc/asound/card{0}/stream0".format(card)) or ""
    m = CONTROLLER_RE.search(stream)
    if m:
        wanted = m.group(1)

    best = None
    raw = read_text("/proc/interrupts") or ""
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].rstrip(":").isdigit():
            continue
        device = parts[-1]
        try:
            count = int(parts[1])
        except ValueError:
            continue
        if wanted and device == wanted:
            return parts[0].rstrip(":"), device
        if re.search(r"musb|ehci|xhci|ohci", device, re.IGNORECASE):
            if best is None or count > best[2]:
                best = (parts[0].rstrip(":"), device, count)
    if best:
        return best[0], best[1]
    return None, None


def default_iface():
    raw = read_text("/proc/net/route") or ""
    for line in raw.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "00000000":
            return parts[0]
    return "eth0"


def udp_out():
    """Datagrams sent, from /proc/net/snmp. An SSDP re-advertisement is a burst
    of multicast NOTIFYs, so it shows up here without needing tcpdump."""
    raw = read_text("/proc/net/snmp") or ""
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("Udp:") and i + 1 < len(lines):
            keys = line.split()
            values = lines[i + 1].split()
            if "OutDatagrams" in keys and len(values) == len(keys):
                try:
                    return int(values[keys.index("OutDatagrams")])
                except ValueError:
                    return None
    return None


def net_bytes(iface):
    raw = read_text("/proc/net/dev") or ""
    for line in raw.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        if name.strip() != iface:
            continue
        parts = rest.split()
        if len(parts) >= 9:
            try:
                return int(parts[0]), int(parts[8])
            except ValueError:
                return None
    return None


def irq_count(irq):
    raw = read_text("/proc/interrupts") or ""
    for line in raw.splitlines():
        parts = line.split()
        if parts and parts[0].rstrip(":") == irq:
            try:
                return int(parts[1])
            except (ValueError, IndexError):
                return None
    return None


class Timeline(object):
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def add(self, t, kind, msg):
        with self.lock:
            self.events.append((t, kind, msg))

    def of_kind(self, kind):
        return sorted(t for (t, k, _m) in self.events if k == kind)


class Series(object):
    def __init__(self):
        self.data = {}

    def add(self, name, t, value):
        self.data.setdefault(name, []).append((t, value))

    def get(self, name):
        return self.data.get(name, [])


def marker_thread(timeline, t0, stop):
    while not stop.is_set():
        line = sys.stdin.readline()
        if not line:
            return
        timeline.add(time.monotonic() - t0, "CLICK", "heard by ear")


def dmesg_thread(timeline, t0, boot_offset, stop):
    """Poll the kernel ring buffer and re-base its timestamps onto our clock."""
    seen_upto = boot_offset
    while not stop.is_set():
        out = run(["dmesg"])
        lines = out.splitlines()
        for line in lines:
            m = DMESG_RE.match(line)
            if not m:
                continue
            ktime = float(m.group(1))
            if ktime <= seen_upto:
                continue
            text = m.group(2).strip()
            if NOISY_KERNEL.search(text):
                timeline.add(ktime - boot_offset, "KERNEL", text[:110])
        for line in reversed(lines):
            m = DMESG_RE.match(line)
            if m:
                seen_upto = max(seen_upto, float(m.group(1)))
                break
        stop.wait(DMESG_POLL)


def proc_cpu_snapshot():
    """pid -> (comm, utime+stime in ticks)."""
    snap = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        raw = read_text("/proc/{0}/stat".format(name))
        if not raw or ")" not in raw:
            continue
        head, tail = raw.rsplit(")", 1)
        comm = head.split("(", 1)[-1]
        parts = tail.split()
        if len(parts) < 13:
            continue
        try:
            snap[name] = (comm, int(parts[11]) + int(parts[12]))
        except ValueError:
            continue
    return snap


def periodicity(times):
    if len(times) < 3:
        return None
    deltas = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    mean = sum(deltas) / len(deltas)
    if mean <= 0:
        return None
    var = sum((d - mean) ** 2 for d in deltas) / len(deltas)
    return mean, var ** 0.5, deltas


def correlate(clicks, others):
    hits = 0
    for c in clicks:
        for o in others:
            if abs(o - c) <= CORRELATE:
                hits += 1
                break
    return hits


def coverage(times, duration):
    """Fraction of the run covered by the +-CORRELATE windows around `times`,
    counting overlaps once.

    Without this a chatty event class convicts itself: 68 events at +-2 s blanket
    66% of a 300 s run, so "6 of 6 clicks matched" is what pure chance looks
    like. Hits only mean something measured against that base rate."""
    if not times or duration <= 0:
        return 0.0
    total, end = 0.0, None
    for t in sorted(times):
        a, b = max(0.0, t - CORRELATE), min(duration, t + CORRELATE)
        if b <= a:
            continue
        if end is None or a > end:
            total += b - a
            end = b
        elif b > end:
            total += b - end
            end = b
    return total / duration


def make_sine_s24_3le(path, rate=44100, freq=441, seconds=5, dbfs=-6.0):
    """A sine in the exact format real playback uses, so the test loads the
    USB bus to the byte like music does.

    441 Hz at 44100 is exactly 100 frames per cycle, so the file is one cycle
    repeated - it costs nothing to make and every sample is exact.

    The file is sized to the whole run on purpose. An earlier version played a
    5 s file through `while :; do cat f; done | aplay`, and that harness turned
    out to click about 35 times a minute all by itself - respawning `cat` every
    five seconds jitters the pipe that aplay is reading, and the ALSA ring
    never shows it because the ring stays full the whole time. Playing one file
    with no loop and no pipe dropped that to nothing. A test that manufactures
    discontinuities cannot be used to hunt discontinuities."""
    amp = int((2 ** 23 - 1) * (10.0 ** (dbfs / 20.0)))
    frames_per_cycle = rate // freq
    cycle = bytearray()
    for i in range(frames_per_cycle):
        v = int(amp * math.sin(2.0 * math.pi * i / frames_per_cycle))
        if v < 0:
            v += 1 << 24
        sample = struct.pack("<I", v)[:3]
        cycle += sample + sample          # both channels, identical
    cycles = (rate * seconds) // frames_per_cycle
    with open(path, "wb") as fh:
        fh.write(bytes(cycle) * cycles)
    return path


def main():
    seconds = 240
    card = None
    markers = True
    tone = None
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-s", "--seconds") and i + 1 < len(argv):
            seconds = int(argv[i + 1])
            i += 1
        elif a in ("-c", "--card") and i + 1 < len(argv):
            card = int(argv[i + 1])
            i += 1
        elif a == "--silence":
            tone = "silence"
        elif a == "--tone":
            tone = "sine"
        elif a == "--no-markers":
            markers = False
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        else:
            print("unknown argument: {0}".format(a))
            return 2
        i += 1

    if os.geteuid() != 0:
        print("Run as root: sudo ./valera_click_hunt.py")
        return 1

    card = find_card(card)
    if card is None:
        print("No playback substream under /proc/asound/card*/pcm0p/sub0/status.")
        print("Is the DAC plugged in? Check: aplay -l")
        return 1

    status_path = "/proc/asound/card{0}/pcm0p/sub0/status".format(card)
    hw_path = "/proc/asound/card{0}/pcm0p/sub0/hw_params".format(card)
    stream_path = "/proc/asound/card{0}/stream0".format(card)
    card_id = (read_text("/proc/asound/card{0}/id".format(card)) or "?").strip()

    # These two bisect the chain: no network, no UPnP, no GStreamer, just
    # ALSA -> USB -> DAC. If the click survives, everything above ALSA is
    # innocent.
    #
    # --silence is the sharper instrument. It streams digital zeroes in
    # S24_3LE, which is the exact format and altsetting real playback uses,
    # so the isochronous load matches to the byte - and a click against pure
    # silence cannot possibly come from the audio data.
    #
    # --tone falls back to speaker-test, which in alsa-utils 1.1.3 supports
    # only S8/S16/S32/FLOAT. S24_3LE is not in its list, and the MX3s accepts
    # only S16_LE and S24_3LE, so the intersection is S16_LE - altset 1, 4
    # bytes per frame instead of 6. That is two thirds of the real USB load,
    # so a bandwidth-sensitive click may not reproduce under it.
    tone_proc = None
    if tone:
        if tone == "silence":
            # Match GStreamer's own ALSA geometry, not aplay's defaults.
            # aplay would take 125 ms periods, which feed the DAC in lumps and
            # make its feedback loop hunt - an artefact of the test, not of the
            # fault. 441/8820 is what the real pipeline uses.
            cmd = ["aplay", "-q", "-D", "hw:{0},0".format(card), "-f", "S24_3LE",
                   "-c", "2", "-r", "44100", "--period-size", "441",
                   "--buffer-size", "8820", "-t", "raw", "/dev/zero"]
            what = "digital silence in S24_3LE, 10 ms periods like GStreamer"
        else:
            # speaker-test is NOT used here, deliberately. In alsa-utils 1.1.3
            # it emits only S8/S16/S32/FLOAT; S24_3LE is not in its list, and
            # the MX3s accepts only S16_LE and S24_3LE, so it would drop the
            # test to altset 1 - 4 bytes per frame instead of 6, two thirds of
            # the real isochronous load. A clean run under that proves nothing
            # about a fault that only shows at full bandwidth, which is exactly
            # the fault we are here to exclude.
            #
            # So generate the sine ourselves and push it through the identical
            # aplay geometry --silence uses. Same format, same altset, same
            # bytes per second as music - and, unlike silence, a dropped packet
            # is plainly audible against it. That combination is the point.
            # /dev/shm is 242 MB here and 24-bit stereo at 44.1 kHz costs
            # 264600 B/s, so a run longer than this cannot be held as one
            # file. Refuse rather than quietly fall back to looping.
            budget = 880
            if seconds > budget:
                print("--tone is limited to {0} s (one file must fit in "
                      "/dev/shm); asked for {1}".format(budget, seconds))
                return 1
            sine = make_sine_s24_3le("/dev/shm/valera_sine.raw",
                                     seconds=seconds + 5)
            cmd = ["aplay", "-q", "-D", "hw:{0},0".format(card),
                   "-f", "S24_3LE", "-c", "2", "-r", "44100",
                   "--period-size", "441", "--buffer-size", "8820",
                   "-t", "raw", sine]
            what = "a 441 Hz sine in S24_3LE, -6 dBFS, 10 ms periods"
        print("driving hw:{0},0 with {1} - TURN THE AMPLIFIER DOWN FIRST".format(
            card, what))
        try:
            # Own process group: cheap insurance that nothing is left
            # holding hw:1,0 open after the run.
            tone_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                universal_newlines=True, preexec_fn=os.setsid)
        except OSError as exc:
            print("could not start {0}: {1}".format(cmd[0], exc))
            return 1
        time.sleep(2.0)
        if tone_proc.poll() is not None:
            err = (tone_proc.stderr.read() or "").strip()
            print("{0} died immediately: {1}".format(cmd[0], err or "(no message)"))
            print("If the device is busy: sudo systemctl stop gmediarender")
            return 1

    hw = parse_kv(read_text(hw_path))
    buffer_size = first_int(hw.get("buffer_size", "")) or 0
    period_size = first_int(hw.get("period_size", "")) or 0
    rate = first_int(hw.get("rate", "")) or 0

    irq, irq_name = find_usb_irq(card)

    st0 = read_text(status_path) or ""
    if "closed" in st0 or "state" not in st0:
        print("!! The substream is CLOSED - nothing is playing right now.")
        print("!! Start the sound first, then run this. Continuing anyway.\n")

    governor = (read_text("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
                or "n/a").strip()

    print("=" * 72)
    print("VALERA CLICK HUNT - card {0} ({1}), {2} s".format(card, card_id, seconds))
    print("=" * 72)
    print("  format {0}  rate {1}  period {2}  buffer {3} frames".format(
        hw.get("format", "?"), rate or "?", period_size or "?", buffer_size or "?"))
    if rate and buffer_size:
        print("  buffer depth: {0:.0f} ms   period: {1:.1f} ms".format(
            1000.0 * buffer_size / rate, 1000.0 * period_size / rate))
    print("  cpufreq governor: {0}".format(governor))
    print("  USB host controller: IRQ {0} ({1})".format(irq or "?", irq_name or "?"))
    # Anchor the timeline to seconds-since-boot so it can be lined up against
    # other traces (a GST_DEBUG log, say) that use their own zero.
    print("  started at uptime {0} s - add this to any +Ns below".format(
        (read_text("/proc/uptime") or "?").split()[0]))
    if markers and sys.stdin.isatty():
        print("\n  >>> PRESS ENTER EVERY TIME YOU HEAR A CLICK <<<\n")
    else:
        markers = False
        print("\n  (no tty - click markers disabled)\n")

    prev_xrun_debug = read_text(XRUN_DEBUG)
    if prev_xrun_debug is not None:
        write_text(XRUN_DEBUG, "1")
    else:
        print("  note: no xrun_debug in this kernel (built without CONFIG_SND_DEBUG),")
        print("        so underruns cannot be logged. The buffer series covers it.\n")

    timeline = Timeline()
    series = Series()
    stop = threading.Event()
    t0 = time.monotonic()
    boot_offset = float((read_text("/proc/uptime") or "0").split()[0])

    d = threading.Thread(target=dmesg_thread, args=(timeline, t0, boot_offset, stop))
    d.daemon = True
    d.start()
    if markers:
        m = threading.Thread(target=marker_thread, args=(timeline, t0, stop))
        m.daemon = True
        m.start()

    prev_proc = proc_cpu_snapshot()
    prev_irq_count = irq_count(irq) if irq else None
    iface = default_iface()
    prev_udp = udp_out()
    prev_net = net_bytes(iface)
    prev_hw_ptr = None
    prev_avail_max = None
    prev_state = None
    low_water = None
    next_slow = t0 + SLOW_WINDOW
    tick = t0

    print("running... (Ctrl-C to stop early)\n")
    try:
        while time.monotonic() - t0 < seconds:
            tick += SAMPLE
            delay_to_tick = tick - time.monotonic()
            if delay_to_tick > 0:
                time.sleep(delay_to_tick)
            now = time.monotonic()
            t = now - t0

            raw = read_text(status_path) or ""
            if "closed" in raw:
                if prev_state != "closed":
                    timeline.add(t, "STATE", "substream closed (playback stopped)")
                    prev_state = "closed"
                prev_hw_ptr = None
                prev_avail_max = None
            else:
                s = parse_kv(raw)
                state = s.get("state", "?")
                hw_ptr = first_int(s.get("hw_ptr", ""))
                appl_ptr = first_int(s.get("appl_ptr", ""))
                avail_max = first_int(s.get("avail_max", ""))
                delay_frames = first_int(s.get("delay", ""))

                if state != prev_state:
                    if prev_state is not None:
                        timeline.add(t, "STATE",
                                     "state {0} -> {1}".format(prev_state, state))
                    prev_state = state

                if state == "RUNNING" and hw_ptr is not None:
                    if prev_hw_ptr is not None and hw_ptr == prev_hw_ptr:
                        timeline.add(t, "STALL", "hw_ptr frozen at {0}".format(hw_ptr))
                    prev_hw_ptr = hw_ptr

                    if delay_frames is not None:
                        series.add("delay", t, delay_frames)

                    # avail_max is a monotonic high-water mark of free space. It
                    # cannot be missed by sampling: if it grew, the buffer drained
                    # deeper than ever before somewhere inside that interval.
                    # Its first value is buffer_size - period_size, which is the
                    # normal start-up artefact, not a drain. Hence the baseline.
                    if avail_max is not None and buffer_size:
                        if prev_avail_max is None:
                            prev_avail_max = max(avail_max, buffer_size - period_size)
                        elif avail_max > prev_avail_max:
                            left = 100.0 * (buffer_size - avail_max) / buffer_size
                            timeline.add(t, "DRAIN",
                                         "new low: only {0:.0f}% of the buffer left "
                                         "({1} frames free)".format(left, avail_max))
                            prev_avail_max = avail_max

                    if appl_ptr is not None and buffer_size:
                        pct = 100.0 * (appl_ptr - hw_ptr) / buffer_size
                        if low_water is None or pct < low_water:
                            low_water = pct
                        if pct < 25.0:
                            timeline.add(t, "STARVE",
                                         "buffer down to {0:.0f}%".format(pct))

            if now >= next_slow:
                next_slow += SLOW_WINDOW

                if irq:
                    c = irq_count(irq)
                    if c is not None and prev_irq_count is not None:
                        series.add("usbirq", t, c - prev_irq_count)
                    prev_irq_count = c

                fm = FREQ_RE.search(read_text(stream_path) or "")
                if fm:
                    spm = parse_feedback(fm.group(2))
                    if spm is not None:
                        series.add("feedback", t, spm * 8000.0)

                cur = proc_cpu_snapshot()
                mypid = str(os.getpid())
                for pid in cur:
                    comm, ticks = cur[pid]
                    was = prev_proc.get(pid)
                    if not was or pid == mypid:
                        continue
                    delta = ticks - was[1]
                    if delta > 0:
                        series.add("cpu:{0}:{1}".format(comm, pid), t, delta)
                prev_proc = cur

                u = udp_out()
                if u is not None and prev_udp is not None:
                    series.add("udpout", t, u - prev_udp)
                prev_udp = u

                nb = net_bytes(iface)
                if nb and prev_net:
                    series.add("rx", t, nb[0] - prev_net[0])
                    series.add("tx", t, nb[1] - prev_net[1])
                prev_net = nb
    except KeyboardInterrupt:
        print("\ninterrupted - reporting what we have\n")

    stop.set()
    time.sleep(0.3)
    if prev_xrun_debug is not None:
        write_text(XRUN_DEBUG, prev_xrun_debug.strip() or "0")
    if tone_proc is not None and tone_proc.poll() is None:
        try:
            os.killpg(os.getpgid(tone_proc.pid), signal.SIGTERM)
        except OSError:
            tone_proc.terminate()
        try:
            tone_proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(tone_proc.pid), signal.SIGKILL)
            except OSError:
                tone_proc.kill()
    try:
        os.unlink("/dev/shm/valera_sine.raw")
    except OSError:
        pass

    # How long the run ACTUALLY lasted, not how long it was asked to last.
    # Ctrl-C is the normal way to end this thing, and feeding the requested
    # duration to report() divides every coverage figure by a run that never
    # happened: `expect` comes out that many times too small and every chatty
    # event class is stamped BEYOND CHANCE. A 40 s stop out of a 600 s request
    # deflated it 15-fold and convicted both classes in the report it printed.
    elapsed = max(time.monotonic() - t0, SAMPLE)

    analyse_series(series, timeline, period_size, buffer_size)
    report(timeline, series, low_water, buffer_size, elapsed)
    inventory()
    return 0


def analyse_series(series, timeline, period_size, buffer_size):
    """Turn the numeric series into timeline events, judged against their own
    median rather than a guessed threshold - the healthy rate is whatever this
    board normally does."""
    irq = series.get("usbirq")
    if len(irq) >= 10:
        med = median([v for (_t, v) in irq])
        if med:
            tol = max(0.2 * med, 50.0)
            for t, v in irq:
                if abs(v - med) > tol:
                    timeline.add(t, "USBIRQ",
                                 "host controller {0} irq/s vs {1:.0f} normal "
                                 "({2:+.0f}%)".format(v, med, 100.0 * (v - med) / med))

    fb = series.get("feedback")
    if len(fb) >= 10:
        med = median([v for (_t, v) in fb])
        if med:
            for t, v in fb:
                ppm = 1e6 * (v - med) / med
                if abs(ppm) > 1000.0:
                    timeline.add(t, "FEEDBACK",
                                 "DAC asked for {0:.0f} Hz, {1:+.0f} ppm off its own "
                                 "normal {2:.0f} Hz".format(v, ppm, med))

    # A process that wakes up periodically to do housekeeping - libupnp
    # re-advertising over SSDP, say - never crosses a fixed CPU threshold on
    # a board this slow. It only stands out against its OWN median.
    for name in sorted(series.data):
        if not name.startswith("cpu:"):
            continue
        vals = series.get(name)
        if len(vals) < 20:
            continue
        med = median([v for (_t, v) in vals])
        comm = name.split(":")[1]
        pid = name.split(":")[2]
        for t, v in vals:
            if v >= med + 5 and v >= 2 * max(med, 1.0):
                timeline.add(t, "CPUSPIKE",
                             "{0}[{1}] burned {2:.0f}% of a core, its normal is "
                             "{3:.0f}%".format(comm, pid, 100.0 * v / CLK_TCK,
                                               100.0 * med / CLK_TCK))

    for name, label in (("udpout", "datagrams sent"), ("rx", "bytes in"),
                        ("tx", "bytes out")):
        vals = series.get(name)
        if len(vals) < 20:
            continue
        med = median([v for (_t, v) in vals])
        for t, v in vals:
            if v > max(2.5 * med, med + 20):
                timeline.add(t, "NET",
                             "{0}: {1:.0f} in one second vs {2:.0f} normal".format(
                                 label, v, med))

    delays = series.get("delay")
    if len(delays) >= 20:
        med = median([v for (_t, v) in delays])
        tol = max(float(period_size or 0), 0.05 * (buffer_size or 0), 32.0)
        if med:
            flagged = 0
            for t, v in delays:
                if abs(v - med) > tol:
                    flagged += 1
                    if flagged <= 40:
                        timeline.add(t, "DELAY",
                                     "hardware delay {0} frames vs {1:.0f} normal "
                                     "- the URB queue moved".format(v, med))


def report(timeline, series, low_water, buffer_size, duration):
    events = sorted(timeline.events)
    print()
    print("=" * 72)
    print("TIMELINE")
    print("=" * 72)
    if not events:
        print("  nothing happened at all - no glitch of any kind was recorded.")
    for t, kind, msg in events:
        print("  +{0:7.2f}s  {1:<8} {2}".format(t, kind, msg))

    print()
    print("=" * 72)
    print("STEADINESS")
    print("=" * 72)
    if low_water is not None and buffer_size:
        print("  ALSA ring never fell below {0:.0f}% of {1} frames".format(
            low_water, buffer_size))
    irq = [v for (_t, v) in series.get("usbirq")]
    if irq:
        print("  USB host irq/s: min {0} median {1:.0f} max {2}".format(
            min(irq), median(irq), max(irq)))
    delays = [v for (_t, v) in series.get("delay")]
    if delays:
        print("  hardware delay: min {0} median {1:.0f} max {2} frames".format(
            min(delays), median(delays), max(delays)))
    feedback = [v for (_t, v) in series.get("feedback")]
    if feedback:
        lo, hi, med = min(feedback), max(feedback), median(feedback)
        print("  DAC feedback: {0:.0f} to {1:.0f} Hz, median {2:.0f} "
              "(spread {3:.0f} ppm)".format(lo, hi, med, 1e6 * (hi - lo) / med))
        print("       a healthy async DAC on its own crystal should sit within a")
        print("       few hundred ppm; a spread in the thousands means its FIFO is")
        print("       being fed lumpily, or its clock is not steering the link.")

    tops = []
    for name in series.data:
        if not name.startswith("cpu:"):
            continue
        vals = [v for (_t, v) in series.get(name)]
        if len(vals) >= 20:
            tops.append((median(vals), name.split(":")[1], name.split(":")[2]))
    if tops:
        tops.sort(reverse=True)
        print("  busiest processes (median % of a core):")
        for med, comm, pid in tops[:5]:
            print("    {0:<16} [{1}] {2:.0f}%".format(comm, pid, 100.0 * med / CLK_TCK))
    for name, label in (("udpout", "datagrams sent/s"), ("rx", "bytes in/s"),
                        ("tx", "bytes out/s")):
        vals = [v for (_t, v) in series.get(name)]
        if vals:
            print("  {0:<18} min {1} median {2:.0f} max {3}".format(
                label, min(vals), median(vals), max(vals)))

    print()
    print("=" * 72)
    print("PERIODICITY  (a click 'once a minute' means a period near 60 s)")
    print("=" * 72)
    kinds = []
    for _t, k, _m in events:
        if k not in kinds:
            kinds.append(k)
    if not kinds:
        print("  no events to measure")
    for kind in kinds:
        times = timeline.of_kind(kind)
        p = periodicity(times)
        if not p:
            print("  {0:<8} {1} event(s) - too few to call it periodic".format(
                kind, len(times)))
            continue
        mean, sd, _deltas = p
        flag = ""
        if 20.0 <= mean <= 120.0 and sd < 0.25 * mean:
            flag = "   <== PERIODIC SUSPECT"
        print("  {0:<8} {1} events, every {2:.1f} s (sd {3:.1f} s){4}".format(
            kind, len(times), mean, sd, flag))

    clicks = timeline.of_kind("CLICK")
    print()
    print("=" * 72)
    print("VERDICT")
    print("=" * 72)
    if not clicks:
        print("  No clicks were marked, so nothing could be correlated.")
        print("  Re-run on a tty and hit Enter on every click you hear.")
        return

    ring = (correlate(clicks, timeline.of_kind("DRAIN"))
            + correlate(clicks, timeline.of_kind("STARVE"))
            + correlate(clicks, timeline.of_kind("STALL")))
    usb = (correlate(clicks, timeline.of_kind("USBIRQ"))
           + correlate(clicks, timeline.of_kind("DELAY"))
           + correlate(clicks, timeline.of_kind("FEEDBACK")))
    explained = False
    print("  {0:<9} {1:>5} {2:>8} {3:>6} {4:>8}".format(
        "class", "n", "cover", "hits", "expect"))
    for kind in ("DRAIN", "STARVE", "STALL", "USBIRQ", "DELAY", "FEEDBACK",
                 "CPUSPIKE", "NET", "KERNEL", "STATE"):
        others = timeline.of_kind(kind)
        if not others:
            continue
        hits = correlate(clicks, others)
        expect = coverage(others, duration) * len(clicks)
        verdict = ""
        if hits >= 3 and hits >= 2.0 * expect:
            verdict = "  <== BEYOND CHANCE"
            explained = True
        print("  {0:<9} {1:>5} {2:>7.0f}% {3:>6} {4:>8.1f}{5}".format(
            kind, len(others), 100.0 * coverage(others, duration), hits,
            expect, verdict))
    print()
    if duration < 30:
        print("  !! run was only {0:.0f} s - too short for any of this to mean"
              " much.".format(duration))
    print("  !! NET cannot convict anything while you are pressing Enter over")
    print("     ssh: the keystroke IS the traffic. Ignore NET unless the")
    print("     markers were typed on the console.")
    print("  'expect' is how many of these clicks would land in that class's")
    print("  windows by pure chance. Hits at or below it prove nothing.")

    print()
    if not explained:
        print("  {0} clicks, and nothing in the instrumented path moved with them.".format(
            len(clicks)))
        print("  The ring stayed full, the URB queue stayed steady, no CPU spike.")
        print("  Look outside the board: the power rail, the USB cable/port, or")
        print("  the MX3s acting on its own. Compare against a bare speaker-test.")
    elif ring:
        print("  The stream starved - the pipeline missed its deadline.")
        print("  Fix the load: daemon priority, or whatever CPUSPIKE names.")
    elif usb:
        print("  The ring was full but the USB layer twitched: the click happened")
        print("  BELOW ALSA. Suspect isochronous scheduling on this controller,")
        print("  the cable/port, or the DAC's feedback loop - not the pipeline.")


def inventory():
    """Everything on this board that wakes on a schedule. A 60 s period has to
    come from somewhere, and if it is not here it is not scheduled work."""
    print()
    print("=" * 72)
    print("WHAT ELSE WAKES UP ON THIS BOARD  (candidates for a 60 s period)")
    print("=" * 72)
    print(run(["systemctl", "list-timers", "--all", "--no-pager"]).strip()
          or "  (no systemd timers)")
    print("\n  --- cron ---")
    body = read_text("/etc/crontab")
    if body:
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" not in line.split()[0]:
                print("  /etc/crontab: {0}".format(line))
    if os.path.isdir("/etc/cron.d"):
        for name in sorted(os.listdir("/etc/cron.d")):
            body = read_text(os.path.join("/etc/cron.d", name)) or ""
            for line in body.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("PATH"):
                    print("  /etc/cron.d/{0}: {1}".format(name, line))
    print("  root crontab: {0}".format(
        (run(["crontab", "-l"]).strip() or "(empty)").replace("\n", " | ")))
    print("\n  --- running services ---")
    for line in run(["systemctl", "list-units", "--type=service", "--state=running",
                     "--no-pager", "--no-legend"]).splitlines():
        if line.strip():
            print("  " + line.strip())


if __name__ == "__main__":
    sys.exit(main())
