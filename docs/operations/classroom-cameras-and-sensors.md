# Classroom cameras, object recognition, and sensors

The tutor uses one **CIT Classroom Control** page. Its **Live cameras and object
recognition** section creates one tile per authenticated local camera publisher;
its **Classroom readings** section creates cards from the latest normalized
`sensor.*`, `telemetry.*`, and `biosignal.*` lesson events.

The camera wall is a bounded latest-frame view, not a surveillance recorder.
Publishers replace an in-memory JPEG or PNG, the browser checks for a newer
frame every 750 ms, and a runtime restart removes every frame. No frame enters
the Fabric event database or semantic recording.

## Current hardware truth

| Source                  | Single-UI presentation                                                            | Physical publisher status                                                                                                               |
| ----------------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Meta Ray-Ban            | Live glasses frames (2 FPS), snapshot fallback, freshness, dimensions, YOLO boxes | Optional Android companion compiles and builds against DAT 0.9.0; real glasses HIL still requires the technician prerequisites below    |
| RoboMaster              | Camera tile and YOLO endpoint accept `robomaster` sources                         | The preserved upstream has SDK and stock-app camera readers, but they are not yet attached to the Fabric media publisher                |
| Tello / RoboMaster TT   | Latest live frame, freshness, dimensions, and optional YOLO boxes                 | Brain2Devices v0.6.35 MJPEG is copied by the independent Tello adapter into ephemeral Fabric memory; Windows firewall/video HIL remains |
| USB or simulator camera | Same tile and analysis path                                                       | Contract-tested publisher path; add the approved camera adapter for the room                                                            |
| LEGO / robot sensors    | Distance, color, reflection, force, IMU, battery, and other scalar cards          | Canonical Pybricks-to-Fabric bridge and exact-name UI setup are implemented; physical hub HIL remains pending                           |
| MindWave Mobile 2       | Vendor-labelled eSense, signal-quality, blink, connection, and health cards       | Independent canonical adapter and simulator are implemented; TGC/headset HIL remains pending; raw EEG is excluded                       |
| Tello telemetry         | Battery, temperature, height, attitude, time-of-flight, and connection cards      | Independent safe adapter and simulator are implemented; physical multi-radio HIL remains pending                                        |

This distinction is deliberate: finding a robot, camera, or sensor never causes
the console to invent a live feed. A tile appears only after an authenticated
publisher registers. A sensor card appears only after a connected node sends a
validated semantic event in the selected lesson.

## Tutor workflow

1. Open **CIT Classroom Control** from the Windows Desktop or Start menu and
   choose **Start classroom devices**. This enables scoped phone-camera access
   and prepares local YOLO while leaving all devices disarmed.
2. Choose **Find devices**. This is passive and does not start a camera or move
   hardware.
3. For Meta glasses, open **Connect a Meta glasses camera**, create the one-use
   code, and enter the displayed classroom address and code in the Android
   companion.
4. For Tello, no separate camera pairing is required: after **Connect grounded
   drones**, the scoped Tello adapter registers its own media source and copies
   the latest local Brain2Devices JPEG. The first physical run may request UAC
   for Brain2Devices' exact-program, local-subnet UDP 11111 firewall rule.
5. On the phone, connect through Meta AI, approve Meta camera access, and choose
   **Share live camera (2 frames/second)**. If the phone reports repeated raw
   frame failures, stop sharing and choose **Use snapshot fallback**. Either mode
   stops when that phone screen is no longer visible.
6. In the camera tile choose **Recognize lamps, drones, and robots**. YOLO runs
   locally on that exact latest frame. It does not run continuously.
7. Review the label, confidence, and box. If a compatible smart plug is assigned
   to an active lesson, use the separate **Turn linked plug on/off** control.

Only the exact `lamp`, `light`, and `smart plug` labels expose the reviewed
outlet control. A `drone` or `robot` result remains advisory and exposes no
power or movement button; use a separately assigned and safety-gated lesson for
those devices.

The default advisory detection floor is 0.20 so the small local model retains
useful drone recall. Confidence remains visible, analysis is tutor-initiated,
and detections never bypass the separate command and safety checks.

