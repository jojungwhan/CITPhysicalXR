package com.cit.controltower.companion;

import android.annotation.SuppressLint;
import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

final class CompanionPreferences {
    private static final String FILE = "control_tower_companion";
    private static final String SITE_ORDER = "site_order_v2";
    private static final String PRIMARY_DEVICE_ID = "primary_device_id_v2";
    private static final String SITE_PREFIX = "site.";
    private static final String ORIGIN = "origin";
    private static final String DEVICE_ID = "device_id";
    private static final String SECRET = "secret";
    private static final String DISPLAY_NAME = "display_name";
    private static final String LOCAL_ENABLED = "local_enabled";
    private static final String SEQUENCE = "sequence";
    private static final String LAST_STATUS = "last_status";
    private static final Pattern DEVICE = Pattern.compile("android-[a-f0-9]{16}");
    private static final Pattern SITE = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
    private static final Pattern SECRET_VALUE = Pattern.compile("[A-Za-z0-9_-]{43,128}");
    private static final Pattern TAILSCALE_HOST = Pattern.compile(
            "(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+ts\\.net"
    );
    private static final int MAX_SITES = 8;

    private CompanionPreferences() {
    }

    static Configuration load(Context context) {
        List<Configuration> configurations = loadAll(context);
        if (configurations.isEmpty()) {
            return Configuration.empty();
        }
        String primary = values(context).getString(PRIMARY_DEVICE_ID, "");
        for (Configuration configuration : configurations) {
            if (configuration.deviceId.equals(primary)) {
                return configuration;
            }
        }
        return configurations.get(0);
    }

    static List<Configuration> loadAll(Context context) {
        SharedPreferences preferences = values(context);
        List<String> ids = orderedDeviceIds(preferences);
        ArrayList<Configuration> configurations = new ArrayList<>();
        for (String deviceId : ids) {
            Configuration configuration = readSite(preferences, deviceId);
            if (configuration.isValid()) {
                configurations.add(configuration);
            }
        }
        if (!configurations.isEmpty()) {
            return List.copyOf(configurations);
        }
        Configuration legacy = legacyConfiguration(preferences);
        return legacy.isValid() ? List.of(legacy) : List.of();
    }

    @SuppressLint("ApplySharedPref")
    static synchronized void savePairing(Context context, Configuration incoming) {
        SharedPreferences preferences = values(context);
        List<Configuration> current = loadAll(context);
        persistSites(preferences, pairingsWith(current, incoming));
        if (current.isEmpty()) {
            preferences.edit().putBoolean(LOCAL_ENABLED, incoming.hasLocalControl()).commit();
        }
    }

    static List<Configuration> pairingsWith(List<Configuration> configurations, Configuration incoming) {
        if (!incoming.isValid()) {
            throw new IllegalArgumentException("Invalid Control Tower pairing");
        }
        ArrayList<Configuration> updated = new ArrayList<>(configurations);
        int replacement = -1;
        for (int index = 0; index < updated.size(); index++) {
            Configuration current = updated.get(index);
            if (current.sameIdentity(incoming)) {
                replacement = index;
            } else if (current.deviceId.equals(incoming.deviceId)
                    || current.siteId.equals(incoming.siteId)) {
                throw new IllegalArgumentException("Remove the existing site before pairing a new identity");
            }
        }
        if (replacement >= 0) {
            updated.set(replacement, incoming);
        } else {
            if (updated.size() >= MAX_SITES) {
                throw new IllegalStateException("Control Tower supports at most eight paired sites");
            }
            updated.add(incoming);
        }
        return List.copyOf(updated);
    }

