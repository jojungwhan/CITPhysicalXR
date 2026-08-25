# Even R1 smart-ring classroom control

## What this integration does

Even R1 is an input-only Interaction Fabric node. It reuses the supported Even
phone/G2 path, but it has its own device card, connection state, capability, and
lesson role. CIT receives only four semantic gestures: tap, double-tap, scroll
up, and scroll down.

R1 must first be paired to G2 through the Even app. Even documents that one R1
binds to one phone and one G2, and that the phone automatically completes the
R1/G2 relationship after both are connected:

- <https://support.evenrealities.com/hc/en-us/articles/13772377058575-How-to-Pair>
- <https://support.evenrealities.com/hc/en-us/articles/13772400722063-How-to-Control>

## Pair and connect

1. Charge and power G2 and R1.
2. In the Even app, connect G2, add R1, and confirm that R1 controls the glasses.
3. Open the provisioned CIT plugin in Even Hub on the phone.
4. Open **CIT Classroom Control** and choose **Find devices**.
5. On **Even R1 smart ring**, choose **Connect R1 input**.
6. Tap or scroll the ring once. Choose **Find devices** again if the R1 card has
   not changed to Connected.

The first gesture creates the separate R1 node. It is stored durably until the
Agent Mesh adapter acknowledges it, so a bridge refresh does not lose that
gesture.

## Assign outputs in the UI

1. Choose **R1 smart-ring device control**.
2. Assign **Even R1** to **R1 smart-ring input**.
3. Add one or more **Ground robot output** roles. Any connected node that
   consumes `mobility.ground.set_velocity` is compatible, including RoboMaster
   S1, Sphero BOLT, a mobile LEGO hub, and Dash.
4. Optionally assign the Tello fleet controller.
5. Start the lesson and enable each intended physical output. For Tello, also
   complete the grounded-aircraft checklist and arm the one-shot sequence.

| R1 gesture  | Lesson behavior                                               |
| ----------- | ------------------------------------------------------------- |
| Scroll up   | Short `0.12 m/s` forward cue to every assigned ground output  |
| Scroll down | Short `0.12 m/s` backward cue to every assigned ground output |
| Tap         | Zero-velocity cue to every assigned ground output             |
| Double-tap  | Request the separately armed bounded Tello sequence           |

Every ground adapter applies its own bounds and deadman timeout. A gesture does
not arm a device, acquire instructor priority, or bypass a stopped session. R1
events never become coding-agent prompts and never enter an LLM.

For the simpler one-cue experience, use **Simultaneous multi-device cue** and
assign R1 to a fleet input role. Double-tap then sends the same bounded cue to
all assigned outputs.

## Troubleshooting

- **R1 card says Setup needed:** reconnect G2 and R1 in the Even app, keep the
  phone unlocked, and reopen the CIT Even Hub plugin.
- **R1 card says Ready but no R1 node appears:** choose **Connect R1 input**, then
  touch the ring once. The bridge discovers the companion node from that first
  structured event.
- **R1 is Connected but a robot does not move:** verify that the node is assigned
  to a ground-output role, the physical lesson is running, that exact output is
  enabled, and instructor stop is clear.
- **Double-tap does not start Tello:** verify the fleet controller role, grounded
  checklist, one-shot arm, aircraft readiness, and active session. Do not retry
  takeoff until the tutor has checked every aircraft.
- **Bridge diagnostics:** review
  `%LOCALAPPDATA%\CITPhysicalXR\glasses-agent\logs`. Logs contain semantic event
  state, not raw Bluetooth packets or audio.
