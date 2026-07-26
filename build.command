#!/bin/bash
# Double-click this once on the MacBook Air to build XboxMIDI.app.
# After the app exists, you never need this again — just double-click the app.

cd "$(dirname "$0")" || exit 1

APP="XboxMIDI.app"
echo "Building $APP ..."

# One-time requirement: Xcode Command Line Tools (free, Apple-official).
if ! xcode-select -p >/dev/null 2>&1; then
  echo
  echo "  >> Xcode Command Line Tools are needed (one time)."
  echo "  >> A system dialog will pop up — click Install, wait for it to finish,"
  echo "  >> then double-click this build.command again."
  xcode-select --install
  exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

cp Info.plist "$APP/Contents/Info.plist"

swiftc -O Sources/main.swift \
  -framework Cocoa -framework GameController -framework CoreMIDI \
  -o "$APP/Contents/MacOS/XboxMIDI"

if [ $? -ne 0 ]; then
  echo "Build failed. Copy the error above and send it over."
  exit 1
fi

# Create the editable mapping next to the app if it isn't there yet.
[ -f mapping.json ] || cp mapping.json "mapping.json"

echo
echo "Done. XboxMIDI.app is in this folder."
echo "Keep XboxMIDI.app and mapping.json together, then double-click the app."
