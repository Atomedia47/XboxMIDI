# XboxMIDI — Ableton Live Remote Script

An Ableton Live **control surface** that turns the MIDI from the XboxMIDI app
into DAW actions plain MIDI mapping can't do: transport, track selection/arming,
and a precise playhead **jog/scrub**. Built for film-style tracking — record a
take, drop to the next track, roll again.

Tested on **Ableton Live 11** (Python 3 `_Framework`).

## Control layout

| Control | Action |
|---|---|
| **A** (note 36) | Play / Stop |
| **B** (note 37) | Record roll (arms Arrangement Record + starts playing) |
| **Left Stick ◄►** (CC 3) | Jog / scrub the playhead — hold, further = faster |
| **D-pad ▲** (note 40) | Select the track above |
| **D-pad ▼** (note 41) | Select the track below |
| **D-pad ◄** (note 42) | Arm the selected track |
| **D-pad ►** (note 43) | Disarm the selected track |

Note/CC numbers match the default `mapping.json` in the app. If you retune the
mapping, update the matching constants at the top of `XboxMIDI/XboxMIDI.py`.

## Install

1. Copy the `XboxMIDI/` folder into your Ableton User Library Remote Scripts dir:

   ```
   ~/Music/Ableton/User Library/Remote Scripts/XboxMIDI/
   ```

2. **Fully quit and reopen** Ableton Live (it scans Remote Scripts only at startup).

3. **Preferences → Link, Tempo & MIDI → Control Surface:** select `XboxMIDI`,
   set **Input** to `XboxMIDI`, **Output** to None. Leave the Track/Sync/Remote
   checkboxes for that port off — the control surface owns it.

4. Launch the XboxMIDI app (so the virtual port + controller feed exist) and work
   in **Arrangement** view.

To reload after editing the script: set the Control Surface to None and back, or
restart Live. Load errors are logged to
`~/Library/Preferences/Ableton/Live 11.x.x/Log.txt`.

## Tuning

Feel is controlled by constants at the top of `XboxMIDI/XboxMIDI.py`:

- `JOG_MAX_BEATS_PER_TICK` — scrub speed at full stick throw.
- `JOG_DEADZONE` — ignore tiny stick drift near center.
