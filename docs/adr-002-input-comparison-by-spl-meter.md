# ADR-002: Comparing the RAW-HA1's inputs with test tones and a phone SPL meter

**Date:** 2026-11-16

**Status:** proposed. **Not closed:** neither measurement has been made - (1) coax via the card
against USB direct, (2) coax via the card with the RAW-HA1's USB cable unplugged against plugged in;
both results tables below are empty.

## Context

On one SMSL RAW-HA1, with the same source (Valera) and the same amplifier settings, the two paths
sound different by ear (2026-11-16):

* **USB direct:** clean, bright, no hum, but the bass is there only for show.
* **Through the Amanero-type card over coax:** the bass is there. This is the path in use,
  [ADR-001](adr-001-coax-via-amanero-instead-of-usb.md).

An earlier comparison (2026-11-04, FiiO SR11 on coax against Valera on USB) put the SR11 thinnest.
By ear, by bass: SR11 coax < Valera USB < Valera via the card. So it is not "coax is bassier": the
SR11 is on coax too.

None of these was level-matched. An input that plays a fraction of a dB louder is heard as fuller
in the bass, so by ear alone a difference in bass and a difference in level look the same. And
swapping cables takes long enough for the ear to forget what it heard before (the owner,
2026-11-17).

A second question came up on 2026-11-17, with the idea of a passive USB hub on Valera feeding both
the RAW-HA1's USB input and the card, switched by the amplifier's remote. Valera would not follow
the remote (gmediarender writes to one ALSA card), but the question underneath is about ground:
while a USB cable joins Valera to the RAW-HA1, Valera's ground reaches the amplifier's board
directly and the card's pulse transformer is bypassed, even when the sound goes over coax. If the
bass drops with the USB cable merely plugged in, the ground decides, as
[ADR-001](adr-001-coax-via-amanero-instead-of-usb.md) states.

## Decision

Measure the difference between the inputs per frequency, with sine tones and a phone SPL meter at
the listening seat.

**Tones:** `python cli/gen_test_tones.py` writes them into `test-tones/` (ignored by git): 1000, 100
and 50 Hz, 30 s each, plus one sequence of all three; 44.1 kHz, 24-bit, stereo, -12 dBFS peak.

**Two comparisons:**

1. **Coax via the card against USB direct** - the paths heard differently on 2026-11-16.
2. **Coax via the card, the RAW-HA1's USB cable unplugged against plugged in** - only the ground
   changes; the input stays coax, the sound goes through the card both times. Plugged in means the
   cable from Valera (directly or through a hub) into the RAW-HA1's USB input, input still set to
   coax.

**Procedure, step by step (first time):**

1. **Tones.** Run `python cli/gen_test_tones.py` on the PC. Put
   `sequence_1000-100-50Hz_-12dBFS.wav` where Valera plays from (the player's library). It plays
   1000, 100 and 50 Hz for 10 s each with 2 s of silence between them, so one play gives all three
   readings.
2. **Meter app.** Any free SPL meter app on the phone. In its settings: weighting **C** (not A: A
   cuts 50 Hz by about 30 dB and hides exactly what is looked for), response **Slow**. If the app
   has no C, use Z (flat), and use the same for every reading.
3. **Phone placement.** At the listening seat, at ear height, on a stack of books or a stand,
   microphone (the bottom edge of the phone) towards the speakers. Not in the hand: moving it by a
   few centimetres changes the 50 Hz reading by more than the effect being looked for. It stays in
   that exact place for all the readings of one comparison.
4. **Settings fixed once.** Renderer volume 100, player EQ off. Amplifier volume set so that 1000 Hz
   reads around 75-80 dB, then not touched again until the comparison is over. Tone controls on the
   RAW-HA1 (BASS/TREBLE, EQ) the same on both sides - check whether it keeps them per input.
5. **Reading.** During each 10 s tone, wait 2-3 s for the number to settle, then note the value.
   No one moves or talks in the room during a reading.
6. **Side A** (coax; for comparison 2 - USB cable unplugged): play the sequence, note the three
   values. Play it twice more. Three runs show how much the readings wander by themselves.
7. **Side B** (USB direct; for comparison 2 - USB cable plugged in, input still coax): the same,
   three runs.
8. **Back to A** for one more run. If it differs from the first A runs by more than about 1 dB,
   something moved (the phone, the volume, the noise in the room): start the comparison again.
9. **Compute** per tone: the average of A, the average of B, B minus A. Then the same for the shape
   of the response: (50 Hz minus 1000 Hz) on A against the same on B.

**Reading the result:**

| what the numbers show                                          | what it means                                                                                                                         |
|:---------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------|
| 1000 Hz equal, 50-100 Hz lower on USB                          | a real difference in bass between the inputs. First check whether the RAW-HA1 keeps BASS/EQ per input, before suspecting the path      |
| all three tones lower on USB by the same amount                | a level difference only; the louder input is heard as bassier                                                                         |
| no difference within about 1 dB at any tone                    | the inputs measure the same with sine tones; what is heard is not frequency response (or not something a phone shows)                |

For comparison 2 the same reading applies, with "USB cable plugged in" in place of "USB": the bass
lower with the cable plugged in means the ground through USB takes it away - recorded in ADR-001 as
support for its decision. No difference means the ground through USB does not change the response,
and the depth heard on the card is something a phone does not show.

## Alternatives rejected

* **By ear alone.** The way it has been done so far; cannot tell bass from level, and is not
  repeatable between sessions.
* **Measurement microphone and REW sweeps.** Gives a full response curve, but needs a calibrated
  measurement mic and an interface that is not here. Overkill for one question: is the bass
  different, or the level.
* **Capturing the output electrically.** The RAW-HA1 drives speakers from a class-D stage; taking
  that into a line input needs a load and an attenuator. Not here either.

## Limits

A phone microphone is not flat at 50 Hz, and the room adds its modes at the listening seat. Both are
the same for both inputs, which is why only the difference between inputs is read. A difference
under about 1 dB is within what this method can tell.

## Results

Each cell is the average of three runs; the spread (largest minus smallest of the three) goes in
brackets, e.g. `78.4 (0.6)`.

**1. Coax via the card against USB direct**

| tone    | coax via the card, dB | USB direct, dB | USB minus coax, dB |
|:--------|----------------------:|---------------:|-------------------:|
| 1000 Hz |                       |                |                    |
| 100 Hz  |                       |                |                    |
| 50 Hz   |                       |                |                    |

**2. Coax via the card: RAW-HA1's USB cable unplugged against plugged in**

| tone    | unplugged, dB | plugged in, dB | plugged minus unplugged, dB |
|:--------|--------------:|---------------:|----------------------------:|
| 1000 Hz |               |                |                             |
| 100 Hz  |               |                |                             |
| 50 Hz   |               |                |                             |
