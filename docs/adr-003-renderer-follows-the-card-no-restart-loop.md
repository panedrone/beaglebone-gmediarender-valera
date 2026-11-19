# ADR-003: The renderer follows the card instead of respawning on a timer

**Date:** 2026-11-19

**Status:** accepted, deployed and checked on the board (card pulled and returned through
`/sys/bus/usb/devices/1-1/authorized`). **Not closed:** the check with the cable pulled by hand, as
opposed to the USB port being deauthorised in software; both take the card off the bus, but only
the hand test also moves the plug.

## Context

The unit shipped by `valera_deploy.py` carried `Restart=always` with `RestartSec=5`. The board has
no onboard codec, so the USB DAC *is* the card `/etc/asound.conf` points at. Pull its cable and
`alsasink` has nothing to open: gmediarender dies, systemd raises it five seconds later, it dies
again, for as long as the cable is out. The owner noticed it the other way round — the renderer
vanished from go-upnp-player's list the moment the cable came out — and asked what business a
renderer has with the far end of the chain.

It has none. Nothing polls the DAC and nothing watches it: the process simply cannot live without
its ALSA device, and the restart loop was the only thing making noise about it.

Measured on 2026-11-19, with the card off the bus:

| | `Restart=always` | bound to the card |
|---|---|---|
| start attempts, card absent | one every 5 s, forever | none; the service is `inactive`, not `failed` |
| `musb-hdrc.1` interrupts/s | 8000+ while a stream is open | 0 |

The renderer's own USB traffic is not in question: 8076 interrupts/s while playing is the DAC's
125 µs packet interval (`/proc/asound/card1/stream0`), the same for any USB audio device, and it
is 96% of all interrupts on this board. What the loop added was a process dying and being rebuilt
every five seconds next to the audio path.

## Options

1. **Leave the loop.** Rejected: it is pure churn, and it is exactly what the owner asked to be
   rid of.
2. **`Restart=no` alone.** Rejected on its own: the renderer would then stay down until somebody
   logged in, after a cable was moved.
3. **Bind the service to the card's device unit, start it from udev.** Chosen.
4. **Bind to `dev-snd-pcmC1D0p.device`.** Rejected: `/dev/snd/*` nodes carry no systemd tag, so
   that unit exists but stays `inactive` — the service would be bound to something that never
   comes up.

## Decision

`valera_deploy.py` writes:

- `Restart=no` in `[Service]`;
- `BindsTo=` and `After=` the card's device unit in `[Unit]`. The name is not hardcoded: the script
  resolves `/sys/class/sound/card<N>` and runs `systemd-escape -p --suffix=device` on it, the same
  way it already finds the card index rather than assuming one. Where that fails, the binding is
  left out with a warning and only `Restart=no` applies;
- `/etc/udev/rules.d/90-gmediarender.rules`, which puts `SYSTEMD_WANTS=gmediarender.service` on a
  sound card appearing, and reloads the udev rules.

systemd stops the service when the card goes and udev starts it when the card returns. Both are
events; nothing is polled and nothing retries.

## Consequences

- With the DAC unplugged the service is `inactive`, not `failed`, and the board is silent: no
  process churn, no USB interrupts.
- Plug it back in and the renderer returns on the udev event, in about ten seconds, and advertises
  itself again. That is the behaviour the owner already saw by hand on 2026-11-19 before it went
  into the script.
- The device unit's name follows the USB port and the card index. Move the DAC to another port and
  the deploy must be run again — the same condition `/etc/asound.conf` has always had.
- A failure that is not the card's absence (gmediarender crashing on its own) now leaves the
  service down instead of respawning it. That is the intended trade: the restart loop never fixed
  such a failure either, it only hid it.
