# Even Realities G2 in Classroom Control

## Connect

1. Pair G2 with the Even app on the Android phone and keep Bluetooth and the
   phone's network connection active.
2. Keep Tailscale connected and open the provisioned CIT glasses prototype in
   Even Hub.
3. In Classroom Control, open the Even Realities G2 card and choose **Scan this
   device again**. This is available even when the first classroom scan missed
   G2.
4. Choose **Connect G2**, wear the glasses, and make one voice or button
   interaction. Scan the card again to confirm the live companion check-in.
5. Select **Glasses and coding agents**, assign G2 and a running Codex or Claude
   session, then start the lesson.

To control physical devices instead, select **Glasses device control**, choose
**Physical devices**, and set up the lesson. Choose **Connect G2 / Meta** in
that lesson; this attaches the wearable bridge and available G2 or Meta input
to the exact lesson rather than an older coding-agent or monitoring session.
Assign each intended RoboMaster, Sphero, LEGO, Dash, or Tello fleet controller
to an output role, then complete the safety step and start the lesson. Tello
also requires the separate one-shot flight checklist.

On G2, start voice and say **CIT controls** (or **CIT 장치 제어**). You can also
choose **Open controls on G2** in the paired phone view. Swipe or move the ring
to choose an assigned output, press to open its supported actions, then press
again to review. Press or swipe right once more to confirm. Double-press goes
back; stop and land are sent immediately.

Choose **All assigned devices > Activate all** for the bounded classroom
demonstration. Light-capable robots turn cyan, demo-capable ground robots travel
about 10 cm forward and back, and the assigned Tello fleet requests takeoff.
The action does not arm anything: the lesson and robots must already be armed,
and Tello must already have its separate tutor one-shot arm. **Stop / land**
preempts robot demonstrations and requests fleet landing.

Discovery and connection do not record raw microphone audio. Only the semantic
interaction enters the Fabric.

## Supported behavior

- G2 voice or button input can submit a bounded semantic prompt to the assigned
  Codex or Claude session.
- Normalized coding-agent completion text can appear on G2.
- Configured phone notifications and the existing CIT Telegram-bot feed can
  appear on G2.
- The R1 ring is registered as a separate input-only device even though it uses
  the paired G2 and Even phone path.
- Exact CIT voice phrases publish a structured device-control intent without
  first sending the phrase to Codex or Claude.
- One confirmed ground command fans out to every ground output assigned in the
  lesson. Each adapter independently translates direction and applies its local
  watchdog.

Supported phrases include:

- CIT robots forward, CIT robots backward, CIT robots left, CIT robots right,
  and CIT robots stop
- CIT 로봇 앞으로, CIT 로봇 뒤로, CIT 로봇 왼쪽, CIT 로봇 오른쪽, and CIT 로봇 정지
- CIT drones take off / CIT 드론 이륙
- CIT drones land / CIT 드론 착륙
- CIT controls / CIT 장치 제어
- CIT activate all devices / CIT 모든 장치 실행
- CIT stop all devices / CIT 모든 장치 정지
- CIT robots demo / CIT 로봇 시연
- CIT robots lights / CIT 로봇 조명

Movement and takeoff show a review on G2 and require one more press. Stop and
land are submitted immediately. Every request still passes through the active
lesson, role assignment, arbitration, safety policy, and adapter bounds.

Classroom Control does not currently offer an arbitrary-text composer for a
physical G2. The current Fabric adapter acknowledges display text already
projected by Agent Mesh; it does not pretend that an unrelated Fabric message
was delivered.

## Telegram

G2 does not run the Android or iOS Telegram app. Install Telegram on the paired
phone, send the phone at least one Telegram notification, then open **Even app >
Settings > Notification**, grant Notification Access, and enable Telegram.
Enable Auto Display only if messages should open immediately.

For the optional CIT bot feed, run the existing Agent Mesh Telegram setup on the
Hub host. It creates and pairs a dedicated Bot API inbox, protects the token in
the local Windows secret store, and defaults private bot messages to the phone,
Meta, and G2 destinations. This bot sees only messages sent to that bot or to an
explicitly allowed group/channel; it does not read unrelated personal chats.
