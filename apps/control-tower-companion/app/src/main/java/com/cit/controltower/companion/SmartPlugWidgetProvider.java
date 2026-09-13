package com.cit.controltower.companion;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

public final class SmartPlugWidgetProvider extends AppWidgetProvider {
    private static final String ACTION_TOGGLE =
            "com.cit.controltower.companion.action.TOGGLE_SMART_PLUGS";
    private static final ExecutorService EXECUTOR = Executors.newSingleThreadExecutor();
    private static final AtomicBoolean BUSY = new AtomicBoolean();

    @Override
    public void onUpdate(Context context, AppWidgetManager manager, int[] appWidgetIds) {
        int status = CompanionPreferences.load(context).isValid()
                ? R.string.widget_ready
                : R.string.widget_not_paired;
        for (int appWidgetId : appWidgetIds) {
            manager.updateAppWidget(appWidgetId, views(context, status));
        }
    }

    @Override
    public void onReceive(Context context, Intent intent) {
        super.onReceive(context, intent);
        if (!ACTION_TOGGLE.equals(intent.getAction()) || !BUSY.compareAndSet(false, true)) {
            return;
        }
        PendingResult pending = goAsync();
        updateAll(context, R.string.widget_sending);
        Context applicationContext = context.getApplicationContext();
        EXECUTOR.execute(() -> {
            int status = R.string.widget_failed;
            try {
                CompanionPreferences.Configuration configuration =
                        CompanionPreferences.load(applicationContext);
                if (!configuration.isValid()) {
                    status = R.string.widget_not_paired;
                } else {
                    UnlockClient.Result result = UnlockClient.toggle(
                            applicationContext,
                            configuration
                    );
                    if (result.accepted && Boolean.TRUE.equals(result.on)) {
                        status = R.string.widget_turned_on;
                    } else if (result.accepted && Boolean.FALSE.equals(result.on)) {
                        status = R.string.widget_turned_off;
                    }
                    CompanionPreferences.setLastStatus(applicationContext, result.message);
                }
            } catch (RuntimeException ignored) {
                CompanionPreferences.setLastStatus(
                        applicationContext,
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
        int status = CompanionPreferences.load(context).isValid()
                ? R.string.widget_ready
                : R.string.widget_not_paired;
        updateAll(context, status);
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
        views.setTextViewText(R.id.widget_status, context.getString(status));
        Intent toggle = new Intent(context, SmartPlugWidgetProvider.class)
                .setAction(ACTION_TOGGLE);
        PendingIntent action = PendingIntent.getBroadcast(
                context,
                0,
                toggle,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        views.setOnClickPendingIntent(R.id.widget_toggle, action);
        return views;
    }
}
