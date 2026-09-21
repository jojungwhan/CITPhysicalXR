package com.cit.controltower.companion;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

final class RemotePlugClient {
    private static final int MAX_RESPONSE_CHARS = 16_384;

    private RemotePlugClient() {
    }

    static PowerResult setPower(
            Context context,
            CompanionPreferences.Configuration configuration,
            boolean on
    ) {
        return PhoneRequestCoordinator.run(configuration.deviceId,
                () -> setPowerRequest(context, configuration, on));
    }

    private static PowerResult setPowerRequest(
            Context context,
            CompanionPreferences.Configuration configuration,
            boolean on
    ) {
        try {
            long sequence = CompanionPreferences.nextSequence(context, configuration);
            String eventId = UUID.randomUUID().toString();
            long occurredAt = System.currentTimeMillis();
            String signature = UnlockProtocol.remotePowerSignature(
                    configuration.secret,
                    configuration.deviceId,
                    eventId,
                    sequence,
                    occurredAt,
                    on
            );
            JSONObject body = envelope(configuration, eventId, sequence, occurredAt)
                    .put("on", on);
            Response response = post(
                    configuration.controlOrigin() + "/api/v1/fabric/remote-plugs/power",
                    body,
                    signature
            );
            if (!response.successful()) {
                return new PowerResult(
                        false,
                        on,
                        response.status >= 500
                                ? context.getString(R.string.power_result_unknown)
                                : response.errorMessage()
                );
            }
            JSONObject parsed = new JSONObject(response.body);
            return new PowerResult(
                    parsed.optBoolean("accepted", false),
                    parsed.optBoolean("on", on),
                    boundedMessage(
                            parsed.optString("message", ""),
                            "Control Tower processed the power request."
                    )
            );
        } catch (Exception ignored) {
            return new PowerResult(
                    false,
                    on,
                    context.getString(R.string.power_result_unknown)
            );
        }
    }

    static StateResult readState(
            Context context,
            CompanionPreferences.Configuration configuration
    ) {
        return PhoneRequestCoordinator.run(configuration.deviceId,
                () -> readStateRequest(context, configuration));
    }

    private static StateResult readStateRequest(
            Context context,
            CompanionPreferences.Configuration configuration
    ) {
        try {
            long sequence = CompanionPreferences.nextSequence(context, configuration);
            String eventId = UUID.randomUUID().toString();
            long occurredAt = System.currentTimeMillis();
            String signature = UnlockProtocol.remoteStateSignature(
                    configuration.secret,
                    configuration.deviceId,
                    eventId,
                    sequence,
                    occurredAt
            );
            Response response = post(
                    configuration.controlOrigin() + "/api/v1/fabric/remote-plugs/state",
                    envelope(configuration, eventId, sequence, occurredAt),
                    signature
            );
            if (!response.successful()) {
                return new StateResult(false, 0, 0, null, response.errorMessage());
            }
            JSONObject parsed = new JSONObject(response.body);
            JSONArray plugs = parsed.getJSONArray("plugs");
            int available = 0;
            int onCount = 0;
            int knownCount = 0;
            for (int index = 0; index < plugs.length(); index++) {
                JSONObject plug = plugs.getJSONObject(index);
                if (plug.optBoolean("available", false)) {
                    available++;
                    if (plug.has("on") && !plug.isNull("on")) {
                        knownCount++;
                        if (plug.getBoolean("on")) {
                            onCount++;
                        }
                    }
                }
            }
            Boolean allOn = available == 0 || knownCount != available
                    ? null
                    : onCount == available;
            return new StateResult(true, plugs.length(), available, allOn, "");
        } catch (Exception error) {
            return new StateResult(false, 0, 0, null, conciseError(error));
        }
    }

    private static JSONObject envelope(
            CompanionPreferences.Configuration configuration,
            String eventId,
            long sequence,
            long occurredAt
    ) throws Exception {
        return new JSONObject()
                .put("schemaVersion", "1.0")
                .put("deviceId", configuration.deviceId)
                .put("eventId", eventId)
                .put("sequence", sequence)
                .put("occurredAtEpochMs", occurredAt);
    }

    private static Response post(String endpoint, JSONObject body, String signature)
            throws Exception {
        byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);
        HttpURLConnection connection = (HttpURLConnection) new URL(endpoint).openConnection();
        try {
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(5_000);
            connection.setReadTimeout(8_000);
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setRequestProperty("X-CIT-Remote-Signature", signature);
            connection.setFixedLengthStreamingMode(payload.length);
            connection.setDoOutput(true);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(payload);
            }
            int status = connection.getResponseCode();
            String response = readResponse(
                    status >= 200 && status < 300
                            ? connection.getInputStream()
                            : connection.getErrorStream()
            );
            return new Response(status, response);
        } finally {
            connection.disconnect();
        }
    }

    private static String readResponse(InputStream stream) throws Exception {
        if (stream == null) {
            return "";
        }
        StringBuilder response = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8)
        )) {
            char[] buffer = new char[1_024];
            int read;
            while ((read = reader.read(buffer)) >= 0 && response.length() < MAX_RESPONSE_CHARS) {
                int remaining = MAX_RESPONSE_CHARS - response.length();
                response.append(buffer, 0, Math.min(read, remaining));
            }
        }
        return response.toString();
    }

    private static String conciseError(Exception error) {
        String message = error.getMessage();
        return boundedMessage(message, error.getClass().getSimpleName());
    }

    private static String boundedMessage(String message, String fallback) {
        String selected = message == null || message.isBlank() ? fallback : message;
        String normalized = selected.replaceAll("\\p{Cntrl}", " ")
                .trim()
                .replaceAll("\\s+", " ");
        if (normalized.isEmpty()) {
            normalized = fallback;
        }
        return normalized.substring(0, Math.min(normalized.length(), 300));
    }

    private static final class Response {
        final int status;
        final String body;

        Response(int status, String body) {
            this.status = status;
            this.body = body;
        }

        boolean successful() {
            return status >= 200 && status < 300;
        }

        String errorMessage() {
            try {
                JSONObject parsed = new JSONObject(body);
                String message = boundedMessage(parsed.optString("message", ""), "");
                if (!message.isEmpty()) {
                    return message;
                }
            } catch (Exception ignored) {
                // The HTTP status remains the bounded fallback; do not expose raw HTML bodies.
            }
            return "Control Tower returned HTTP " + status;
        }
    }

    static final class PowerResult {
        final boolean accepted;
        final boolean on;
        final String message;

        PowerResult(boolean accepted, boolean on, String message) {
            this.accepted = accepted;
            this.on = on;
            this.message = message;
        }
    }

    static final class StateResult {
        final boolean accepted;
        final int total;
        final int available;
        final Boolean allOn;
        final String message;

        StateResult(boolean accepted, int total, int available, Boolean allOn, String message) {
            this.accepted = accepted;
            this.total = total;
            this.available = available;
            this.allOn = allOn;
            this.message = message;
        }
    }
}
