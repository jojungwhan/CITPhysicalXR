# Control Tower Companion

This small Android app can hold up to eight independent Control Tower site pairings. Its main
screen provides explicit ON and OFF actions for each site's exact saved Matter-plug selection; the
Home-screen widget shows the first two sites. A site can remain local-Wi-Fi-only or provide a private Tailscale HTTPS
origin for control over Wi-Fi or 5G. Each request is signed, sequenced per site, timestamped, and
sent once; the app never talks to a plug directly and never queues a missed command for later.

The primary pairing may also detect a genuine secure-lock to unlocked transition and send one
signed event over that site's local Wi-Fi. Camera sync and unlock automation never use a remote
origin. A separate Home-screen widget opens the companion without issuing a device command.

Each site's settings screen performs a one-time APK install and additive provisioning while the
phone is attached and authorized for Android debugging. Upgrading or pairing another site no
longer clears existing site records. After the screen reports pairing complete, USB is not part of
the plug-control runtime path and can be disconnected.

Updating an existing site requires the same phone identity and pairing secret. To replace a
revoked or rotated identity, remove that site from the phone before pairing it again.

Build locally with the repository's pinned Android toolchain:

```powershell
./gradlew.bat :app:testDebugUnitTest :app:assembleDebug
```

The runtime looks for `app/build/outputs/apk/debug/app-debug.apk` by default. Pairing also enrolls
the phone's current per-network Wi-Fi MAC in Control Tower's application allowlist. The operator
must separately save an exact Matter-plug selection and enable the automation from the PC.
