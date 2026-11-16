# ADR-002: Comparing the RAW-HA1's inputs with test tones and a phone SPL meter

**Date:** 2026-11-16

**Status:** proposed. **Not closed:** the measurement has not been made; the results table below is
empty.

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
in the bass, so by ear alone a difference in bass and a difference in level look the same.

## Decision

Measure the difference between the inputs per frequency, with sine tones and a phone SPL meter at
the listening seat.

**Tones:** `python cli/gen_test_tones.py` writes them into `test-tones/` (ignored by git): 1000, 100
and 50 Hz, 30 s each, plus one sequence of all three; 44.1 kHz, 24-bit, stereo, -12 dBFS peak.

**Procedure:**

1. Phone in one fixed place at the listening seat, the same for every reading. C weighting if the
   app has it (A weighting all but removes 50 Hz), slow response.
2. Amplifier volume set once and not touched again. Renderer at 100, player EQ off, the same player
   and the same files for both inputs.
3. Play the three tones through the card (coax), read the level of each.
4. Switch the source to USB, play the same three tones, read again.
5. Compare the difference between the inputs per tone, not the absolute numbers.

**Reading the result:**

| what the numbers show                                          | what it means                                                                                                                         |
|:---------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------|
| 1000 Hz equal, 50-100 Hz lower on USB                          | a real difference in bass between the inputs. First check whether the RAW-HA1 keeps BASS/EQ per input, before suspecting the path      |
| all three tones lower on USB by the same amount                | a level difference only; the louder input is heard as bassier                                                                         |
| no difference within about 1 dB at any tone                    | the inputs measure the same with sine tones; what is heard is not frequency response (or not something a phone shows)                |

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

| tone    | coax via the card, dB | USB direct, dB | USB minus coax, dB |
|:--------|----------------------:|---------------:|-------------------:|
| 1000 Hz |                       |                |                    |
| 100 Hz  |                       |                |                    |
| 50 Hz   |                       |                |                    |
