package com.cit.controltower.companion;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class CameraFtpProtocol {
    static final int PORT = 2121;
    private static final String PASSWORD_DOMAIN = "cit-control-tower-camera-ftp-v1";

    private CameraFtpProtocol() {
    }

    static String password(String secret) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.US_ASCII), "HmacSHA256"));
        byte[] digest = mac.doFinal(PASSWORD_DOMAIN.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder().withoutPadding().encodeToString(digest);
    }

    static String uploadId(String name, long size, String sha256) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        digest.update(name.getBytes(StandardCharsets.UTF_8));
        digest.update((byte) 0);
        digest.update(Long.toString(size).getBytes(StandardCharsets.US_ASCII));
        digest.update((byte) 0);
        digest.update(sha256.getBytes(StandardCharsets.US_ASCII));
        return hex(digest.digest());
    }

    static String hex(byte[] values) {
        StringBuilder encoded = new StringBuilder(values.length * 2);
        for (byte value : values) {
            encoded.append(String.format("%02x", value & 0xff));
        }
        return encoded.toString();
    }
}
