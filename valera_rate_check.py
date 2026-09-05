#!/usr/bin/env python3
"""Does this host deliver the frames the DAC is asking for?

In asynchronous USB audio the device owns the clock. It reports the rate it
wants through its feedback endpoint and the host is supposed to follow. If the
host does not - because a driver is wrong, not because a CPU is busy - the
DAC's FIFO drains at the difference between the two rates and breaks up on a
schedule. Buffer depth divided by the deficit gives the interval between
audible faults, and that is what a "burble roughly every six seconds" is.

This measures both numbers directly:

    delivered   frames the hardware pointer advanced, per second of wall clock
    asked       what the device reports through `Momentary freq`

The source is /dev/zero, so nothing comes out of the speakers and the amplifier
can be left alone. That matters more than it sounds: the same fault judged by
ear over five minutes produced counts ranging from 0 to 31 a minute, and four
separate conclusions were drawn from that spread and later withdrawn. Forty
five seconds of this gives a number that does not care what anyone expected.

Usage:

    ./valera_rate_check.py                 # 44100, whatever format the DAC takes
    ./valera_rate_check.py -r 96000        # one rate
    ./valera_rate_check.py --sweep         # every rate the DAC advertises
    ./valera_rate_check.py -s 120          # longer run per rate

Read it like this. A ratio of 1.0000 with the device asking for its nominal
rate is a working chain. A ratio near 1 with the device pegged at some other
value - the same number in every sample, never moving - is a feedback loop that
is not closing; the host is sending at its own rate and ignoring the request.
A ratio well below 1 is data that never arrives, and if it is an exact fraction
that does not change with the sample rate, suspect the driver rather than the
hardware: a controller running out of capacity produces scatter and xruns, not
a clean 5/6.
"""

import os
import re
import subprocess
import sys
import time

SETTLE = 3.0          # let the feedback loop converge before timing anything
DEFAULT_SECONDS = 45


def read(path):
    try:
        with open(path) as fh:
            return fh.read()
    except IOError:
        return ""


def find_card():
    """First card with a playback device, by index. There is no onboard codec
    on this board, so the USB DAC is whatever index it lands on - 1 on the
    factory eMMC image, 0 on a current one. Guessing wrong wastes a run."""
    out = read("/proc/asound/cards")
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\s+\[", line)
        if m:
            idx = int(m.group(1))
            if os.path.isdir("/proc/asound/card%d/pcm0p" % idx):
                return idx
    return None


def card_name(card):
    return (read("/proc/asound/card%d/id" % card) or "?").strip()


def stream_info(card):
    """Formats and rates the device advertises, straight from the descriptor
    the kernel parsed. Returns (formats, rates)."""
    text = read("/proc/asound/card%d/stream0" % card)
    formats = re.findall(r"Format:\s*(\S+)", text)
    rates = set()
    for line in re.findall(r"Rates:\s*(.+)", text):
        for r in line.split(","):
            r = r.strip()
            if r.isdigit():
                rates.add(int(r))
    return formats, sorted(rates)


def pick_format(formats):
    """Prefer the widest the device will take. The point is to load the bus the
    way music does, not to be gentle with it."""
    for want in ("S32_LE", "S24_3LE", "S16_LE"):
        if want in formats:
            return want
    return "S16_LE"


def momentary(card):
    m = re.search(r"Momentary freq = (\d+) Hz",
                  read("/proc/asound/card%d/stream0" % card))
    return int(m.group(1)) if m else None


def hw_ptr(card):
    for line in read("/proc/asound/card%d/pcm0p/sub0/status" % card).splitlines():
        if line.startswith("hw_ptr"):
            return int(line.split(":")[1])
    return None


def state(card):
    for line in read("/proc/asound/card%d/pcm0p/sub0/status" % card).splitlines():
        if line.startswith("state"):
            return line.split(":")[1].strip()
    return "?"


def measure(card, fmt, rate, seconds):
    """Play silence at `rate` and count what actually goes out."""
    period = max(rate // 100, 32)          # 10 ms, same geometry alsasink uses
    buf = period * 20                      # 200 ms
    cmd = ["aplay", "-q", "-D", "hw:%d,0" % card, "-f", fmt, "-c", "2",
           "-r", str(rate), "--period-size", str(period),
           "--buffer-size", str(buf), "-t", "raw", "/dev/zero"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE, universal_newlines=True)
    try:
        time.sleep(SETTLE)
        if proc.poll() is not None:
            return None, (proc.stderr.read() or "").strip()
        counts, asked, states = [], [], set()
        prev = hw_ptr(card)
        tick = time.monotonic()
        for _ in range(seconds):
            tick += 1.0
            delay = tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            cur = hw_ptr(card)
            counts.append(cur - prev)
            prev = cur
            states.add(state(card))
            got = momentary(card)
            if got:
                asked.append(got)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        time.sleep(1.0)
    counts.sort()
    return {
        "median": counts[len(counts) // 2],
        "min": counts[0],
        "max": counts[-1],
        "asked": (min(asked), max(asked), len(set(asked))) if asked else None,
        "states": states,
    }, None


def main():
    argv = sys.argv[1:]
    rates, seconds, card, sweep = [], DEFAULT_SECONDS, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-r", "--rate") and i + 1 < len(argv):
            rates.append(int(argv[i + 1])); i += 1
        elif a in ("-s", "--seconds") and i + 1 < len(argv):
            seconds = int(argv[i + 1]); i += 1
        elif a in ("-c", "--card") and i + 1 < len(argv):
            card = int(argv[i + 1]); i += 1
        elif a == "--sweep":
            sweep = True
        elif a in ("-h", "--help"):
            print(__doc__)
            return 0
        i += 1

    if os.geteuid() != 0:
        print("run as root - /proc/asound and hw: access")
        return 1

    if card is None:
        card = find_card()
        if card is None:
            print("no playback card found. Is the DAC plugged in?")
            return 1

    formats, advertised = stream_info(card)
    if not formats:
        print("card %d has no stream0 - not a USB audio device?" % card)
        return 1
    fmt = pick_format(formats)

    if sweep:
        rates = advertised
    elif not rates:
        rates = [44100]

    print()
    print("card %d (%s), format %s" % (card, card_name(card), fmt))
    print("device advertises: %s" % ", ".join(str(r) for r in advertised))
    print("%d s per rate, silence - nothing comes out of the speakers" % seconds)
    print()
    print("%9s %11s %9s %19s %s" % ("rate", "delivered", "ratio", "DAC asked", "verdict"))

    for rate in rates:
        if advertised and rate not in advertised:
            print("%9d  not advertised by this device, skipped" % rate)
            continue
        res, err = measure(card, fmt, rate, seconds)
        if res is None:
            print("%9d  FAILED: %s" % (rate, err))
            continue
        ratio = res["median"] / float(rate)
        if res["asked"]:
            lo, hi, distinct = res["asked"]
            if distinct == 1 and abs(lo - rate) > rate * 0.001:
                ask = "%d PEGGED" % lo
            elif lo == hi:
                ask = "%d" % lo
            else:
                ask = "%d..%d" % (lo, hi)
        else:
            ask = "n/a"
        if res["states"] - {"RUNNING"}:
            verdict = "XRUN " + ",".join(sorted(res["states"] - {"RUNNING"}))
        elif ratio > 0.999:
            verdict = "OK"
        else:
            verdict = "SHORT %.1f%%" % (100.0 * (1 - ratio))
        print("%9d %11d %9.4f %19s %s" % (rate, res["median"], ratio, ask, verdict))

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
