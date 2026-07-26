// XboxMIDI — turns an Xbox controller into a MIDI + keyboard controller for
// Ableton (or any DAW) on a Mac.
//
// Native macOS app. No Python, no extra software, no virtual-port installers.
//   - GameController.framework reads the Xbox controller (Bluetooth or USB)
//   - CoreMIDI publishes a virtual "XboxMIDI" source that Ableton sees automatically
//   - CoreGraphics can also fire real keystrokes (Space, arrow keys, ⌘S …) so a
//     button can drive things MIDI can't reach — track navigation, scrubbing, save.
//   - Runs as a menu-bar app (🎮) so it stays out of the way while you work.
//
// Mapping is data, not code: edit mapping.json (sits next to the app) to retune
// which button/stick/trigger sends which MIDI note/CC — or which keystroke.
// No rebuild needed; use the menu-bar "Reload mapping.json" item.

import Cocoa
import GameController
import CoreMIDI
import ApplicationServices   // CGEvent (keystrokes) + AX (Accessibility check)

// MARK: - Mapping config

// A keystroke a control can fire, e.g. { "key": "right", "mods": ["cmd"], "repeat": true }.
struct KeyStroke: Codable {
    var key: String            // "space", "left"/"right"/"up"/"down", "s", "f9", "a".."z", "0".."9", …
    var mods: [String]?        // ["cmd"], ["shift"], ["option"], ["ctrl"] (any combination)
    var `repeat`: Bool?        // hold-to-repeat (great for scrubbing); default false = fire once per press
}

struct Mapping: Codable {
    var channel: Int              // 1-16
    var velocity: Int             // note-on velocity for buttons (0-127)
    var deadzone: Float           // stick center deadzone (0.0-1.0)
    var buttons: [String: Int]    // element name -> MIDI note number
    var axes: [String: Int]       // element name -> MIDI CC number
    var keys: [String: KeyStroke]? // element name -> keystroke (takes priority over MIDI for that control)
}

let defaultMapping = Mapping(
    channel: 1,
    velocity: 127,
    deadzone: 0.08,
    buttons: [
        "a": 36, "b": 37, "x": 38, "y": 39,
        "dpadUp": 40, "dpadDown": 41, "dpadLeft": 42, "dpadRight": 43,
        "leftShoulder": 44, "rightShoulder": 45,
        "leftStickButton": 46, "rightStickButton": 47,
        "menu": 48, "options": 49
    ],
    axes: [
        "leftTrigger": 1, "rightTrigger": 2,
        "leftStickX": 3, "leftStickY": 4,
        "rightStickX": 5, "rightStickY": 6
    ],
    // Film-style tracking defaults (Arrangement view). Controls listed here send
    // keystrokes instead of MIDI. Everything else stays MIDI.
    keys: [
        "a":            KeyStroke(key: "space", mods: nil, repeat: nil),          // Play / Stop
        "rightTrigger": KeyStroke(key: "down",  mods: nil, repeat: nil),          // Next track (select track below)
        "leftTrigger":  KeyStroke(key: "up",    mods: nil, repeat: nil),          // Previous track (select track above)
        "dpadRight":    KeyStroke(key: "right", mods: nil, repeat: true),         // Skim forward (hold to scrub)
        "dpadLeft":     KeyStroke(key: "left",  mods: nil, repeat: true),         // Skim back (hold to scrub)
        "menu":         KeyStroke(key: "s",     mods: ["cmd"], repeat: nil)       // Save project (⌘S)
    ]
)

// MARK: - MIDI output (virtual source)

final class MIDIOut {
    private var client = MIDIClientRef()
    private var source = MIDIEndpointRef()

    init() {
        MIDIClientCreate("XboxMIDI" as CFString, nil, nil, &client)
        MIDISourceCreate(client, "XboxMIDI" as CFString, &source)
    }

