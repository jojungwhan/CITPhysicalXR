package com.cit.controltower.companion;

import android.app.KeyguardManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.view.View;
import android.widget.RemoteViews;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SmartPlugWidgetProvider extends AppWidgetProvider {
    private static final String ACTION_SET_POWER =
            "com.cit.controltower.companion.action.SET_SITE_POWER";
    private static final String EXTRA_DEVICE_ID = "device_id";
    private static final String EXTRA_ON = "on";
    private static final ExecutorService EXECUTOR = Executors.newFixedThreadPool(2);
    private static final AtomicBoolean BUSY = new AtomicBoolean();

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] appWidgetIds) {
        int status = CompanionPreferences.loadAll(context).isEmpty()
                ? R.string.widget_not_paired
                : R.string.widget_ready;
        for (int appWidgetId : appWidgetIds) {
            manager.updateAppWidget(appWidgetId, views(context, status));
        }
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        if (!ACTION_SET_POWER.equals(intent.getAction()) || !BUSY.compareAndSet(false, true)) {
            return;
        }
        String requestedDeviceId = intent.getStringExtra(EXTRA_DEVICE_ID);
        boolean on = intent.getBooleanExtra(EXTRA_ON, false);
        CompanionPreferences.Configuration configuration = findConfiguration(
                context,
                requestedDeviceId
        );
        if (!configuration.isValid()) {
            BUSY.set(false);
            updateAll(context, R.string.widget_not_paired);
            return;
        }
        KeyguardManager keyguard = (KeyguardManager) context.getSystemService(
                Context.KEYGUARD_SERVICE
        );
        if (keyguard == null || !keyguard.isDeviceSecure()) {
            BUSY.set(false);
            updateAll(context, R.string.widget_lock_required);
            return;
        }

        PendingResult pending = goAsync();
        updateAll(context, R.string.widget_sending);
        Context applicationContext = context.getApplicationContext();
        EXECUTOR.execute(() -> {
            int status = R.string.widget_failed;
            try {
                RemotePlugClient.PowerResult result = RemotePlugClient.setPower(
                        applicationContext,
                        configuration,
                        on
                );
                if (result.accepted) {
                    status = result.on
                            ? R.string.widget_turned_on
                            : R.string.widget_turned_off;
                }
                CompanionPreferences.setLastStatus(
                        applicationContext,
                        configuration,
                        result.message
                );
            } catch (RuntimeException ignored) {
                CompanionPreferences.setLastStatus(
                        applicationContext,
                        configuration,
                        applicationContext.getString(R.string.widget_failed)
                );
            } finally {
                updateAll(applicationContext, status);
                BUSY.set(false);
                pending.finish();
            }
        });
    }

    static void refreshAll(Context context) {
        int status = CompanionPreferences.loadAll(context).isEmpty()
                ? R.string.widget_not_paired
                : R.string.widget_ready;
        updateAll(context, status);
    }

    private static CompanionPreferences.Configuration findConfiguration(
            Context context,
            String deviceId
    ) {
        if (deviceId == null) {
            return CompanionPreferences.Configuration.empty();
        }
        for (CompanionPreferences.Configuration configuration
                : CompanionPreferences.loadAll(context)) {
            if (configuration.deviceId.equals(deviceId)) {
                return configuration;
            }
        }
        return CompanionPreferences.Configuration.empty();
    }

    private static void updateAll(Context context, int status) {
        AppWidgetManager manager = AppWidgetManager.getInstance(context);
        ComponentName provider = new ComponentName(context, SmartPlugWidgetProvider.class);
        int[] ids = manager.getAppWidgetIds(provider);
        for (int id : ids) {
            manager.updateAppWidget(id, views(context, status));
        }
    }

    private static RemoteViews views(Context context, int status) {
        RemoteViews views = new RemoteViews(context.getPackageName(), R.layout.smart_plug_widget);
        List<CompanionPreferences.Configuration> configurations =
                CompanionPreferences.loadAll(context);
        bindSite(
                context,
                views,
                configurations,
                0,
                R.id.widget_site_one,
                R.id.widget_site_one_name,
                R.id.widget_site_one_on,
                R.id.widget_site_one_off
        );
        bindSite(
                context,
                views,
                configurations,
                1,
                R.id.widget_site_two,
                R.id.widget_site_two_name,
                R.id.widget_site_two_on,
                R.id.widget_site_two_off
        );
        if (configurations.size() > 2 && status == R.string.widget_ready) {
            views.setTextViewText(
                    R.id.widget_status,
                    context.getResources().getQuantityString(
                            R.plurals.widget_site_more,
                            configurations.size() - 2,
                            configurations.size() - 2
                    )
            );
        } else {
            views.setTextViewText(R.id.widget_status, context.getString(status));
        }
        return views;
    }

    private static void bindSite(
            Context context,
            RemoteViews views,
            List<CompanionPreferences.Configuration> configurations,
            int index,
            int rowId,
            int nameId,
            int onId,
            int offId
    ) {
        if (index >= configurations.size()) {
            views.setViewVisibility(rowId, View.GONE);
            return;
        }
        CompanionPreferences.Configuration configuration = configurations.get(index);
        views.setViewVisibility(rowId, View.VISIBLE);
        views.setTextViewText(nameId, configuration.siteName);
        views.setOnClickPendingIntent(
                onId,
                powerIntent(context, configuration.deviceId, true)
        );
        views.setOnClickPendingIntent(
                offId,
                powerIntent(context, configuration.deviceId, false)
        );
    }

    private static PendingIntent powerIntent(Context context, String deviceId, boolean on) {
        String action = on ? "on" : "off";
        Intent intent = new Intent(context, SmartPlugWidgetProvider.class)
                .setAction(ACTION_SET_POWER)
                .setData(Uri.parse("cit-control-tower://widget/" + deviceId + "/" + action))
                .putExtra(EXTRA_DEVICE_ID, deviceId)
                .putExtra(EXTRA_ON, on);
        return PendingIntent.getBroadcast(
                context,
                (deviceId + ":" + action).hashCode(),
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
    }
}
