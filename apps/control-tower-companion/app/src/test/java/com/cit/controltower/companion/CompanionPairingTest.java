package com.cit.controltower.companion;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertThrows;

import org.junit.Test;

import java.util.List;

public final class CompanionPairingTest {
    private static final String SECRET = "a".repeat(43);

    private static CompanionPreferences.Configuration pairing(
            String deviceId, String secret, String siteId, String origin
    ) {
        return new CompanionPreferences.Configuration(
                "", origin, deviceId, secret, "Phone", siteId, "Classroom"
        );
    }

    @Test
    public void existingSiteCannotBeReplacedByAnUntrustedPairingLink() {
        CompanionPreferences.Configuration current = pairing(
                "android-0123456789abcdef", SECRET, "academy", "https://academy.example.ts.net"
        );
        for (CompanionPreferences.Configuration forged : List.of(
                pairing("android-fedcba9876543210", "b".repeat(43), "academy",
                        "https://other.example.ts.net"),
                pairing(current.deviceId, "b".repeat(43), "academy", current.remoteOrigin),
                pairing(current.deviceId, "b".repeat(43), "different", current.remoteOrigin)
        )) {
            assertThrows(IllegalArgumentException.class,
                    () -> CompanionPreferences.pairingsWith(List.of(current), forged));
        }
    }

    @Test
    public void authenticatedMigrationPreservesIdentityAndOtherSites() {
        CompanionPreferences.Configuration legacy = new CompanionPreferences.Configuration(
                "http://172.30.1.4:8766", "android-0123456789abcdef", SECRET, "Phone"
        );
        CompanionPreferences.Configuration home = pairing(
                "android-fedcba9876543210", "b".repeat(43), "home", "https://home.example.ts.net"
        );
        CompanionPreferences.Configuration migrated = pairing(
                legacy.deviceId, SECRET, "academy", "https://academy.example.ts.net"
        );
        assertEquals(List.of(migrated, home),
                CompanionPreferences.pairingsWith(List.of(legacy, home), migrated));
        assertEquals(List.of(legacy, home),
                CompanionPreferences.pairingsWith(List.of(legacy), home));
        CompanionPreferences.Configuration colliding = pairing(
                legacy.deviceId, SECRET, home.siteId, migrated.remoteOrigin
        );
        assertThrows(IllegalArgumentException.class,
                () -> CompanionPreferences.pairingsWith(List.of(legacy, home), colliding));
    }
}