    private func send(_ bytes: [UInt8]) {
        let bufSize = 1024
        var buffer = Data(count: bufSize)
        buffer.withUnsafeMutableBytes { (raw: UnsafeMutableRawBufferPointer) in
            let list = raw.bindMemory(to: MIDIPacketList.self).baseAddress!
            var packet = MIDIPacketListInit(list)
            packet = MIDIPacketListAdd(list, bufSize, packet, 0, bytes.count, bytes)
            _ = packet
            MIDIReceived(source, list)
        }
    }

    func noteOn(_ note: Int, _ velocity: Int, _ channel: Int) {
        send([UInt8(0x90 | ((channel - 1) & 0x0F)), UInt8(note & 0x7F), UInt8(velocity & 0x7F)])
    }
    func noteOff(_ note: Int, _ channel: Int) {
        send([UInt8(0x80 | ((channel - 1) & 0x0F)), UInt8(note & 0x7F), 0])
    }
    func cc(_ controller: Int, _ value: Int, _ channel: Int) {
        send([UInt8(0xB0 | ((channel - 1) & 0x0F)), UInt8(controller & 0x7F), UInt8(value & 0x7F)])
    }
}

// MARK: - Keyboard output (synthesized keystrokes → whatever app is focused, e.g. Ableton)

final class Keyboard {
    // key name -> US-ANSI virtual key code
    static let codes: [String: CGKeyCode] = [
        "a":0,"s":1,"d":2,"f":3,"h":4,"g":5,"z":6,"x":7,"c":8,"v":9,"b":11,"q":12,
        "w":13,"e":14,"r":15,"y":16,"t":17,"1":18,"2":19,"3":20,"4":21,"6":22,"5":23,
        "=":24,"9":25,"7":26,"-":27,"8":28,"0":29,"]":30,"o":31,"u":32,"[":33,"i":34,
        "p":35,"return":36,"enter":36,"l":37,"j":38,"'":39,"k":40,";":41,"\\":42,
        ",":43,"/":44,"n":45,"m":46,".":47,"tab":48,"space":49,"`":50,
        "delete":51,"backspace":51,"escape":53,"esc":53,
        "f5":96,"f6":97,"f7":98,"f3":99,"f8":100,"f9":101,"f11":103,"f10":109,"f12":111,
        "f1":122,"f2":120,"f4":118,
        "home":115,"pageup":116,"forwarddelete":117,"end":119,"pagedown":121,
        "left":123,"right":124,"down":125,"up":126
    ]

    private static func flags(_ mods: [String]) -> CGEventFlags {
        var f: CGEventFlags = []
        for m in mods {
            switch m.lowercased() {
            case "cmd", "command", "⌘":            f.insert(.maskCommand)
            case "shift", "⇧":                     f.insert(.maskShift)
            case "opt", "option", "alt", "⌥":      f.insert(.maskAlternate)
            case "ctrl", "control", "⌃":           f.insert(.maskControl)
            default: NSLog("XboxMIDI: unknown modifier '\(m)'")
            }
        }
        return f
    }

    func post(_ ks: KeyStroke) {
        guard let code = Keyboard.codes[ks.key.lowercased()] else {
            NSLog("XboxMIDI: unknown key '\(ks.key)' — see README for valid key names")
            return
        }
        let f = Keyboard.flags(ks.mods ?? [])
        let src = CGEventSource(stateID: .combinedSessionState)
        if let down = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: true) {
            down.flags = f
            down.post(tap: .cghidEventTap)
        }
        if let up = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: false) {
            up.flags = f
            up.post(tap: .cghidEventTap)
        }
    }

    // Do we have Accessibility permission (required to send keystrokes to other apps)?
    var trusted: Bool { AXIsProcessTrusted() }

    // Ask macOS to show the "grant Accessibility" prompt if we don't have it yet.
    @discardableResult
    func promptForTrust() -> Bool {
        let key = kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String
        return AXIsProcessTrustedWithOptions([key: true] as CFDictionary)
    }
}

