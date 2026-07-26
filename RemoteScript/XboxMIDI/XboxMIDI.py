# XboxMIDI control surface for Ableton Live 11.
#
# The XboxMIDI menu-bar app turns your Xbox controller into MIDI on the virtual
# "XboxMIDI" port. This script interprets that MIDI with full access to Live's
# engine, so a controller can do film-style tracking:
#
#   A  (note 36) ............ Play / Stop
#   B  (note 37) ............ Record roll (arms Arrangement Record + starts playing)
#   Left Stick X  (CC 3) .... Jog / scrub the playhead — push left/right, further = faster
#   D-pad Up    (note 40) ... Select the track above (up the list)
#   D-pad Down  (note 41) ... Select the track below (down the list)
#   D-pad Left  (note 42) ... Arm the selected track
#   D-pad Right (note 43) ... Disarm the selected track
#
# These numbers match the default mapping.json in the app. Change both together
# if you retune. Tuning knobs are the constants below.

from __future__ import absolute_import
from _Framework.ControlSurface import ControlSurface
import Live

# --- MIDI assignments (must match mapping.json in the app) ---
CH = 0                     # MIDI channel 1 (app sends channel 1 -> index 0)

NOTE_PLAY       = 36       # A
NOTE_RECORD     = 37       # B
NOTE_TRACK_UP   = 40       # D-pad up    -> select track above
NOTE_TRACK_DOWN = 41       # D-pad down  -> select track below
NOTE_ARM        = 42       # D-pad left  -> arm selected track
NOTE_DISARM     = 43       # D-pad right -> disarm selected track

CC_JOG = 3                 # left stick X

# --- Feel / tuning ---
JOG_MAX_BEATS_PER_TICK = 0.5   # jog speed at full stick throw (update_display runs ~10x/sec)
JOG_DEADZONE = 0.06            # ignore tiny stick drift


class XboxMIDI(ControlSurface):

    def __init__(self, c_instance):
        ControlSurface.__init__(self, c_instance)
        self._jog = 0.0
        with self.component_guard():
            pass
        self.log_message("XboxMIDI: control surface loaded.")
        self.show_message("XboxMIDI controller ready")

    # Ask Live to forward exactly the notes/CCs we use to receive_midi().
    def build_midi_map(self, midi_map_handle):
        script = self._c_instance.handle()
        for note in (NOTE_PLAY, NOTE_RECORD, NOTE_TRACK_UP, NOTE_TRACK_DOWN,
                     NOTE_ARM, NOTE_DISARM):
            Live.MidiMap.forward_midi_note(script, midi_map_handle, CH, note)
        Live.MidiMap.forward_midi_cc(script, midi_map_handle, CH, CC_JOG)

    def receive_midi(self, midi_bytes):
        if len(midi_bytes) != 3:
            return
        status, d1, d2 = midi_bytes[0], midi_bytes[1], midi_bytes[2]
        kind = status & 0xF0
        if kind == 0x90 and d2 > 0:          # note on
            self._on_note(d1)
        elif kind == 0xB0:                    # control change
            self._on_cc(d1, d2)

    def _on_note(self, note):
        song = self.song()
        if note == NOTE_PLAY:
            if song.is_playing:
                song.stop_playing()
            else:
                song.start_playing()
        elif note == NOTE_RECORD:
            song.record_mode = not song.record_mode
            if song.record_mode and not song.is_playing:
                song.start_playing()
        elif note == NOTE_TRACK_UP:
            self._select_track(-1)
        elif note == NOTE_TRACK_DOWN:
            self._select_track(1)
        elif note == NOTE_ARM:
            self._set_arm(True)
        elif note == NOTE_DISARM:
            self._set_arm(False)

    def _on_cc(self, cc, value):
        if cc == CC_JOG:
            deflection = (value - 64) / 64.0          # -1..1, center = 64
            self._jog = 0.0 if abs(deflection) < JOG_DEADZONE else deflection

    # Live calls this ~10x/sec; run the continuous jog here.
    def update_display(self):
        ControlSurface.update_display(self)
        if self._jog != 0.0:
            self._scrub(self._jog * JOG_MAX_BEATS_PER_TICK)

    def _scrub(self, delta_beats):
        song = self.song()
        t = song.current_song_time + delta_beats
        song.current_song_time = t if t > 0.0 else 0.0

    def _select_track(self, direction):
        song = self.song()
        tracks = list(song.tracks)
        if not tracks:
            return
        try:
            idx = tracks.index(song.view.selected_track)
        except ValueError:
            idx = 0
        idx = max(0, min(len(tracks) - 1, idx + direction))
        target = tracks[idx]
        song.view.selected_track = target
        self.show_message("Track: %s" % target.name)

    def _set_arm(self, state):
        track = self.song().view.selected_track
        if track.can_be_armed:
            track.arm = state
            self.show_message("%s: %s" % ("Armed" if state else "Disarmed", track.name))
        else:
            self.show_message("%s can't be armed" % track.name)

    def disconnect(self):
        self.log_message("XboxMIDI: control surface unloaded.")
        ControlSurface.disconnect(self)
