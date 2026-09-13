package com.cit.controltower.companion;

import android.app.KeyguardManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ServiceInfo;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Build;
import android.os.IBinder;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

public final class UnlockMonitorService extends Service {
    private static final String CHANNEL_ID = "control_tower_unlock";
    private static final int NOTIFICATION_ID = 4107;
    private static final long CAMERA_SYNC_INITIAL_DELAY_SECONDS = 30L;
    private static final long CAMERA_SYNC_INTERVAL_SECONDS = TimeUnit.MINUTES.toSeconds(15L);
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final ScheduledExecutorService cameraScheduler =
            Executors.newSingleThreadScheduledExecutor();
    private BroadcastReceiver screenReceiver;
    private KeyguardManager keyguardManager;
    private volatile boolean sawLockedState;

    static void start(Context context) {
        Intent service = new Intent(context, UnlockMonitorService.class);
        context.startForegroundService(service);
    }

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
        startAsForeground(getString(R.string.notification_waiting));
        keyguardManager = (KeyguardManager) getSystemService(KEYGUARD_SERVICE);
        sawLockedState = keyguardManager != null && keyguardManager.isKeyguardLocked();
        screenReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                String action = intent.getAction();
                if (Intent.ACTION_SCREEN_ON.equals(action)) {
                    sawLockedState = keyguardManager != null
                            && keyguardManager.isKeyguardLocked();
                } else if (Intent.ACTION_USER_PRESENT.equals(action)) {
                    boolean genuineUnlock = sawLockedState
                            && keyguardManager != null
                            && !keyguardManager.isKeyguardLocked();
                    sawLockedState = false;
                    if (genuineUnlock) {
                        handleUnlock();
                    }
                }
            }
        };
        IntentFilter filter = new IntentFilter();
        filter.addAction(Intent.ACTION_SCREEN_ON);
        filter.addAction(Intent.ACTION_USER_PRESENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(screenReceiver, filter, Context.RECEIVER_EXPORTED);
        } else {
            registerReceiver(screenReceiver, filter);
        }
        cameraScheduler.scheduleWithFixedDelay(
                this::handleAutomaticCameraUpload,
                CAMERA_SYNC_INITIAL_DELAY_SECONDS,
                CAMERA_SYNC_INTERVAL_SECONDS,
                TimeUnit.SECONDS
        );
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        CompanionPreferences.Configuration configuration = CompanionPreferences.load(this);
        if (!CompanionPreferences.isLocalEnabled(this) || !configuration.isValid()) {
            stopSelf();
            return START_NOT_STICKY;
        }
        updateNotification(getString(R.string.notification_waiting));
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (screenReceiver != null) {
            unregisterReceiver(screenReceiver);
            screenReceiver = null;
        }
        executor.shutdownNow();
        cameraScheduler.shutdownNow();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void handleUnlock() {
        CompanionPreferences.Configuration configuration = CompanionPreferences.load(this);
        if (!CompanionPreferences.isLocalEnabled(this) || !configuration.isValid()) {
            return;
        }
        if (!hasWifiTransport()) {
            setStatusAndNotify(
                    getString(R.string.wifi_required),
                    getString(R.string.notification_failed)
            );
            return;
        }
        updateNotification(getString(R.string.notification_sending));
        executor.execute(() -> {
            UnlockClient.Result result;
            try {
                result = UnlockClient.send(this, configuration);
            } catch (RuntimeException error) {
                setStatusAndNotify(
                        getString(R.string.notification_failed),
                        getString(R.string.notification_failed)
                );
                return;
            }
            int notificationText;
            if (result.accepted && "succeeded".equals(result.outcome)) {
                notificationText = R.string.notification_succeeded;
            } else if ("disabled".equals(result.outcome) || "cooldown".equals(result.outcome)) {
                notificationText = R.string.notification_disabled;
            } else {
                notificationText = R.string.notification_failed;
            }
            setStatusAndNotify(result.message, getString(notificationText));
        });
    }

    private void handleAutomaticCameraUpload() {
        CompanionPreferences.Configuration configuration = CompanionPreferences.load(this);
        if (!CompanionPreferences.isLocalEnabled(this)
                || !configuration.isValid()
                || !CameraUploadCoordinator.hasMediaPermission(this)
                || !hasWifiTransport()) {
            return;
        }
        CameraUploadCoordinator.request(this, new CameraUploadCoordinator.Listener() {
            @Override
            public void onProgress(int completed, int total, String name) {
                // The durable status is updated when the complete verified batch finishes.
            }

            @Override
            public void onComplete(CameraFtpClient.Result result, Exception failure) {
                // CameraUploadCoordinator persists a concise result for the activity.
            }
        });
    }

    private boolean hasWifiTransport() {
        ConnectivityManager connectivity =
                (ConnectivityManager) getSystemService(CONNECTIVITY_SERVICE);
        if (connectivity == null) {
            return false;
        }
        Network active = connectivity.getActiveNetwork();
        NetworkCapabilities capabilities = connectivity.getNetworkCapabilities(active);
        return capabilities != null && capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI);
    }

    private void setStatusAndNotify(String status, String notificationText) {
        CompanionPreferences.setLastStatus(this, status);
        updateNotification(notificationText);
    }

    private void createNotificationChannel() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) {
            return;
        }
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel),
                NotificationManager.IMPORTANCE_LOW
        );
        channel.setDescription(getString(R.string.notification_channel_description));
        manager.createNotificationChannel(channel);
    }

    private void startAsForeground(String text) {
        Notification notification = notification(text);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
            );
        } else {
            startForeground(NOTIFICATION_ID, notification);
        }
    }

    private void updateNotification(String text) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.notify(NOTIFICATION_ID, notification(text));
        }
    }

    private Notification notification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent content = PendingIntent.getActivity(
                this,
                0,
                open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        return new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_control_tower)
                .setContentTitle(getString(R.string.notification_title))
                .setContentText(text)
                .setContentIntent(content)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setCategory(Notification.CATEGORY_SERVICE)
                .build();
    }
}