// MARK: - Controller -> MIDI / keyboard bridge

final class Bridge {
    let midi = MIDIOut()
    let kbd = Keyboard()
    var map: Mapping
    private var lastButton: [String: Bool] = [:]
    private var lastCC: [Int: Int] = [:]
    private var keyDown: [String: Bool] = [:]
    private var repeaters: [String: Timer] = [:]

    init(_ map: Mapping) { self.map = map }

    func handle(_ gp: GCExtendedGamepad) {
        let buttons: [(String, Bool)] = [
            ("a", gp.buttonA.isPressed),
            ("b", gp.buttonB.isPressed),
            ("x", gp.buttonX.isPressed),
            ("y", gp.buttonY.isPressed),
            ("dpadUp", gp.dpad.up.isPressed),
            ("dpadDown", gp.dpad.down.isPressed),
            ("dpadLeft", gp.dpad.left.isPressed),
            ("dpadRight", gp.dpad.right.isPressed),
            ("leftShoulder", gp.leftShoulder.isPressed),
            ("rightShoulder", gp.rightShoulder.isPressed),
            ("leftStickButton", gp.leftThumbstickButton?.isPressed ?? false),
            ("rightStickButton", gp.rightThumbstickButton?.isPressed ?? false),
            ("menu", gp.buttonMenu.isPressed),
            ("options", gp.buttonOptions?.isPressed ?? false)
        ]
        for (name, pressed) in buttons {
            if fireKey(name, pressed) { continue }   // keystroke-mapped: it owns this control
            guard let note = map.buttons[name] else { continue }
            if lastButton[name] != pressed {
                lastButton[name] = pressed
                pressed ? midi.noteOn(note, map.velocity, map.channel)
                        : midi.noteOff(note, map.channel)
            }
        }

        // Triggers can be a keystroke (treated as a button via a threshold) or a CC.
        trigger("leftTrigger", gp.leftTrigger.value)
        trigger("rightTrigger", gp.rightTrigger.value)

        axis("leftStickX", gp.leftThumbstick.xAxis.value, bipolar: true)
        axis("leftStickY", gp.leftThumbstick.yAxis.value, bipolar: true)
        axis("rightStickX", gp.rightThumbstick.xAxis.value, bipolar: true)
        axis("rightStickY", gp.rightThumbstick.yAxis.value, bipolar: true)
    }

    private func trigger(_ name: String, _ value: Float) {
        if map.keys?[name] != nil {
            _ = fireKey(name, value >= 0.5)   // half-pull = "pressed"
            return
        }
        axis(name, value, bipolar: false)
    }

    private func axis(_ name: String, _ raw: Float, bipolar: Bool) {
        guard let cc = map.axes[name] else { return }
        var v = raw
        if bipolar {
            if abs(v) < map.deadzone { v = 0 }
            v = (v + 1) / 2                 // -1..1 -> 0..1, center = 0.5
        } else {
            if v < map.deadzone { v = 0 }
        }
        let value = max(0, min(127, Int((v * 127).rounded())))
        if lastCC[cc] != value {
            lastCC[cc] = value
            midi.cc(cc, value, map.channel)
        }
    }

    // Returns true if this control is keystroke-mapped (so the caller skips MIDI for it).
    @discardableResult
    private func fireKey(_ name: String, _ pressed: Bool) -> Bool {
        guard let ks = map.keys?[name] else { return false }
        if keyDown[name] == pressed { return true }   // no edge change; still "owned" by keys
        keyDown[name] = pressed
        if pressed {
            kbd.post(ks)
            if ks.repeat == true {
                let t = Timer(timeInterval: 0.11, repeats: true) { [weak self] _ in self?.kbd.post(ks) }
                RunLoop.main.add(t, forMode: .common)
                repeaters[name] = t
            }
        } else {
            repeaters[name]?.invalidate()
            repeaters[name] = nil
        }
        return true
    }

