package com.cit.controltower.companion;

import java.nio.charset.StandardCharsets;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class UnlockProtocol {
    private static final String UNLOCK_DOMAIN = "cit-control-tower-unlock-v1";
    private static final String TOGGLE_DOMAIN = "cit-control-tower-toggle-v1";

    private UnlockProtocol() {
    }

    static String canonical(
            String deviceId,
            String eventId,
            long sequence,
            long occurredAtEpochMs
    ) {
        return canonical(UNLOCK_DOMAIN, deviceId, eventId, sequence, occurredAtEpochMs);
    }

    static String toggleCanonical(
            String deviceId,
            String eventId,
            long sequence,
            long occurredAtEpochMs
    ) {
        return canonical(TOGGLE_DOMAIN, deviceId, eventId, sequence, occurredAtEpochMs);
    }

    private static String canonical(
            String domain,
            String deviceId,
            String eventId,
            long sequence,
            long occurredAtEpochMs
    ) {
        return domain + "\n" + deviceId + "\n" + eventId + "\n"
                + sequence + "\n" + occurredAtEpochMs;
    }

    static String signature(
            String secret,
            String deviceId,
            String eventId,
            long sequence,
            long occurredAtEpochMs
    ) throws Exception {
        return signature(
                secret,
                canonical(deviceId, eventId, sequence, occurredAtEpochMs)
        );
    }

    static String toggleSignature(
            String secret,
            String deviceId,
            String eventId,
            long sequence,
            long occurredAtEpochMs
    ) throws Exception {
        return signature(
                secret,
                toggleCanonical(deviceId, eventId, sequence, occurredAtEpochMs)
        );
    }

    private static String signature(String secret, String canonical) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.US_ASCII), "HmacSHA256"));
        byte[] digest = mac.doFinal(canonical.getBytes(StandardCharsets.US_ASCII));
        StringBuilder encoded = new StringBuilder(digest.length * 2);
        for (byte value : digest) {
            encoded.append(String.format("%02x", value & 0xff));
        }
        return encoded.toString();
    }
}