Object detection never submits a device command. The tutor's explicit button
still goes through the normal session, role, arbitration, safety, and adapter
checks. In particular, seeing an object cannot automatically energize an outlet,
move a robot, or fly a drone.

## One-time Meta companion installation

This is technician work, not part of a lesson. It reuses the existing CIT
glasses Android application and enables its optional Meta camera source set;
the ordinary G2/Meta agent bridge build remains unchanged.

Requirements:

- Android 12 or newer phone with USB debugging enabled.
- Meta AI and the glasses paired to the same Meta account.
- Meta Wearables developer mode, or application ID/client token from the Meta
  Wearables Developer Center.
- A GitHub token allowed to read Meta's public GitHub Packages artifacts. A
  classic token needs `read:packages`; the token must also be permitted by any
  organization policy that applies to the account.
- `adb`, Java 17, and the Android SDK available on the technician computer.
- Windows Defender Firewall allowed for the CIT/Python runtime on **Private
  networks** only. Do not enable it on Public networks.

From the **CIT Classroom Control** Windows launcher choose **One-time setup:
Meta glasses camera**. The visible technician window verifies package access,
builds the optional companion, finds the authorized USB phone, and installs it.
No tutor needs to type a command.

For scripted technician automation, the equivalent preflight and install are:

```powershell
pnpm hardware:meta-camera:windows -- -Mode Preflight -DeveloperMode
pnpm hardware:meta-camera:windows -- -Mode Install -DeveloperMode
```

Omit `-DeveloperMode` for a registered application. The script then prompts for
the Meta application ID and client token. It also prompts securely for the
GitHub package token when `GITHUB_TOKEN` is not already set. Prompted values are
placed only in the current process environment for Gradle; the script does not
write them to the repository, a settings file, or its output.

The Meta SDK artifacts currently used are `mwdat-core:0.9.0` and
`mwdat-camera:0.9.0`. The optional source has been compile- and APK-build-tested
against those official artifacts. An Android 16 emulator test using the
official `mwdat-mockdevice:0.9.0` also produced and converted an uncompressed
live frame. A physical phone-and-glasses round trip is still required. Re-run
the normal Android build without
`-PcitMetaCamera=true` to verify that the existing Android 8+ companion remains
independent.

## Sensor event shape

Adapters should publish a normalized scalar payload, for example:

```json
{
  "topic": "sensor.distance",
  "sourceNodeId": "lego-spike-01",
  "payload": {
    "value": 180,
    "unit": "mm"
  }
}
```

The console keeps the newest reading per source and topic and shows at most six
scalar values on a card. Media, token, and credential-shaped fields are
suppressed. Raw audio, images, video, and continuous biosignal streams must not
be repackaged as sensor cards.

## Troubleshooting

- **No camera tile:** the publisher has not registered. For Meta, create a new
  one-use pairing code and keep the phone on the same private classroom LAN.
  For Tello, confirm Brain2Devices reports a current video `session_id`, check
  its UDP 11111/firewall diagnostic, and inspect the Tello adapter log.
- **Live video stops after three frame failures:** choose **Use snapshot
  fallback**. The bridge rejects unexpected decoded-frame layouts instead of
  uploading a corrupt image.
- **Waiting:** the source registered but no frame arrived in the last five
  seconds. The last valid image remains visible for diagnosis.
- **Recognition unavailable:** local YOLO preparation failed, commonly because
  the first model download had no internet access. Restart Classroom Control
  once the technician network is available.
- **Meta Maven 401:** the GitHub token does not have usable `read:packages`
  access. No glasses code can be compiled until that external package grant is
  corrected.
- **No LEGO readings:** verify that a real adapter node is registered, the
  lesson is active, and the adapter is publishing `sensor.*` or `telemetry.*`
  events. In **Find devices**, configure the exact advertised name and port map;
  merely pairing the hub is not a reading.
- **No MindWave/Tello readings:** verify that the relevant card says Connected,
  not merely Found, and that the unarmed Device monitoring session is active.
