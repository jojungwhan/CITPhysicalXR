package com.cit.controltower.companion;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

final class CameraUploadCoordinator {
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();
    private static final AtomicBoolean BUSY = new AtomicBoolean();

    private CameraUploadCoordinator() {
    }

    static boolean hasMediaPermission(Context context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            return context.checkSelfPermission(Manifest.permission.READ_MEDIA_IMAGES)
                    == PackageManager.PERMISSION_GRANTED
                    && context.checkSelfPermission(Manifest.permission.READ_MEDIA_VIDEO)
                    == PackageManager.PERMISSION_GRANTED;
        }
        return context.checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE)
                == PackageManager.PERMISSION_GRANTED;
    }

    static boolean request(Context context, Listener listener) {
        if (!BUSY.compareAndSet(false, true)) {
            return false;
        }
        Context applicationContext = context.getApplicationContext();
        EXECUTOR.execute(() -> {
            CameraFtpClient.Result result = null;
            Exception failure = null;
            try {
                CompanionPreferences.Configuration configuration =
                        CompanionPreferences.load(applicationContext);
                if (!configuration.isValid()) {
                    throw new IllegalStateException("Control Tower is not paired");
                }
                result = CameraFtpClient.uploadSonyMedia(
                        applicationContext,
                        configuration,
                        (completed, total, name) -> listener.onProgress(completed, total, name)
                );
                CompanionPreferences.setLastStatus(applicationContext, result.message);
            } catch (Exception error) {
                failure = error;
                String message = error.getMessage();
                CompanionPreferences.setLastStatus(
                        applicationContext,
                        message == null || message.isBlank()
                                ? error.getClass().getSimpleName()
                                : message
                );
            } finally {
                BUSY.set(false);
                listener.onComplete(result, failure);
            }
        });
        return true;
    }

    interface Listener {
        void onProgress(int completed, int total, String name);

        void onComplete(CameraFtpClient.Result result, Exception failure);
    }
}
