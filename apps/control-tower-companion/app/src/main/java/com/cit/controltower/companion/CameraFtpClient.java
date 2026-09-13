package com.cit.controltower.companion;

import android.content.ContentResolver;
import android.content.ContentUris;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.provider.MediaStore;

import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.ByteArrayInputStream;
import java.io.Closeable;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.io.OutputStreamWriter;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class CameraFtpClient {
    private static final Pattern RESPONSE = Pattern.compile("^(\\d{3})([- ])(.*)$");
    private static final Pattern EPSV = Pattern.compile(".*\\(\\|\\|\\|(\\d+)\\|\\).*");
    private static final Pattern PASV = Pattern.compile(
            ".*\\((\\d+),(\\d+),(\\d+),(\\d+),(\\d+),(\\d+)\\).*"
    );
    private static final int CONNECT_TIMEOUT_MS = 8_000;
    private static final int CONTROL_TIMEOUT_MS = 30_000;
    private static final int VERIFY_TIMEOUT_MS = 180_000;
    private static final int BUFFER_SIZE = 256 * 1024;

    private CameraFtpClient() {
    }

    static Result uploadSonyMedia(
            Context context,
            CompanionPreferences.Configuration configuration,
            ProgressListener progress
    ) throws Exception {
        URI origin = new URI(configuration.origin);
        String host = origin.getHost();
        if (host == null || host.isBlank()) {
            throw new IOException("Control Tower FTP host is unavailable");
        }
        List<MediaItem> media = listSonyMedia(context.getContentResolver());
        if (media.isEmpty()) {
            return new Result(0, 0, 0L, "No Sony camera originals are on this phone.");
        }
        int uploaded = 0;
        int verified = 0;
        long uploadedBytes = 0L;
        try (Session session = new Session(host, CameraFtpProtocol.PORT)) {
            session.login(
                    configuration.deviceId,
                    CameraFtpProtocol.password(configuration.secret)
            );
            for (int index = 0; index < media.size(); index++) {
                MediaItem item = media.get(index);
                progress.onProgress(index, media.size(), item.name);
                String sha256 = hash(context.getContentResolver(), item.uri);
                String uploadId = CameraFtpProtocol.uploadId(item.name, item.size, sha256);
                if (session.size(uploadId + ".ok") >= 0) {
                    verified++;
                    continue;
                }

                String partName = uploadId + ".part";
                long remoteSize = session.size(partName);
                long offset = remoteSize >= 0 && remoteSize <= item.size ? remoteSize : 0L;
                if (offset < item.size) {
                    try (InputStream source = context.getContentResolver().openInputStream(item.uri)) {
                        if (source == null) {
                            throw new IOException("Cannot open " + item.name);
                        }
                        skipFully(source, offset);
                        session.store(partName, source, offset);
                    }
                    uploaded++;
                    uploadedBytes += item.size - offset;
                }

                byte[] receipt = new JSONObject()
                        .put("schemaVersion", "1.0")
                        .put("uploadId", uploadId)
                        .put("name", item.name)
                        .put("sizeBytes", item.size)
                        .put("sha256", sha256)
                        .toString()
                        .getBytes(StandardCharsets.UTF_8);
                session.store(
                        uploadId + ".json",
                        new ByteArrayInputStream(receipt),
                        0L
                );
                session.waitForAcknowledgement(uploadId + ".ok", VERIFY_TIMEOUT_MS);
                verified++;
            }
        }
        return new Result(
                uploaded,
                verified,
                uploadedBytes,
                verified + " Sony camera original(s) verified on this PC."
        );
    }

    private static List<MediaItem> listSonyMedia(ContentResolver resolver) throws IOException {
        List<MediaItem> result = new ArrayList<>();
        Uri collection = MediaStore.Files.getContentUri("external");
        String[] projection;
        String selection;
        String[] arguments;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            projection = new String[]{
                    MediaStore.Files.FileColumns._ID,
                    MediaStore.Files.FileColumns.DISPLAY_NAME,
                    MediaStore.Files.FileColumns.SIZE,
                    MediaStore.Files.FileColumns.RELATIVE_PATH,
            };
            selection = MediaStore.Files.FileColumns.RELATIVE_PATH + " LIKE ?";
            arguments = new String[]{"DCIM/Imaging Edge Mobile/%"};
        } else {
            projection = new String[]{
                    MediaStore.Files.FileColumns._ID,
                    MediaStore.Files.FileColumns.DISPLAY_NAME,
                    MediaStore.Files.FileColumns.SIZE,
                    MediaStore.Files.FileColumns.DATA,
            };
            selection = MediaStore.Files.FileColumns.DATA + " LIKE ?";
            arguments = new String[]{"%/DCIM/Imaging Edge Mobile/%"};
        }
        try (Cursor cursor = resolver.query(
                collection,
                projection,
                selection,
                arguments,
                MediaStore.Files.FileColumns.DISPLAY_NAME + " ASC"
        )) {
            if (cursor == null) {
                throw new IOException("Android media inventory is unavailable");
            }
            int idColumn = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns._ID);
            int nameColumn = cursor.getColumnIndexOrThrow(
                    MediaStore.Files.FileColumns.DISPLAY_NAME
            );
            int sizeColumn = cursor.getColumnIndexOrThrow(MediaStore.Files.FileColumns.SIZE);
            while (cursor.moveToNext()) {
                String name = cursor.getString(nameColumn);
                long size = cursor.getLong(sizeColumn);
                if (name == null || size < 0 || !supportedName(name)) {
                    continue;
                }
                result.add(new MediaItem(
                        ContentUris.withAppendedId(collection, cursor.getLong(idColumn)),
                        name,
                        size
                ));
            }
        } catch (SecurityException error) {
            throw new IOException("Allow Control Tower to read photos and videos once", error);
        }
        result.sort(Comparator.comparing(item -> item.name.toLowerCase(Locale.ROOT)));
        return result;
    }

    private static boolean supportedName(String name) {
        String lower = name.toLowerCase(Locale.ROOT);
        return lower.endsWith(".arw")
                || lower.endsWith(".heic")
                || lower.endsWith(".heif")
                || lower.endsWith(".hif")
                || lower.endsWith(".jpeg")
                || lower.endsWith(".jpg")
                || lower.endsWith(".m2ts")
                || lower.endsWith(".mov")
                || lower.endsWith(".mp4")
                || lower.endsWith(".mts");
    }

    private static String hash(ContentResolver resolver, Uri uri) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream source = resolver.openInputStream(uri)) {
            if (source == null) {
                throw new IOException("Cannot read camera original");
            }
            byte[] buffer = new byte[BUFFER_SIZE];
            int read;
            while ((read = source.read(buffer)) >= 0) {
                if (read > 0) {
                    digest.update(buffer, 0, read);
                }
            }
        }
        return CameraFtpProtocol.hex(digest.digest());
    }

    private static void skipFully(InputStream source, long offset) throws IOException {
        long remaining = offset;
        while (remaining > 0) {
            long skipped = source.skip(remaining);
            if (skipped > 0) {
                remaining -= skipped;
                continue;
            }
            if (source.read() < 0) {
                throw new IOException("Camera file became shorter during resume");
            }
            remaining--;
        }
    }

    interface ProgressListener {
        void onProgress(int completed, int total, String name);
    }

    static final class Result {
        final int uploadedFiles;
        final int verifiedFiles;
        final long uploadedBytes;
        final String message;

        Result(int uploadedFiles, int verifiedFiles, long uploadedBytes, String message) {
            this.uploadedFiles = uploadedFiles;
            this.verifiedFiles = verifiedFiles;
            this.uploadedBytes = uploadedBytes;
            this.message = message;
        }
    }

    private static final class MediaItem {
        final Uri uri;
        final String name;
        final long size;

        MediaItem(Uri uri, String name, long size) {
            this.uri = uri;
            this.name = name;
            this.size = size;
        }
    }

    private static final class Response {
        final int code;
        final String text;

        Response(int code, String text) {
            this.code = code;
            this.text = text;
        }
    }

    private static final class Session implements Closeable {
        private final String host;
        private final Socket control;
        private final BufferedReader reader;
        private final BufferedWriter writer;

        Session(String host, int port) throws IOException {
            this.host = host;
            control = new Socket();
            control.connect(new InetSocketAddress(host, port), CONNECT_TIMEOUT_MS);
            control.setSoTimeout(CONTROL_TIMEOUT_MS);
            reader = new BufferedReader(new InputStreamReader(
                    control.getInputStream(),
                    StandardCharsets.US_ASCII
            ));
            writer = new BufferedWriter(new OutputStreamWriter(
                    control.getOutputStream(),
                    StandardCharsets.US_ASCII
            ));
            expect(readResponse(), 220);
        }

        void login(String username, String password) throws IOException {
            Response user = command("USER " + username);
            if (user.code == 331) {
                expect(command("PASS " + password), 230);
            } else {
                expect(user, 230);
            }
            expect(command("TYPE I"), 200);
        }

        long size(String name) throws IOException {
            Response response = command("SIZE " + name);
            if (response.code == 550) {
                return -1L;
            }
            expect(response, 213);
            try {
                return Long.parseLong(response.text.substring(4).trim());
            } catch (NumberFormatException error) {
                throw new IOException("FTP returned an invalid size", error);
            }
        }

        void store(String name, InputStream source, long offset) throws IOException {
            int dataPort = passivePort();
            try (Socket data = new Socket()) {
                data.connect(new InetSocketAddress(host, dataPort), CONNECT_TIMEOUT_MS);
                if (offset > 0) {
                    expect(command("REST " + offset), 350);
                }
                Response starting = command("STOR " + name);
                if (starting.code != 125 && starting.code != 150) {
                    throw failure(starting);
                }
                try (OutputStream output = new BufferedOutputStream(
                        data.getOutputStream(),
                        BUFFER_SIZE
                ); InputStream buffered = new BufferedInputStream(source, BUFFER_SIZE)) {
                    byte[] buffer = new byte[BUFFER_SIZE];
                    int read;
                    while ((read = buffered.read(buffer)) >= 0) {
                        if (read > 0) {
                            output.write(buffer, 0, read);
                        }
                    }
                }
            }
            Response completed = readResponse();
            if (completed.code != 226 && completed.code != 250) {
                throw failure(completed);
            }
        }

        void waitForAcknowledgement(String name, int timeoutMs) throws IOException {
            long deadline = System.currentTimeMillis() + timeoutMs;
            while (System.currentTimeMillis() < deadline) {
                if (size(name) >= 0) {
                    return;
                }
                try {
                    Thread.sleep(1_000L);
                } catch (InterruptedException error) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Camera FTP verification was interrupted", error);
                }
            }
            throw new IOException("Control Tower did not verify the camera file in time");
        }

        private int passivePort() throws IOException {
            Response epsv = command("EPSV");
            if (epsv.code == 229) {
                Matcher match = EPSV.matcher(epsv.text);
                if (!match.matches()) {
                    throw new IOException("FTP returned an invalid EPSV endpoint");
                }
                return Integer.parseInt(match.group(1));
            }
            Response pasv = command("PASV");
            expect(pasv, 227);
            Matcher match = PASV.matcher(pasv.text);
            if (!match.matches()) {
                throw new IOException("FTP returned an invalid PASV endpoint");
            }
            return Integer.parseInt(match.group(5)) * 256 + Integer.parseInt(match.group(6));
        }

        private Response command(String value) throws IOException {
            if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
                throw new IOException("Invalid FTP command");
            }
            writer.write(value);
            writer.write("\r\n");
            writer.flush();
            return readResponse();
        }

        private Response readResponse() throws IOException {
            String first = reader.readLine();
            if (first == null) {
                throw new IOException("FTP connection closed unexpectedly");
            }
            Matcher match = RESPONSE.matcher(first);
            if (!match.matches()) {
                throw new IOException("FTP returned an invalid response");
            }
            int code = Integer.parseInt(match.group(1));
            StringBuilder text = new StringBuilder(first);
            if ("-".equals(match.group(2))) {
                String terminator = match.group(1) + " ";
                while (true) {
                    String line = reader.readLine();
                    if (line == null) {
                        throw new IOException("FTP multiline response was incomplete");
                    }
                    text.append('\n').append(line);
                    if (line.startsWith(terminator)) {
                        break;
                    }
                    if (text.length() > 32_768) {
                        throw new IOException("FTP response is too large");
                    }
                }
            }
            return new Response(code, text.toString());
        }

        private static void expect(Response response, int expected) throws IOException {
            if (response.code != expected) {
                throw failure(response);
            }
        }

        private static IOException failure(Response response) {
            return new IOException("FTP returned " + response.code);
        }

        @Override
        public void close() {
            try {
                command("QUIT");
            } catch (IOException ignored) {
                // Socket close below is the authoritative cleanup.
            }
            try {
                control.close();
            } catch (IOException ignored) {
                // Nothing remains to recover after the socket is closed.
            }
        }
    }
}
