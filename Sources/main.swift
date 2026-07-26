// XboxMIDI — turns an Xbox controller into a MIDI device for Ableton (or any DAW).
//
// Native macOS app. No Python, no extra software, no virtual-port installers.
//   - GameController.framework reads the Xbox controller (Bluetooth or USB)
//   - CoreMIDI publishes a virtual "XboxMIDI" source that Ableton sees automatically
//   - Runs as a menu-bar app (🎮) so it stays out of the way while you play
//
// Mapping is data, not code: edit mapping.json (sits next to the app) to retune
// which button/stick/trigger sends which MIDI note or CC. No rebuild needed.

import Cocoa
import GameController
import CoreMIDI

// MARK: - Mapping config

struct Mapping: Codable {
    var channel: Int          // 1-16
    var velocity: Int         // note-on velocity for buttons (0-127)
    var deadzone: Float       // stick center deadzone (0.0-1.0)
    var buttons: [String: Int] // element name -> MIDI note number
    var axes: [String: Int]    // element name -> MIDI CC number
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

// MARK: - Controller -> MIDI bridge

final class Bridge {
    let midi = MIDIOut()
    var map: Mapping
    private var lastButton: [String: Bool] = [:]
    private var lastCC: [Int: Int] = [:]

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
            guard let note = map.buttons[name] else { continue }
            if lastButton[name] != pressed {
                lastButton[name] = pressed
                pressed ? midi.noteOn(note, map.velocity, map.channel)
                        : midi.noteOff(note, map.channel)
            }
        }

        axis("leftTrigger", gp.leftTrigger.value, bipolar: false)
        axis("rightTrigger", gp.rightTrigger.value, bipolar: false)
        axis("leftStickX", gp.leftThumbstick.xAxis.value, bipolar: true)
        axis("leftStickY", gp.leftThumbstick.yAxis.value, bipolar: true)
        axis("rightStickX", gp.rightThumbstick.xAxis.value, bipolar: true)
        axis("rightStickY", gp.rightThumbstick.yAxis.value, bipolar: true)
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
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate {
    var statusItem: NSStatusItem!
    var statusLine: NSMenuItem!
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
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: "Reload mapping.json", action: #selector(reload), keyEquivalent: "r"))
        menu.addItem(NSMenuItem(title: "Quit XboxMIDI", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        statusItem.menu = menu

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
        statusLine.title = "Mapping reloaded ✓"
    }

    private func attach(_ controller: GCController) {
        guard let gp = controller.extendedGamepad else { return }
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
