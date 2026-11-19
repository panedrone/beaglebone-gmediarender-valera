# ADR-003: The renderer follows the card instead of respawning on a timer

**Date:** 2026-11-19

**Status:** accepted and deployed, **amended twice the same day**: the `BindsTo=` half was
withdrawn after it took the renderer down (see *Withdrawn: the binding to the device unit*), and a
second udev rule was added after the premise "the daemon dies with its card" was caught being false
(see *Amendment: the card leaving stops the service*). What stands is `Restart=no` plus two udev
rules, add and remove, the remove one conditional (`/usr/local/sbin/gmediarender-card-gone`): the
daemon is rebuilt only when it is the process holding the sound device. Deployed and checked on
the board 2026-11-19: a card coming and going no longer touches an idle renderer, it advertises
with no sound card at all, and switching the amplifier away while Valera was playing rebuilt it
once, in ten seconds, and left the bus at 0 interrupts/s. **Not closed:** the same with a *stale*
handle — a stream run out by itself, nobody playing — and anything checked with the cable pulled by
hand rather than the port deauthorised.

## Context

The unit shipped by `valera_deploy.py` carried `Restart=always` with `RestartSec=5`. The board has
no onboard codec, so the USB DAC *is* the card `/etc/asound.conf` points at. Pull its cable and
`alsasink` has nothing to open: gmediarender dies, systemd raises it five seconds later, it dies
again, for as long as the cable is out. The owner noticed it the other way round — the renderer
vanished from go-upnp-player's list the moment the cable came out — and asked what business a
renderer has with the far end of the chain.

It has none. Nothing polls the DAC and nothing watches it: ~~the process simply cannot live without
its ALSA device~~ (wrong — see the amendment below, 2026-11-19), and the restart loop was the only
thing making noise about it.

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
- ~~`BindsTo=` and `After=` the card's device unit in `[Unit]`, its name escaped from
  `/sys/class/sound/card<N>` with `systemd-escape -p --suffix=device`~~ — withdrawn 2026-11-19,
  see below;
- `/etc/udev/rules.d/90-gmediarender.rules`, which puts `SYSTEMD_WANTS=gmediarender.service` on a
  sound card appearing, and reloads the udev rules.

The daemon dies with the card, once, and udev starts it again when a card appears. Both are
events; nothing is polled and nothing retries.

## Withdrawn: the binding to the device unit (2026-11-19)

Within the hour of the deploy the owner moved the cables — from the RAW-HA1's direct USB
connection to the Amanero card (ADR-001) — and the renderer was gone from the network and from
go-upnp-player's list. The board was up, on the same address, and `gmediarender` read `inactive`:

```
systemd[1]: Dependency failed for GMediaRender UPnP Renderer.
systemd[1]: gmediarender.service: Job gmediarender.service/start failed with result 'dependency'.
```

The device unit's name carries the **USB interface** number, not just the port: the RAW-HA1's audio
interface is `1-1:1.0`, the Amanero's is `1-1:1.1`. So the unit was bound to a device that no
longer existed, udev's start was refused by the dependency, and the failure was silent — nothing
in the player's log but a refused connection.

The binding is therefore gone. It bought one cosmetic thing, `inactive` instead of a dead process,
and cost the renderer on every change of DAC — and this box has two audio paths the owner switches
between by hand. `Restart=no` already ends the respawning, and the udev rule already brings the
service back; neither knows or cares which card appeared.

Noted for the record: the check made when the binding went in — card off the bus, card back —
passed without it. Stopping came from the process dying on the missing device and starting from the
udev rule, so the test could not tell the binding apart from its absence.

## Amendment: the card leaving stops the service (2026-11-19)

Later the same day, the board was looked at again on the owner's ask — what is making a mess in
there. It was making one: an SMSL DAC had been plugged, played, and unplugged, and three hours
later, with nothing playing and load average 0.00, `musb-hdrc.1` was still taking **8177
interrupts a second** — 96% of every interrupt on the board.

What held it open:

```
/proc/asound/card1/pcm0p/sub0/status
state: DISCONNECTED
owner_pid: 392          # gmediarender, started at boot, never restarted
/proc/392/fd/80 -> /dev/snd/pcmC1D0p
```

`systemctl restart gmediarender` → `closed`, and the rate went to **0**.

