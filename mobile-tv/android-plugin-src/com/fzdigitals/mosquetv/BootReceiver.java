package com.fzdigitals.mosquetv;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

/**
 * Relaunches the app a few seconds after boot so the stick powers
 * straight into the kiosk with no launcher involved.
 */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(final Context ctx, Intent intent) {
        if (intent == null) return;
        String a = intent.getAction();
        if (!Intent.ACTION_BOOT_COMPLETED.equals(a)
                && !"android.intent.action.QUICKBOOT_POWERON".equals(a)) {
            return;
        }
        // Give the system + Wi-Fi a moment, then open the app.
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            Intent launch = new Intent(ctx, MainActivity.class)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            try {
                ctx.startActivity(launch);
            } catch (Exception ignored) {
            }
            // Belt-and-suspenders: a foreground service that retries.
            Intent svc = new Intent(ctx, KioskService.class);
            try {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    ctx.startForegroundService(svc);
                } else {
                    ctx.startService(svc);
                }
            } catch (Exception ignored) {
            }
        }, 8000);
    }
}