    @SuppressLint("ApplySharedPref")
    static synchronized void removePairing(Context context, String deviceId) {
        SharedPreferences preferences = values(context);
        ArrayList<Configuration> remaining = new ArrayList<>();
        for (Configuration configuration : loadAll(context)) {
            if (!configuration.deviceId.equals(deviceId)) {
                remaining.add(configuration);
            }
        }
        persistSites(preferences, remaining);
        if (remaining.isEmpty() || !load(context).hasLocalControl()) {
            preferences.edit().putBoolean(LOCAL_ENABLED, false).commit();
        }
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
    static synchronized long nextSequence(
            Context context,
            Configuration configuration
    ) {
        SharedPreferences preferences = values(context);
        boolean migrated = orderedDeviceIds(preferences).contains(configuration.deviceId);
        String key = migrated ? siteKey(configuration.deviceId, SEQUENCE) : SEQUENCE;
        long current = preferences.getLong(key, 0L);
        if (current == Long.MAX_VALUE) {
            throw new IllegalStateException("Phone sequence is exhausted; pair this site again");
        }
        long next = current + 1L;
        // Persist synchronously before networking so a crash cannot replay the request.
        if (!preferences.edit().putLong(key, next).commit()) {
            throw new IllegalStateException("Could not persist the phone request sequence");
        }
        return next;
    }

    static void setLastStatus(
            Context context,
            Configuration configuration,
            String status
    ) {
        String key = orderedDeviceIds(values(context)).contains(configuration.deviceId)
                ? siteKey(configuration.deviceId, LAST_STATUS)
                : LAST_STATUS;
        values(context).edit().putString(key, status).apply();
    }

    static void setLastStatus(Context context, String status) {
        Configuration configuration = load(context);
        if (configuration.isValid()) {
            setLastStatus(context, configuration, status);
        }
    }

    static String lastStatus(Context context, Configuration configuration) {
        SharedPreferences preferences = values(context);
        String key = orderedDeviceIds(preferences).contains(configuration.deviceId)
                ? siteKey(configuration.deviceId, LAST_STATUS)
                : LAST_STATUS;
        return preferences.getString(key, "");
    }

    static String lastStatus(Context context) {
        Configuration configuration = load(context);
        return configuration.isValid() ? lastStatus(context, configuration) : "";
    }

    private static void persistSites(
            SharedPreferences preferences,
            List<Configuration> configurations
    ) {
        String oldPrimary = preferences.getString(PRIMARY_DEVICE_ID, "");
        Set<String> oldIds = new HashSet<>(orderedDeviceIds(preferences));
        Configuration legacy = legacyConfiguration(preferences);
        Map<String, Long> sequences = new HashMap<>();
        Map<String, String> statuses = new HashMap<>();
        for (Configuration configuration : configurations) {
            if (oldIds.contains(configuration.deviceId)) {
                sequences.put(
                        configuration.deviceId,
                        preferences.getLong(siteKey(configuration.deviceId, SEQUENCE), 0L)
                );
                statuses.put(
                        configuration.deviceId,
                        preferences.getString(siteKey(configuration.deviceId, LAST_STATUS), "")
                );
            } else if (legacy.isValid() && legacy.sameIdentity(configuration)) {
                sequences.put(configuration.deviceId, preferences.getLong(SEQUENCE, 0L));
                statuses.put(configuration.deviceId, preferences.getString(LAST_STATUS, ""));
            }
        }
        SharedPreferences.Editor editor = preferences.edit();
        for (String key : preferences.getAll().keySet()) {
            if (key.startsWith(SITE_PREFIX)) {
                editor.remove(key);
            }
        }
        JSONArray order = new JSONArray();
        for (Configuration configuration : configurations) {
            order.put(configuration.deviceId);
            writeSite(
                    editor,
                    configuration,
                    sequences.getOrDefault(configuration.deviceId, 0L),
                    statuses.getOrDefault(configuration.deviceId, "")
            );
        }
        editor.putString(SITE_ORDER, order.toString());
        String primary = "";
        for (Configuration configuration : configurations) {
            if (configuration.deviceId.equals(oldPrimary)) {
                primary = oldPrimary;
                break;
            }
        }
        if (primary.isEmpty() && !configurations.isEmpty()) {
            primary = configurations.get(0).deviceId;
        }
        editor.putString(PRIMARY_DEVICE_ID, primary);
        editor.remove(ORIGIN)
                .remove(DEVICE_ID)
                .remove(SECRET)
                .remove(DISPLAY_NAME)
                .remove(SEQUENCE)
                .remove(LAST_STATUS);
        if (!editor.commit()) {
            throw new IllegalStateException("Could not persist Control Tower site pairing");
        }
    }

    private static void writeSite(
            SharedPreferences.Editor editor,
            Configuration configuration,
            long sequence,
            String lastStatus
    ) {
        String prefix = SITE_PREFIX + configuration.deviceId + ".";
        editor.putString(prefix + "origin", configuration.origin)
                .putString(prefix + "remote_origin", configuration.remoteOrigin)
                .putString(prefix + "secret", configuration.secret)
                .putString(prefix + "display_name", configuration.displayName)
                .putString(prefix + "site_id", configuration.siteId)
                .putString(prefix + "site_name", configuration.siteName)
                .putLong(prefix + SEQUENCE, sequence)
                .putString(prefix + LAST_STATUS, lastStatus);
    }

    private static Configuration readSite(
            SharedPreferences preferences,
            String deviceId
    ) {
        String prefix = SITE_PREFIX + deviceId + ".";
        return new Configuration(
                preferences.getString(prefix + "origin", ""),
                preferences.getString(prefix + "remote_origin", ""),
                deviceId,
                preferences.getString(prefix + "secret", ""),
                preferences.getString(prefix + "display_name", "Control Tower phone"),
                preferences.getString(prefix + "site_id", ""),
                preferences.getString(prefix + "site_name", "Control Tower")
        );
    }

    private static Configuration legacyConfiguration(SharedPreferences preferences) {
        return new Configuration(
                preferences.getString(ORIGIN, ""),
                "",
                preferences.getString(DEVICE_ID, ""),
                preferences.getString(SECRET, ""),
                preferences.getString(DISPLAY_NAME, "Control Tower phone"),
                "legacy-site",
                "Control Tower"
        );
    }

    private static List<String> orderedDeviceIds(SharedPreferences preferences) {
        ArrayList<String> ids = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        try {
            JSONArray order = new JSONArray(preferences.getString(SITE_ORDER, "[]"));
            for (int index = 0; index < order.length() && ids.size() < MAX_SITES; index++) {
                String value = order.optString(index, "");
                if (DEVICE.matcher(value).matches() && seen.add(value)) {
                    ids.add(value);
                }
            }
        } catch (Exception ignored) {
            return List.of();
        }
        return ids;
    }

    private static String siteKey(String deviceId, String field) {
        return SITE_PREFIX + deviceId + "." + field;
    }

    private static SharedPreferences values(Context context) {
        return context.getSharedPreferences(FILE, Context.MODE_PRIVATE);
    }

    static final class Configuration {
        final String origin;
        final String remoteOrigin;
        final String deviceId;
        final String secret;
        final String displayName;
        final String siteId;
        final String siteName;

        Configuration(String origin, String deviceId, String secret, String displayName) {
            this(
                    origin,
                    "",
                    deviceId,
                    secret,
                    displayName,
                    "legacy-site",
                    "Control Tower"
            );
        }

        Configuration(
                String origin,
                String remoteOrigin,
                String deviceId,
                String secret,
                String displayName,
                String siteId,
                String siteName
        ) {
            this.origin = origin == null ? "" : origin;
            this.remoteOrigin = remoteOrigin == null ? "" : remoteOrigin;
            this.deviceId = deviceId == null ? "" : deviceId;
            this.secret = secret == null ? "" : secret;
            this.displayName = normalizeName(displayName, "Control Tower phone");
            this.siteId = siteId == null ? "" : siteId;
            this.siteName = normalizeName(siteName, "Control Tower");
        }

        static Configuration empty() {
            return new Configuration("", "", "", "", "", "", "");
        }

        boolean isValid() {
            return (validPrivateOrigin(origin) || validRemoteOrigin(remoteOrigin))
                    && (remoteOrigin.isEmpty() || validRemoteOrigin(remoteOrigin))
                    && DEVICE.matcher(deviceId).matches()
                    && SITE.matcher(siteId).matches()
                    && SECRET_VALUE.matcher(secret).matches()
                    && !displayName.isEmpty()
                    && displayName.length() <= 80
                    && !siteName.isEmpty()
                    && siteName.length() <= 80;
        }

        boolean sameIdentity(Configuration other) {
            return deviceId.equals(other.deviceId) && secret.equals(other.secret);
        }

        boolean hasRemoteControl() {
            return !remoteOrigin.isEmpty();
        }

        boolean hasLocalControl() {
            return validPrivateOrigin(origin);
        }

        String controlOrigin() {
            return hasRemoteControl() ? remoteOrigin : origin;
        }

        private static String normalizeName(String value, String fallback) {
            if (value == null) {
                return fallback;
            }
            String normalized = value.trim().replaceAll("\\s+", " ");
            return normalized.isEmpty() ? fallback : normalized;
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

        private static boolean validRemoteOrigin(String value) {
            try {
                URI parsed = new URI(value);
                String host = parsed.getHost();
                return "https".equals(parsed.getScheme())
                        && parsed.getUserInfo() == null
                        && host != null
                        && TAILSCALE_HOST.matcher(host.toLowerCase(Locale.ROOT)).matches()
                        && (parsed.getPort() == -1 || parsed.getPort() == 443)
                        && (parsed.getPath().isEmpty() || "/".equals(parsed.getPath()))
                        && parsed.getQuery() == null
                        && parsed.getFragment() == null;
            } catch (URISyntaxException ignored) {
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
