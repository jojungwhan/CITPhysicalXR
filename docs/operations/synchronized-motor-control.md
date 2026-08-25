# Synchronized motor control

## Prepare and test from the classroom page

1. Connect each BOLT and Ollie from its own device card. Confirm that its exact
   ID is shown as connected.
2. In **Group control**, select **Control connected BOLT and Ollie together**.
   This prepares and arms only the synchronized-control session; it sends no
   movement.
3. Place the robots on the floor with their forward directions aligned. Use the
   shared arrows. Each click sends one bounded nudge to every connected ground
   robot. **Stop** sends an explicit stop to every ground role.
4. Select **Assign connected inputs** when those devices are available. The
   status chips turn active after their exact nodes are assigned.
5. Connect MindWave from its device card, then select the input-connect button
   again. A new blink can start one 10 cm forward/stop/back demonstration. This
   is a discrete vendor event, not an attention measurement.

Supported wearable controls:

- G2 or Meta: use the existing confirmed `CIT robots forward`, `backward`,
  `left`, `right`, or `stop` voice commands.
- Even R1: scroll up for forward, scroll down for backward, and tap for stop.
- MindWave: one blink starts one debounced bounded demonstration.

## Optional Tello movement

Tello is off in the group by default. First complete the flight confirmation
and take off from the ordinary Tello or ordered-fleet controls. Then select
**Include Tello movement**. Shared forward/back/left/right clicks add one
bounded 20 cm command for each independently connected Tello route.

The shared stop button stops ground robots only. Use normal **Land** or the
ordered fleet landing control for an aircraft. Emergency motor stop remains a
separate last-resort action.

## Expected results

- Each output has its own command lifecycle and can fail without cancelling a
  safe sibling command.
- BOLT and Ollie may start a few milliseconds apart and travel slightly
  different distances because their firmware and kinematics differ.
- Removing the group checkbox stops ground robots and closes the synchronized
  session.
- Losing an adapter connection disarms the affected physical session, and each
  Sphero local watchdog stops stale movement.
