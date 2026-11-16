# ADR-001: Coax through an Amanero-type card instead of the RAW-HA1's USB input

**Date:** 2026-11-16

**Status:** accepted and in use. **Not closed:** (1) the RCA shell continuity check on the card has
not been done; (2) whether the board's VBUS still reaches the card has not been checked.

How the chain is wired now is in
[audio_transport_power_grounding_map.md](audio_transport_power_grounding_map.md); this record is about
the choice only.

## Context

Fed directly over USB, the SMSL RAW-HA1 does not play acceptably, although everything measurable on
the USB side is correct: on `5.10.240-bone80` `valera_rate_check.py` shows ratio `1.0000`, the DAC asks
its nominal rate, `hw_params` shows no resampling (see [SMSL-RAW-HA1.md](SMSL-RAW-HA1.md)). The data
arrive bit-exact; the sound does not.

Inside the RAW-HA1 the USB bridge sits on the main board and shares its ground with the power
converters for the logic rails, a Bluetooth module, HDMI and the class-D amplifier. The USB input
bonds the transport's ground - and with it the board's power supply and Ethernet - straight onto that
ground, with no isolation.

The DAC's clock is generated on that same board whichever input is used. No input fixes it.

## Decision

The board feeds an Amanero-type USB card (a Combo384 clone with Accusilicon AS318B oscillators); the
card feeds the RAW-HA1 over coaxial S/PDIF through its pulse transformer. **The board and the card are
powered from the same linear supply** (LHY Audio 15W/5V). Only this combination plays; the board on a
switching supply or on a PC USB port kills the sound.

What decides it is the ground, not the clocks: the transformer breaks the transport's DC connection
to the RAW-HA1, and the common linear supply leaves one small source of 50 Hz leakage instead of a
switching supply's Y-capacitor. The two work only together - the transformer passes common-mode
current at HF through its inter-winding capacitance.

## Alternatives rejected

* **RAW-HA1 USB input directly.** Keeps the asynchronous clock, 768 kHz and DSD128 over DoP; bonds the
  transport's ground onto a board shared with the class-D amplifier. Rejected by ear.
* **High-speed USB isolator in front of the RAW-HA1's USB input** (ADuM4160 does not qualify, it is
  full-speed only). Would break the ground and keep async and DSD128. Not adopted: it leaves the
  DAC chip on the RAW-HA1's small local oscillators, which the card's AS318B at least feed through
  the receiver PLL's passband. Not tried by ear either.
* **Toslink.** Complete isolation with no capacitance; more jitter. Not adopted.
* **Card powered from USB (VBUS) or from a separate supply.** Brings a second leakage source or the
  board's supply onto the card's ground. Rejected by ear.

## Cost

* The asynchronous clock is lost: the DAC chip runs from the RAW-HA1's receiver PLL. The AS318B
  contribute only the slow jitter below the PLL's corner.
* 192 kHz ceiling: DoP stops at DSD64; DSD128 over DoP (352.8 kHz) no longer plays.

## Open check: RCA shell continuity

If the RCA shell on the card is tied to the card's ground, the coax shield carries the transport's
ground straight into the RAW-HA1, and the transformer isolates the centre conductor only - the decision
would then be working for a different reason than stated here.

Check with a multimeter, card unpowered and disconnected: continuity between the RCA shell and the
USB-B shell / GND on the card.

* **No continuity** - the isolation is as described. Close item (1) in the status line.
* **Continuity** - record the finding here and in the grounding map; isolating the shell (isolated RCA
  socket, or a cut trace) becomes the next decision.
