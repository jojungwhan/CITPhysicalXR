package com.cit.controltower.companion;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class UnlockProtocolTest {
    @Test
    public void canonicalPayloadAndSignatureMatchServerContract() throws Exception {
        String secret = "test-secret-abcdefghijklmnopqrstuvwxyz-0123456789";
        String canonical = UnlockProtocol.canonical(
                "android-0123456789abcdef",
                "7f7ec0b5-bc68-45b8-b683-ffbbb87cce0f",
                42L,
                1789016400000L
        );

        assertEquals(
                "cit-control-tower-unlock-v1\nandroid-0123456789abcdef\n"
                        + "7f7ec0b5-bc68-45b8-b683-ffbbb87cce0f\n42\n1789016400000",
                canonical
        );
        assertEquals(
                "0ed1d9676f72c88628b5078d138e84432c1abb8a286243cffcfb388a8810b5c8",
                UnlockProtocol.signature(
                        secret,
                        "android-0123456789abcdef",
                        "7f7ec0b5-bc68-45b8-b683-ffbbb87cce0f",
                        42L,
                        1789016400000L
                )
        );
    }

    @Test
    public void toggleSignatureUsesAnIndependentDomain() throws Exception {
        String secret = "test-secret-abcdefghijklmnopqrstuvwxyz-0123456789";
        String canonical = UnlockProtocol.toggleCanonical(
                "android-0123456789abcdef",
                "7f7ec0b5-bc68-45b8-b683-ffbbb87cce0f",
                42L,
                1789016400000L
        );

        assertEquals(
                "cit-control-tower-toggle-v1\nandroid-0123456789abcdef\n"
                        + "7f7ec0b5-bc68-45b8-b683-ffbbb87cce0f\n42\n1789016400000",
                canonical
        );
        assertEquals(
                "d90a86c14a580dae307484e2992cf4ff4bf5eb151a0d5e4619e025045c34456c",
                UnlockProtocol.toggleSignature(
                        secret,
                        "android-0123456789abcdef",
                        "7f7ec0b5-bc68-45b8-b683-ffbbb87cce0f",
                        42L,
                        1789016400000L
                )
        );
    }

    @Test
    public void remoteStateAndExplicitPowerUseIndependentDomains() throws Exception {
        String secret = "test-secret-abcdefghijklmnopqrstuvwxyz-0123456789";
        String deviceId = "android-0123456789abcdef";
        String eventId = "7f7ec0b5-bc68-45b8-b683-ffbbb87cce0f";

        assertEquals(
                "cit-control-tower-remote-state-v1\nandroid-0123456789abcdef\n"
                        + "7f7ec0b5-bc68-45b8-b683-ffbbb87cce0f\n42\n1789016400000",
                UnlockProtocol.remoteStateCanonical(
                        deviceId,
                        eventId,
                        42L,
                        1789016400000L
                )
        );
        assertEquals(
                "bc456242584bb3e67c9c49ef67810505b286b21545f6056f366ed0a57de69588",
                UnlockProtocol.remoteStateSignature(
                        secret,
                        deviceId,
                        eventId,
                        42L,
                        1789016400000L
                )
        );
        assertEquals(
                "4f5e03b353a8159fa56d7ec51f9a6f5bab045f7ba9d6766fb37f06fb6953486e",
                UnlockProtocol.remotePowerSignature(
                        secret,
                        deviceId,
                        eventId,
                        42L,
                        1789016400000L,
                        true
                )
        );
        assertEquals(
                "2ec7b586d8c41152d6725963d5f649f41c3ae7fd59a8e1ef1935628652c6e514",
                UnlockProtocol.remotePowerSignature(
                        secret,
                        deviceId,
                        eventId,
                        42L,
                        1789016400000L,
                        false
                )
        );
    }

    @Test
    public void cameraFtpCredentialsMatchTheServerContract() throws Exception {
        assertEquals(
                "WVuXwQziPrwfha8vLZ2hwrn5Hb1lr46FoC4XO_XFeHw",
                CameraFtpProtocol.password("A".repeat(43))
        );
        assertEquals(
                "f6c770699f6a82deaa95e9fbae230bad7d4fe30195d4dede16f004d124c50019",
                CameraFtpProtocol.uploadId(
                        "DSC00001.JPG",
                        1234L,
                        "a".repeat(64)
                )
        );
    }
}
