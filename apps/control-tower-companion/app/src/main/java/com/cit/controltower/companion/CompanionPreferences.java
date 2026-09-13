package com.cit.controltower.companion;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.SharedPreferences;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.regex.Pattern;

final class CompanionPreferences {
    private static final String FILE = "control_tower_companion";
    private static final String ORIGIN = "origin";
    private static final String DEVICE_ID = "device_id";
    private static final String SECRET = "secret";
    private static final String DISPLAY_NAME = "display_name";
    private static final String LOCAL_ENABLED = "local_enabled";
    private static final String SEQUENCE = "sequence";
    private static final String LAST_STATUS = "last_status";
    private static final Pattern DEVICE = Pattern.compile("android-[a-f0-9]{16}");
    private static final Pattern SECRET_VALUE = Pattern.compile("[A-Za-z0-9_-]{43,128}");

    private CompanionPreferences() {
    }

    static Configuration load(Context context) {
        SharedPreferences values = values(context);
        return new Configuration(
                values.getString(ORIGIN, ""),
                values.getString(DEVICE_ID, ""),
                values.getString(SECRET, ""),
                values.getString(DISPLAY_NAME, "Control Tower")
        );
    }

    static void savePairing(Context context, Configuration configuration) {
        if (!configuration.isValid()) {
            throw new IllegalArgumentException("Invalid Control Tower pairing");
        }
        values(context).edit()
                .putString(ORIGIN, configuration.origin)
                .putString(DEVICE_ID, configuration.deviceId)
                .putString(SECRET, configuration.secret)
                .putString(DISPLAY_NAME, configuration.displayName)
                .putBoolean(LOCAL_ENABLED, true)
                .putLong(SEQUENCE, 0L)
                .remove(LAST_STATUS)
                .apply();
    }

    static void clearPairing(Context context) {
        values(context).edit().clear().apply();
    }

    static boolean isLocalEnabled(Context context) {
        return values(context).getBoolean(LOCAL_ENABLED, false);
    }

    static void setLocalEnabled(Context context, boolean enabled) {
        values(context).edit().putBoolean(LOCAL_ENABLED, enabled).apply();
    }

    @SuppressLint("ApplySharedPref")
    static synchronized long nextSequence(Context context) {
        SharedPreferences preferences = values(context);
        long current = preferences.getLong(SEQUENCE, 0L);
        if (current == Long.MAX_VALUE) {
            throw new IllegalStateException("Unlock sequence is exhausted; pair the phone again");
        }
        long next = current + 1L;
        // Persist synchronously on the worker thread before networking so a crash cannot replay it.
        preferences.edit().putLong(SEQUENCE, next).commit();
        return next;
    }

    static void setLastStatus(Context context, String status) {
        values(context).edit().putString(LAST_STATUS, status).apply();
    }

    static String lastStatus(Context context) {
        return values(context).getString(LAST_STATUS, "");
    }

    private static SharedPreferences values(Context context) {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    static final class Configuration {
        final String origin;
        final String deviceId;
        final String secret;
        final String displayName;

        Configuration(String origin, String deviceId, String secret, String displayName) {
            this.origin = origin == null ? "" : origin;
            this.deviceId = deviceId == null ? "" : deviceId;
            this.secret = secret == null ? "" : secret;
            this.displayName = normalizeName(displayName);
        }

        boolean isValid() {
            return validPrivateOrigin(origin)
                    && DEVICE.matcher(deviceId).matches()
                    && SECRET_VALUE.matcher(secret).matches()
                    && !displayName.isEmpty()
                    && displayName.length() <= 80;
        }

        boolean sameIdentity(Configuration other) {
            return deviceId.equals(other.deviceId) && origin.equals(other.origin);
        }

        private static String normalizeName(String value) {
            if (value == null) {
                return "Control Tower";
            }
            String normalized = value.trim().replaceAll("\\s+", " ");
            return normalized.isEmpty() ? "Control Tower" : normalized;
        }

        private static boolean validPrivateOrigin(String value) {
            try {
                URI parsed = new URI(value);
                if (!("http".equals(parsed.getScheme()) || "https".equals(parsed.getScheme()))
                        || parsed.getUserInfo() != null
                        || parsed.getHost() == null
                        || parsed.getPort() < 1
                        || !(parsed.getPath().isEmpty() || "/".equals(parsed.getPath()))
                        || parsed.getQuery() != null
                        || parsed.getFragment() != null) {
                    return false;
                }
                String[] octets = parsed.getHost().toLowerCase(Locale.ROOT).split("\\.", -1);
                if (octets.length != 4) {
                    return false;
                }
                int first = parseOctet(octets[0]);
                int second = parseOctet(octets[1]);
                parseOctet(octets[2]);
                parseOctet(octets[3]);
                return first == 10
                        || (first == 172 && second >= 16 && second <= 31)
                        || (first == 192 && second == 168);
            } catch (IllegalArgumentException | URISyntaxException ignored) {
                return false;
            }
        }

        private static int parseOctet(String value) {
            if (value.isEmpty() || (value.length() > 1 && value.startsWith("0"))) {
                throw new IllegalArgumentException("Invalid IPv4 octet");
            }
            int parsed = Integer.parseInt(value);
            if (parsed < 0 || parsed > 255) {
                throw new IllegalArgumentException("Invalid IPv4 octet");
            }
            return parsed;
        }
    }
}
