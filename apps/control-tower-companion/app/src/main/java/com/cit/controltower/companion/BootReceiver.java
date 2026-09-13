package com.cit.controltower.companion;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(action)
                && !Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)) {
            return;
        }
        CompanionPreferences.Configuration configuration = CompanionPreferences.load(context);
        if (configuration.isValid() && CompanionPreferences.isLocalEnabled(context)) {
            UnlockMonitorService.start(context);
        }
    }
}
