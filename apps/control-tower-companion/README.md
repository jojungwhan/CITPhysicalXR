# Control Tower Companion

This small Android app detects only a genuine secure-lock to unlocked transition and sends one
signed, non-replayable event to the local Control Tower service over Wi-Fi. Its main screen also
has one explicit button that toggles the exact Matter-plug selection saved on the PC. The same
control is available as an Android Home screen widget that performs the signed toggle immediately
without opening the app. A separate Home screen widget opens the companion without issuing a
device command. The app never talks to the Matter plugs directly and it never queues a missed
event for later delivery.

The PC settings screen performs a one-time APK install and provisioning while the dedicated phone
is attached and authorized for Android debugging. After the screen reports pairing complete, USB is
not part of the runtime path and can be disconnected.

Build locally with the repository's pinned Android toolchain:

```powershell
./gradlew.bat :app:testDebugUnitTest :app:assembleDebug
```

The runtime looks for `app/build/outputs/apk/debug/app-debug.apk` by default. Pairing also enrolls
the phone's current per-network Wi-Fi MAC in Control Tower's application allowlist. The operator
must separately save an exact Matter-plug selection and enable the automation from the PC.
