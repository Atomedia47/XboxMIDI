# HANDOFF — for Claude running on the MacBook Air

You're picking up **XboxMIDI**, a native macOS menu-bar app that turns an Xbox
controller into a virtual MIDI device for Ableton Live. It was written on a
Windows machine and never compiled — **you are the first real build.** Your job:
build it, get past Gatekeeper, confirm it runs, and help the user map it in Ableton.
Fix any Swift errors you hit; the API targets are GameController + CoreMIDI.

## Architecture (so you can debug fast)
- `Sources/main.swift` — the entire app:
  - `MIDIOut` — CoreMIDI virtual source named "XboxMIDI" (`MIDISourceCreate` +
    `MIDIReceived`). Ableton sees it as a MIDI input.
  - `Bridge` — maps `GCExtendedGamepad` state → MIDI. Buttons → Note On/Off,
    triggers/sticks → CC. Diffs against last state so it only sends on change.
  - `AppDelegate` — menu-bar (`LSUIElement`) app, `.accessory` activation policy,
    `GCController.shouldMonitorBackgroundEvents = true` so input keeps working
    while Ableton is focused. Loads `mapping.json` from the folder next to the app.
- `mapping.json` — user-editable control map (button→note, axis→CC).
- `build.command` — compiles the `.app` with `swiftc` + `-framework` flags.
- `Info.plist` — bundle metadata (min macOS 11).

## Steps to run
1. **Build:** `bash build.command` (or double-click it).
   - If Xcode Command Line Tools are missing it triggers `xcode-select --install`;
     wait for that, then re-run.
   - If `swiftc` errors, read `Sources/main.swift`, fix, rebuild. Likely suspects
     across SDK versions: optional `buttonOptions` / thumbstick-button names on
     `GCExtendedGamepad`, or `MIDIPacketList` send pattern. Keep the public
     behavior identical.
2. **Gatekeeper:** the app is unsigned. First launch: `xattr -dr com.apple.quarantine XboxMIDI.app`
   (or right-click → Open → Open). Explain this to the user.
3. **Verify the MIDI port exists** even before a controller is connected:
   `` `system_profiler SPMIDIDataType 2>/dev/null | grep -i xbox` `` or check
   Audio MIDI Setup → MIDI Studio for "XboxMIDI". Launch the app first.
4. **Controller:** have the user pair the Xbox pad in System Settings → Bluetooth
   (or plug in USB). The 🎮 menu should read "Connected: …".
5. **Ableton:** Settings → Link/MIDI → enable Track + Remote on "XboxMIDI".
   ⌘M, click a control, move the pad, repeat. Confirm notes (buttons) and CC
   (triggers/sticks) actually move Ableton controls.
6. **Report back** what worked. If you changed `main.swift`, commit it:
   `git commit -am "Mac build fixes"` and tell the user to `git push`.

## Notes
- Don't add dependencies or a Python path — staying single-binary native is the
  whole point.
- `mapping.json` and `XboxMIDI.app` must live in the same folder (the app reads
  the mapping from its sibling directory and writes the default there on first run).
- Menu bar has a "Reload mapping.json" item for retuning without relaunch.
