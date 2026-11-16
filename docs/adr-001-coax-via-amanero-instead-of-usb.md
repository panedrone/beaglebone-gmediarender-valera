# ADR-001: Coax through an Amanero-type card instead of the RAW-HA1's USB input

**Date:** 2026-11-16

**Status:** accepted and in use. **Not closed:** (1) the RCA shell continuity check on the card has
not been done; (2) whether the board's VBUS still reaches the card has not been checked; (3) DoP64
has not been played through the card (DSD converted to PCM by go-upnp-player plays, 2026-11-16);
(4) the CM6631A board has not been tried on its own lead from the linear supply, which is what
separates "the supply decides" from "the Amanero board itself" - see *Open check: CM6631A on the
linear supply*.

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
  transport's ground onto a board shared with the class-D amplifier. Rejected by ear. Tried again
  2026-11-16 with Valera on the linear supply: no hum, clean and bright, but thin in the bass. Not
  level-matched; the measurement is [ADR-002](adr-002-input-comparison-by-spl-meter.md).
* **High-speed USB isolator in front of the RAW-HA1's USB input** (ADuM4160 does not qualify, it is
  full-speed only). Would break the ground and keep async and DSD128. Not adopted: it leaves the
  DAC chip on the RAW-HA1's small local oscillators, which the card's AS318B at least feed through
  the receiver PLL's passband. Not tried by ear either.
* **Toslink.** Complete isolation with no capacitance; more jitter. Not adopted.
* **Card powered from USB (VBUS) or from a separate supply.** Brings a second leakage source or the
  board's supply onto the card's ground. Rejected by ear.
* **CM6631A pro board instead of the Amanero-type card** (tried 2026-11-16). C-Media CM6631A,
  asynchronous UAC2, PCM to 192 kHz; coax through a Pulse transformer, Toslink, three oscillators
  (45.1584, 49.152, 12 MHz) each on its own regulator. It has no power input of its own - the
  micro-USB next to the USB-B is a second data input for Android phones (OTG) - so it runs on
  Valera's VBUS. By ear, over coax: plays decently, but without the depth the Amanero-type card has
  on its own lead from the linear supply. Not adopted. Not level-matched
  ([ADR-002](adr-002-input-comparison-by-spl-meter.md)); `valera_rate_check.py` not run on it;
  Toslink not tried.

  The comparison changed two things at once, the board and its supply, so it does not yet say which
  of them gives the depth. That is open item (4).

## Cost

* The asynchronous clock is lost: the DAC chip runs from the RAW-HA1's receiver PLL. The AS318B
  contribute only the slow jitter below the PLL's corner.
* 192 kHz ceiling, and with it DSD128 over DoP. Over the RAW-HA1's USB input it did play: foobar2000
  → Valera → USB, the amplifier's display reading `DoP 5.6448 MHz` and `hw_params` on the board
  352800 Hz ([SMSL-RAW-HA1.md](SMSL-RAW-HA1.md), *DSD without a DSD decoder*). Over coax 352.8 kHz
  does not fit. What still plays through the card:
  * **DoP64** - 176.4 kHz, display `DoP 2.8224 MHz`, bit-exact to the DAC. Needs the renderer at
    volume 100 and no resampling, as any DoP. Fits the link; not played through the card yet.
  * **DSD of any rate converted to PCM** - [go-upnp-player](https://github.com/panedrone/go-upnp-player)
    converts DSF/DFF itself, 24-bit at 176.4 kHz by default
    ([its ADR-028](https://github.com/panedrone/go-upnp-player/blob/master/docs/adr-028-dsd-converted-to-pcm-in-the-player.md)),
    so DSD128 reaches the card as PCM and fits under 192 kHz. foobar2000 does the same with
    foo_input_sacd set to PCM output. Played through the card from go-upnp-player, 2026-11-16.
* Native DSD (the RAW-HA1's `DSD_U32_BE` altset) never went anywhere in this project, and S/PDIF
  cannot carry it at all.

## Open check: RCA shell continuity

If the RCA shell on the card is tied to the card's ground, the coax shield carries the transport's
ground straight into the RAW-HA1, and the transformer isolates the centre conductor only - the decision
would then be working for a different reason than stated here.

Check with a multimeter, card unpowered and disconnected: continuity between the RCA shell and the
USB-B shell / GND on the card.

* **No continuity** - the isolation is as described. Close item (1) in the status line.
* **Continuity** - record the finding here and in the grounding map; isolating the shell (isolated RCA
  socket, or a cut trace) becomes the next decision.

## Open check: CM6631A on the linear supply

Feed the CM6631A from the second 5 V lead of the linear supply through a split USB cable: data and
GND from Valera, VBUS from the supply, Valera's VBUS cut. Easiest without soldering: a cheap USB
cable opened in the middle, only the red wire (VBUS) cut, its CM6631A end joined to the supply's
+5 V in a Wago 221, its Valera end insulated and left unconnected; black, green, white and the shield
untouched. Valera's VBUS must never meet the supply's +5 V - that puts two sources on one rail. The
supply's ground needs no extra wire: it is already common through Valera.

* **The depth appears** - the supply decides: any decent bridge on its own lead of the linear supply
  does the job, and the Amanero-type card is not essential to this chain.
* **It does not** - the difference is in the Amanero-type board itself.

Either way, record the result here and close item (4).
