#!/usr/bin/env python3
"""Test tones for the level-matched input comparison of ADR-002.

Writes 44.1 kHz, 24-bit, stereo sine tones at -12 dBFS peak into the given folder
(default: test-tones/, which git ignores):

    1000Hz / 0100Hz / 0050Hz _-12dBFS_30s.wav       30 s each, one tone
    sequence_1000-100-50Hz_-12dBFS.wav              10 s per tone, 2 s silence between

Runs on the PC, not on the board: python cli/gen_test_tones.py [folder]
"""
import math
import struct
import sys
import wave
from pathlib import Path

RATE = 44100
LEVEL_DBFS = -12.0
TONE_S = 30
SEQ_TONE_S = 10
FADE_S = 0.05
GAP_S = 2
FREQS = (1000, 100, 50)

AMP = 10 ** (LEVEL_DBFS / 20) * (2 ** 23 - 1)


def tone(freq, seconds):
    # short fade in and out, so neither end clicks
    n = int(RATE * seconds)
    f = int(RATE * FADE_S)
    for i in range(n):
        g = min(1.0, i / f, (n - 1 - i) / f)
        yield int(round(AMP * g * math.sin(2 * math.pi * freq * i / RATE)))


def silence(seconds):
    for _ in range(int(RATE * seconds)):
        yield 0


def write(path, samples):
    buf = bytearray()
    for s in samples:
        b = struct.pack('<i', s)[:3]
        buf += b + b  # the same sample on both channels
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(3)
        w.setframerate(RATE)
        w.writeframes(bytes(buf))
    print(path, len(buf) // 6 / RATE, 's')


def sequence():
    for f in FREQS:
        yield from tone(f, SEQ_TONE_S)
        yield from silence(GAP_S)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else 'test-tones')
    out.mkdir(parents=True, exist_ok=True)
    for f in FREQS:
        write(out / f'{f:04d}Hz_-12dBFS_30s.wav', tone(f, TONE_S))
    write(out / 'sequence_1000-100-50Hz_-12dBFS.wav', sequence())


if __name__ == '__main__':
    main()
