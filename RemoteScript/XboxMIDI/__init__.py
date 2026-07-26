"""XboxMIDI — Ableton Live 11 control surface for the XboxMIDI app.

Reads the MIDI the XboxMIDI menu-bar app sends (from your Xbox controller) and
drives Live's transport, track selection/arming, and a precise playhead jog —
things plain MIDI mapping can't do. See XboxMIDI.py for the control layout.
"""
from __future__ import absolute_import
from .XboxMIDI import XboxMIDI


def create_instance(c_instance):
    return XboxMIDI(c_instance)