    // True if any control is mapped to a keystroke (i.e. we need Accessibility).
    var usesKeystrokes: Bool { !(map.keys?.isEmpty ?? true) }
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    var statusLine: NSMenuItem!
    var keyLine: NSMenuItem!
    var bridge: Bridge!

    func applicationDidFinishLaunching(_ note: Notification) {
        bridge = Bridge(loadMapping())

        // Menu-bar item
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.title = "🎮"
        let menu = NSMenu()
        statusLine = NSMenuItem(title: "Waiting for controller…", action: nil, keyEquivalent: "")
        statusLine.isEnabled = false
        menu.addItem(statusLine)
        menu.addItem(NSMenuItem(title: "MIDI port: XboxMIDI", action: nil, keyEquivalent: ""))
        keyLine = NSMenuItem(title: "Keyboard control: …", action: nil, keyEquivalent: "")
        keyLine.isEnabled = false
        menu.addItem(keyLine)
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Enable Keyboard Control (Accessibility)…",
                                action: #selector(openAccessibility), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: "Reload mapping.json", action: #selector(reload), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Quit XboxMIDI", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        statusItem.menu = menu

        // If the mapping uses keystrokes, make sure we have Accessibility permission.
        if bridge.usesKeystrokes { bridge.kbd.promptForTrust() }
        refreshKeyStatus()

        // Receive controller input even when Ableton is the focused app.
        GCController.shouldMonitorBackgroundEvents = true

        NotificationCenter.default.addObserver(self, selector: #selector(connected(_:)),
                                               name: .GCControllerDidConnect, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(disconnected(_:)),
                                               name: .GCControllerDidDisconnect, object: nil)
        GCController.controllers().forEach { attach($0) }
    }

    @objc func connected(_ n: Notification) {
        if let c = n.object as? GCController { attach(c) }
    }
    @objc func disconnected(_ n: Notification) {
        statusLine.title = "Controller disconnected"
    }
    @objc func reload() {
        bridge.map = loadMapping()
        if bridge.usesKeystrokes { bridge.kbd.promptForTrust() }
        refreshKeyStatus()
        statusLine.title = "Mapping reloaded ✓"
    }
    @objc func openAccessibility() {
        bridge.kbd.promptForTrust()
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
            NSWorkspace.shared.open(url)
        }
    }

    private func refreshKeyStatus() {
        if !bridge.usesKeystrokes {
            keyLine.title = "Keyboard control: off (MIDI only)"
        } else if bridge.kbd.trusted {
            keyLine.title = "Keyboard control: enabled ✓"
        } else {
            keyLine.title = "Keyboard control: ⚠︎ needs Accessibility permission"
        }
    }

    private func attach(_ controller: GCController) {
        guard let gp = controller.extendedGamepad else { return }
        controller.handlerQueue = .main   // keep keystroke timers on the main run loop
        statusLine.title = "Connected: \(controller.vendorName ?? "Controller") ✓"
        gp.valueChangedHandler = { [weak self] gamepad, _ in
            self?.bridge.handle(gamepad)
        }
    }

    // mapping.json lives next to the .app so it's easy to edit; created on first run.
    private func loadMapping() -> Mapping {
        let appDir = (Bundle.main.bundlePath as NSString).deletingLastPathComponent
        let path = appDir + "/mapping.json"
        let fm = FileManager.default
        if let data = fm.contents(atPath: path),
           let m = try? JSONDecoder().decode(Mapping.self, from: data) {
            return m
        }
        // Write the default beside the app so the user can retune it later.
        if let data = try? JSONEncoder().encodePretty(defaultMapping) {
            try? data.write(to: URL(fileURLWithPath: path))
        }
        return defaultMapping
    }
}

extension JSONEncoder {
    func encodePretty<T: Encodable>(_ value: T) throws -> Data {
        outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encode(value)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory) // menu-bar app, no Dock icon
app.run()