So the premise of this ADR was half wrong. The daemon dies with its card only while the card is
*playing*: `alsasink` gets a fatal error on the next write. When gmediarender has left the PCM open
after a stream ran out on its own — the defect measured the same day in the player's ADR-031 — the
disconnect kills nothing. The process sits in `sleep`, holding a handle to a device that is gone,
and the kernel keeps feeding the isochronous endpoint at the DAC's 125 µs interval, for as long as
the service is up. `Restart=no` does not help: nothing restarted. The add rule does not help
either: `SYSTEMD_WANTS` on a unit that is already `active` is a no-op, so plugging a DAC back in
left the stale handle in place and the renderer talking to the wrong device.

A second udev rule therefore fires on the card's removal, and what it runs decides whether the
daemon needs rebuilding at all:

```
SUBSYSTEM=="sound", ACTION=="remove", KERNEL=="card*", RUN+="/usr/local/sbin/gmediarender-card-gone"
```

```sh
pid=$(/bin/systemctl show -p MainPID --value gmediarender.service 2>/dev/null)
[ -n "$pid" ] && [ "$pid" != 0 ] || exit 0
for fd in /proc/"$pid"/fd/*; do
    case "$(readlink "$fd" 2>/dev/null)" in
        /dev/snd/*) exec /bin/systemctl --no-block restart gmediarender.service ;;
    esac
done
```

Still events and nothing polled: the card goes, and the service is rebuilt **only if it is the one
holding a sound device**, because that handle is now dead. `RUN+=` and not a device-unit binding,
because the binding is what was withdrawn above.

The condition is the whole point, and it was learned the hard way twice in ten minutes:

* **`stop` was wrong.** It is the tidy reading of "the renderer follows the card", and the owner
  switched the amplifier to the FiiO SR11 on coaxial — which takes the USB DAC off the bus — and
  Valera was gone from the control point's list. A renderer that disappears whenever the amp is
  listening elsewhere is no use; gmediarender does not need a card to be a renderer.
* **Unconditional `restart` was wrong too.** Switching the amplifier's input back to USB
  re-enumerates the DAC — `usb 1-1: USB disconnect` and a fresh device number 21 s later, measured
  in `dmesg` — so the rule rebuilt the daemon exactly when the owner was reaching for Valera in
  the list, and libupnp needs ten seconds to bind and say "Ready for rendering". The renderer was
  missing precisely at the moment it was wanted.

Checked on the board 2026-11-19, with the port deauthorised
(`echo 0 > /sys/bus/usb/devices/1-1/authorized`) rather than by hand:

| | result |
|---|---|
| card leaves, nothing held | PID unchanged, `active`, SSDP still on `*:1900` — the renderer never leaves the list |
| card returns | PID still unchanged, PCM `closed`, `aplay -l` sees it, 0 interrupts/s |
| with no card at all | `active`, "Ready for rendering", advertising; it cannot play, since `/etc/asound.conf` names a card that is not there |
| `remove` event with the PCM open | fires anyway: `remove .../sound/card1` arrived while `state: RUNNING` |
| the fd scan against a real holder | `holds /dev/snd/pcmC1D0p` → verdict yes |

The last two are the halves of the stuck-handle case. Its live form turned up on its own within the
hour: with Valera *playing*, the owner switched the amplifier to coaxial and on to the FiiO. The
card left with gmediarender holding it, the helper fired once — `Stopping` 14:32:03, `Ready for
rendering` 14:32:13 — and the board settled at `--- no soundcards ---`, service `active`, 0
interrupts/s. The renderer was out of the list for those ten seconds, which is what a rebuild
costs and why it is conditional. What is still not staged is the *stale* handle, where the stream
has run out by itself and gmediarender holds a device nobody is playing to.

Rejected alternatives: a timer that notices a dead handle (polling, which is the thing this ADR
exists to remove), and `Restart=always` back again (it never released the handle either — the
process was alive, so there was nothing to restart).

## Consequences

- With the DAC unplugged the service is `inactive`, not `failed`, and the board is silent: no
  process churn, no USB interrupts.
- Plug it back in and the renderer returns on the udev event, in about ten seconds, and advertises
  itself again. That is the behaviour the owner already saw by hand on 2026-11-19 before it went
  into the script.
- Changing the DAC still needs the deploy run again, because `/etc/asound.conf` names the card
  index — the condition this box has always had. Nothing else depends on which card it is.
- A failure that is not the card's absence (gmediarender crashing on its own) now leaves the
  service down instead of respawning it. That is the intended trade: the restart loop never fixed
  such a failure either, it only hid it.
