package com.cit.controltower.companion;

import android.Manifest;
import android.app.Activity;
import android.app.KeyguardManager;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int CAMERA_MEDIA_PERMISSION_REQUEST = 1002;
    private TextView pairingStatus;
    private TextView serviceStatus;
    private TextView lastStatus;
    private Button toggleButton;
    private Button addToggleWidgetButton;
    private Button addLauncherWidgetButton;
    private Button cameraUploadButton;
    private Button startButton;
    private Button stopButton;
    private final ExecutorService controlExecutor = Executors.newSingleThreadExecutor();
    private boolean toggleBusy;
    private String launchMessage = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(buildContent());
        acceptProvisioning(getIntent());
        requestNotificationPermission();
        refresh();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        acceptProvisioning(intent);
        refresh();
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    @Override
    protected void onDestroy() {
        controlExecutor.shutdownNow();
        super.onDestroy();
    }

    private ScrollView buildContent() {
        int padding = dp(24);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(padding, padding, padding, padding);
        content.setBackgroundColor(getColor(R.color.cit_surface));

        TextView title = text(getString(R.string.title), 28, true);
        title.setTextColor(getColor(R.color.cit_blue));
        content.addView(title, matchWrap());

        TextView subtitle = text(getString(R.string.subtitle), 16, false);
        subtitle.setPadding(0, dp(12), 0, dp(24));
        content.addView(subtitle, matchWrap());

        pairingStatus = text("", 17, true);
        content.addView(pairingStatus, matchWrap());
        serviceStatus = text("", 16, false);
        serviceStatus.setPadding(0, dp(10), 0, dp(10));
        content.addView(serviceStatus, matchWrap());
        lastStatus = text("", 14, false);
        lastStatus.setTextColor(Color.DKGRAY);
        lastStatus.setPadding(0, 0, 0, dp(20));
        content.addView(lastStatus, matchWrap());

        TextView manualControlTitle = text(getString(R.string.manual_control_title), 18, true);
        content.addView(manualControlTitle, matchWrap());

        TextView manualControlHelp = text(getString(R.string.manual_control_help), 14, false);
        manualControlHelp.setPadding(0, dp(6), 0, dp(4));
        content.addView(manualControlHelp, matchWrap());

        toggleButton = button(getString(R.string.toggle_plugs));
        toggleButton.setTextSize(18);
        toggleButton.setTextColor(Color.WHITE);
        toggleButton.setMinHeight(dp(72));
        toggleButton.setBackgroundTintList(
                ColorStateList.valueOf(getColor(R.color.cit_green))
        );
        toggleButton.setCompoundDrawablesRelativeWithIntrinsicBounds(
                R.drawable.ic_power_toggle,
                0,
                0,
                0
        );
        toggleButton.setCompoundDrawableTintList(ColorStateList.valueOf(Color.WHITE));
        toggleButton.setCompoundDrawablePadding(dp(10));
        toggleButton.setOnClickListener(view -> toggleConfiguredSmartPlugs());
        content.addView(toggleButton, buttonLayout());

        TextView cameraUploadTitle = text(getString(R.string.camera_upload_title), 18, true);
        cameraUploadTitle.setPadding(0, dp(24), 0, 0);
        content.addView(cameraUploadTitle, matchWrap());

        TextView cameraUploadHelp = text(getString(R.string.camera_upload_help), 14, false);
        cameraUploadHelp.setPadding(0, dp(6), 0, dp(4));
        content.addView(cameraUploadHelp, matchWrap());

        cameraUploadButton = button(getString(R.string.camera_upload_now));
        cameraUploadButton.setMinHeight(dp(56));
        cameraUploadButton.setOnClickListener(view -> startCameraUpload());
        content.addView(cameraUploadButton, buttonLayout());

        addToggleWidgetButton = button(getString(R.string.add_toggle_widget));
        addToggleWidgetButton.setOnClickListener(view -> requestToggleWidget());
        content.addView(addToggleWidgetButton, buttonLayout());

        addLauncherWidgetButton = button(getString(R.string.add_launcher_widget));
        addLauncherWidgetButton.setOnClickListener(view -> requestLauncherWidget());
        content.addView(addLauncherWidgetButton, buttonLayout());

        startButton = button(getString(R.string.start_monitoring));
        startButton.setOnClickListener(view -> {
            CompanionPreferences.Configuration configuration = CompanionPreferences.load(this);
            KeyguardManager keyguard = (KeyguardManager) getSystemService(KEYGUARD_SERVICE);
            if (!configuration.isValid()) {
                launchMessage = getString(R.string.not_paired);
            } else if (keyguard == null || !keyguard.isDeviceSecure()) {
                launchMessage = getString(R.string.secure_lock_required);
            } else {
                CompanionPreferences.setLocalEnabled(this, true);
                UnlockMonitorService.start(this);
                launchMessage = "";
            }
            refresh();
        });
        content.addView(startButton, buttonLayout());

        stopButton = button(getString(R.string.stop_monitoring));
        stopButton.setOnClickListener(view -> {
            CompanionPreferences.setLocalEnabled(this, false);
            stopService(new Intent(this, UnlockMonitorService.class));
            launchMessage = "";
            refresh();
        });
        content.addView(stopButton, buttonLayout());

        Button battery = button(getString(R.string.battery_settings));
        battery.setOnClickListener(view -> startActivity(
                new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
        ));
        content.addView(battery, buttonLayout());

        Button clear = button(getString(R.string.clear_pairing));
        clear.setOnClickListener(view -> {
            stopService(new Intent(this, UnlockMonitorService.class));
            CompanionPreferences.clearPairing(this);
            SmartPlugWidgetProvider.refreshAll(this);
            launchMessage = "";
            refresh();
        });
        content.addView(clear, buttonLayout());

        ScrollView scroll = new ScrollView(this);
        scroll.addView(content);
        return scroll;
    }

    private void acceptProvisioning(Intent intent) {
        Uri uri = intent == null ? null : intent.getData();
        CompanionPreferences.Configuration incoming = configurationFrom(uri);
        if (uri == null) {
            return;
        }
        if (incoming == null) {
            launchMessage = getString(R.string.pairing_invalid);
            return;
        }
        CompanionPreferences.Configuration existing = CompanionPreferences.load(this);
        if (!incoming.isValid()) {
            launchMessage = getString(R.string.pairing_invalid);
            return;
        }
        if (existing.isValid() && !existing.sameIdentity(incoming)) {
            launchMessage = getString(R.string.pairing_conflict);
            return;
        }
        CompanionPreferences.savePairing(this, incoming);
        SmartPlugWidgetProvider.refreshAll(this);
        KeyguardManager keyguard = (KeyguardManager) getSystemService(KEYGUARD_SERVICE);
        if (keyguard == null || !keyguard.isDeviceSecure()) {
            CompanionPreferences.setLocalEnabled(this, false);
            launchMessage = getString(R.string.secure_lock_required);
            return;
        }
        UnlockMonitorService.start(this);
        launchMessage = getString(R.string.pairing_complete);
    }

    private CompanionPreferences.Configuration configurationFrom(Uri uri) {
        try {
            if (uri == null
                    || !"cit-control-tower".equals(uri.getScheme())
                    || !"pair".equals(uri.getHost())
                    || uri.getQuery() != null
                    || uri.getFragment() != null) {
                return null;
            }
            List<String> segments = uri.getPathSegments();
            if (segments.size() != 1
                    || !uri.getEncodedPath().equals("/" + segments.get(0))) {
                return null;
            }
            byte[] decoded = Base64.getUrlDecoder().decode(segments.get(0));
            if (decoded.length < 80 || decoded.length > 1_024) {
                return null;
            }
            JSONObject payload = new JSONObject(new String(decoded, StandardCharsets.UTF_8));
            if (payload.length() != 4) {
                return null;
            }
            return new CompanionPreferences.Configuration(
                    payload.optString("origin", ""),
                    payload.optString("deviceId", ""),
                    payload.optString("secret", ""),
                    payload.optString("name", "")
            );
        } catch (Exception ignored) {
            return null;
        }
    }

    private void refresh() {
        if (pairingStatus == null) {
            return;
        }
        CompanionPreferences.Configuration configuration = CompanionPreferences.load(this);
        boolean paired = configuration.isValid();
        boolean enabled = paired && CompanionPreferences.isLocalEnabled(this);
        pairingStatus.setText(
                paired
                        ? getString(R.string.paired_with, configuration.origin)
                        : getString(R.string.not_paired)
        );
        serviceStatus.setText(
                enabled
                        ? getString(R.string.service_running)
                        : getString(R.string.service_stopped)
        );
        String recent = CompanionPreferences.lastStatus(this);
        lastStatus.setText(!launchMessage.isEmpty() ? launchMessage : recent);
        lastStatus.setVisibility(
                launchMessage.isEmpty() && recent.isEmpty() ? TextView.GONE : TextView.VISIBLE
        );
        startButton.setEnabled(paired && !enabled);
        stopButton.setEnabled(enabled);
        toggleButton.setEnabled(paired && !toggleBusy);
        cameraUploadButton.setEnabled(paired);
        addToggleWidgetButton.setEnabled(paired);
        addLauncherWidgetButton.setEnabled(true);
    }

    private void startCameraUpload() {
        if (!hasCameraMediaPermission()) {
            requestCameraMediaPermission();
            launchMessage = getString(R.string.camera_upload_permission);
            refresh();
            return;
        }
        boolean accepted = CameraUploadCoordinator.request(
                this,
                new CameraUploadCoordinator.Listener() {
                    @Override
                    public void onProgress(int completed, int total, String name) {
                        runOnUiThread(() -> {
                            launchMessage = getString(
                                    R.string.camera_upload_progress,
                                    completed,
                                    total,
                                    name
                            );
                            refresh();
                        });
                    }

                    @Override
                    public void onComplete(CameraFtpClient.Result result, Exception failure) {
                        runOnUiThread(() -> {
                            if (failure == null && result != null) {
                                launchMessage = getResources().getQuantityString(
                                        R.plurals.camera_upload_succeeded,
                                        result.verifiedFiles,
                                        result.verifiedFiles
                                );
                            } else {
                                String detail = failure == null ? "Unknown error" : failure.getMessage();
                                launchMessage = getString(
                                        R.string.camera_upload_failed,
                                        detail == null || detail.isBlank()
                                                ? failure.getClass().getSimpleName()
                                                : detail
                                );
                            }
                            CompanionPreferences.setLastStatus(MainActivity.this, launchMessage);
                            refresh();
                        });
                    }
                }
        );
        if (!accepted) {
            launchMessage = getString(R.string.camera_upload_busy);
            refresh();
        }
    }

    private boolean hasCameraMediaPermission() {
        return CameraUploadCoordinator.hasMediaPermission(this);
    }

    private void requestCameraMediaPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
                requestPermissions(
                        new String[]{
                                Manifest.permission.READ_MEDIA_IMAGES,
                                Manifest.permission.READ_MEDIA_VIDEO,
                                Manifest.permission.READ_MEDIA_VISUAL_USER_SELECTED,
                        },
                        CAMERA_MEDIA_PERMISSION_REQUEST
                );
            } else {
                requestPermissions(
                        new String[]{
                                Manifest.permission.READ_MEDIA_IMAGES,
                                Manifest.permission.READ_MEDIA_VIDEO,
                        },
                        CAMERA_MEDIA_PERMISSION_REQUEST
                );
            }
        } else {
            requestPermissions(
                    new String[]{Manifest.permission.READ_EXTERNAL_STORAGE},
                    CAMERA_MEDIA_PERMISSION_REQUEST
            );
        }
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode,
            String[] permissions,
            int[] grantResults
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == CAMERA_MEDIA_PERMISSION_REQUEST && hasCameraMediaPermission()) {
            startCameraUpload();
        }
    }

    private void requestToggleWidget() {
        requestHomeWidget(
                SmartPlugWidgetProvider.class,
                getString(R.string.toggle_widget_name)
        );
    }

    private void requestLauncherWidget() {
        requestHomeWidget(
                ControlTowerLauncherWidgetProvider.class,
                getString(R.string.launcher_widget_name)
        );
    }

    private void requestHomeWidget(Class<?> providerClass, String widgetName) {
        AppWidgetManager manager = AppWidgetManager.getInstance(this);
        ComponentName provider = new ComponentName(this, providerClass);
        if (manager.isRequestPinAppWidgetSupported()
                && manager.requestPinAppWidget(provider, null, null)) {
            launchMessage = getString(R.string.widget_pin_requested, widgetName);
        } else {
            launchMessage = getString(R.string.widget_pin_unavailable);
        }
        refresh();
    }

    private void toggleConfiguredSmartPlugs() {
        if (toggleBusy) {
            return;
        }
        CompanionPreferences.Configuration configuration = CompanionPreferences.load(this);
        if (!configuration.isValid()) {
            launchMessage = getString(R.string.not_paired);
            refresh();
            return;
        }
        toggleBusy = true;
        launchMessage = getString(R.string.toggle_sending);
        refresh();
        controlExecutor.execute(() -> {
            UnlockClient.Result result;
            try {
                result = UnlockClient.toggle(this, configuration);
            } catch (RuntimeException error) {
                String message = error.getMessage();
                result = new UnlockClient.Result(
                        false,
                        "failed",
                        null,
                        message == null || message.isBlank()
                                ? error.getClass().getSimpleName()
                                : message
                );
            }
            UnlockClient.Result completed = result;
            runOnUiThread(() -> {
                if (isDestroyed()) {
                    return;
                }
                if (completed.accepted && Boolean.TRUE.equals(completed.on)) {
                    launchMessage = getString(R.string.toggle_on_succeeded);
                } else if (completed.accepted && Boolean.FALSE.equals(completed.on)) {
                    launchMessage = getString(R.string.toggle_off_succeeded);
                } else {
                    launchMessage = getString(
                            R.string.toggle_failed_detail,
                            completed.message
                    );
                }
                CompanionPreferences.setLastStatus(this, launchMessage);
                toggleBusy = false;
                refresh();
            });
        });
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1001);
        }
    }

    private TextView text(String value, int sizeSp, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(Color.BLACK);
        if (bold) {
            view.setTypeface(view.getTypeface(), android.graphics.Typeface.BOLD);
        }
        return view;
    }

    private Button button(String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        return button;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams buttonLayout() {
        LinearLayout.LayoutParams params = matchWrap();
        params.topMargin = dp(8);
        return params;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
