package com.cit.controltower.companion;

import android.content.Context;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

final class UnlockClient {
    private static final int MAX_RESPONSE_CHARS = 8_192;

    private UnlockClient() {
    }

    static synchronized Result send(
            Context context,
            CompanionPreferences.Configuration configuration
    ) {
        return sendRequest(configuration, CompanionPreferences.nextSequence(context), false);
    }

    static synchronized Result toggle(
            Context context,
            CompanionPreferences.Configuration configuration
    ) {
        return sendRequest(configuration, CompanionPreferences.nextSequence(context), true);
    }

    private static Result sendRequest(
            CompanionPreferences.Configuration configuration,
            long sequence,
            boolean toggle
    ) {
        HttpURLConnection connection = null;
        try {
            String eventId = UUID.randomUUID().toString();
            long occurredAt = System.currentTimeMillis();
            String signature = toggle
                    ? UnlockProtocol.toggleSignature(
                            configuration.secret,
                            configuration.deviceId,
                            eventId,
                            sequence,
                            occurredAt
                    )
                    : UnlockProtocol.signature(
                            configuration.secret,
                            configuration.deviceId,
                            eventId,
                            sequence,
                            occurredAt
                    );
            JSONObject body = new JSONObject()
                    .put("schemaVersion", "1.0")
                    .put("deviceId", configuration.deviceId)
                    .put("eventId", eventId)
                    .put("sequence", sequence)
                    .put("occurredAtEpochMs", occurredAt);
            byte[] payload = body.toString().getBytes(StandardCharsets.UTF_8);

            URL endpoint = new URL(
                    configuration.origin + (
                            toggle
                                    ? "/api/v1/fabric/unlock-automation/toggle"
                                    : "/api/v1/fabric/unlock-automation/events"
                    )
            );
            connection = (HttpURLConnection) endpoint.openConnection();
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(5_000);
            connection.setReadTimeout(8_000);
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Accept", "application/json");
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setRequestProperty(
                    toggle ? "X-CIT-Toggle-Signature" : "X-CIT-Unlock-Signature",
                    signature
            );
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
            if (status < 200 || status >= 300) {
                return new Result(
                        false,
                        "failed",
                        null,
                        "Control Tower returned HTTP " + status
                );
            }
            JSONObject parsed = new JSONObject(response);
            Boolean on = parsed.has("on") && !parsed.isNull("on")
                    ? parsed.getBoolean("on")
                    : null;
            return new Result(
                    parsed.optBoolean("accepted", false),
                    parsed.optString("outcome", "failed"),
                    on,
                    parsed.optString("message", "Control Tower processed the unlock event.")
            );
        } catch (Exception error) {
            String message = error.getMessage();
            return new Result(
                    false,
                    "failed",
                    null,
                    message == null || message.isBlank()
                            ? error.getClass().getSimpleName()
                            : message
            );
        } finally {
            if (connection != null) {
                connection.disconnect();
            }
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

    static final class Result {
        final boolean accepted;
        final String outcome;
        final Boolean on;
        final String message;

        Result(boolean accepted, String outcome, Boolean on, String message) {
            this.accepted = accepted;
            this.outcome = outcome;
            this.on = on;
            this.message = message;
        }
    }
}
