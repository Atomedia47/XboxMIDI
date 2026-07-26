# XboxMIDI

Turn an Xbox controller into a MIDI device for Ableton Live (or any DAW) on a Mac.

- **No Python, no installers, no loopMIDI** — one small native app.
- Ableton sees a MIDI input called **XboxMIDI** automatically.
- Runs as a menu-bar app (🎮). Double-click and it's ready.
- Retune the controls by editing `mapping.json` — no rebuilding.

---

## One-time setup on the MacBook Air

### 1. Get the folder onto the Mac
Copy this whole `XboxMIDI` folder over by USB, **or** clone it from GitHub (see bottom).

### 2. Build the app (once)
Double-click **`build.command`**.

- If macOS says it can't open it because it's from an unidentified developer:
  right-click `build.command` → **Open** → **Open**. (Only needed the first time.)
- If it asks to install **Xcode Command Line Tools**, click **Install**, wait for it
  to finish, then double-click `build.command` again. (Free, Apple-official, one time.)

When it's done, **`XboxMIDI.app`** appears in the folder.
> Keep `XboxMIDI.app` and `mapping.json` in the same folder.

### 3. Pair the controller (once)
Turn the Xbox controller on, hold the pair button, then on the Mac:
**System Settings → Bluetooth** → connect the controller.
(Wired USB works too — just plug it in.)

---

## Everyday use

1. Double-click **`XboxMIDI.app`** → 🎮 appears in the menu bar.
   Click it to see connection status.
2. In Ableton: **Settings → Link, Tempo & MIDI**.
   Under MIDI Ports, find **XboxMIDI** and turn **Track** and **Remote** **On**.
3. Hit **⌘M** (MIDI Map Mode), click a knob/button in Ableton, then move the
   matching control on the controller. Repeat for each control. Hit **⌘M** to finish.

That's it. Next time, just double-click the app.

---

## Retuning the controls (`mapping.json`)

`mapping.json` sits next to the app. Edit it in any text editor, then use the
menu-bar **Reload mapping.json** item (or relaunch the app).

- `channel` — MIDI channel, 1–16
- `velocity` — button note-on velocity, 0–127
- `deadzone` — ignore tiny stick drift near center, 0.0–1.0
- `buttons` — each control → a **MIDI note number**
- `axes` — each control → a **MIDI CC number**

**Buttons:** `a`, `b`, `x`, `y`, `dpadUp`, `dpadDown`, `dpadLeft`, `dpadRight`,
`leftShoulder`, `rightShoulder`, `leftStickButton`, `rightStickButton`,
`menu`, `options`

**Axes:** `leftTrigger`, `rightTrigger`, `leftStickX`, `leftStickY`,
`rightStickX`, `rightStickY`

Sticks send 0–127 with center at 64; triggers send 0–127 from rest to fully pressed.

---

## Troubleshooting

- **Ableton doesn't show XboxMIDI:** launch the app *before* opening Ableton, or
  toggle the MIDI port off/on in Ableton's settings.
- **Controller not detected:** re-check Bluetooth pairing; open the 🎮 menu to
  confirm it says "Connected". Some third-party pads need to be in Xbox mode.
- **Input stops when Ableton is focused:** shouldn't happen (the app monitors in
  the background), but relaunching the app fixes any edge case.

---

## Clone from GitHub (optional)

```bash
git clone <your-repo-url> XboxMIDI
cd XboxMIDI
```
Then follow **One-time setup** above.
