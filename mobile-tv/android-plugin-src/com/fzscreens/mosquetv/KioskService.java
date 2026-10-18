package com.fzscreens.mosquetv;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

/**
 * Short-lived foreground service used as a fallback launcher after
 * boot: on builds where the boot broadcast can't open an activity
 * directly, this service retries a few times then exits.
 */
public class KioskService extends Service {
    private static final String CHANNEL_ID = "kiosk";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private int attempts = 0;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        ensureChannel();
        Notification n = new Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Mosque TV")
                .setContentText("Starting…")
                .setSmallIcon(android.R.drawable.stat_notify_more)
                .build();
        try {
            startForeground(1, n);
        } catch (Exception ignored) {
            // Type/permission enforcement varies by build — retries continue.
        }
        retry();
        return START_NOT_STICKY;
    }

    private void retry() {
        if (attempts++ >= 5) {
            stopSelf();
            return;
        }
        Intent launch = new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                        | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
        try {
            startActivity(launch);
        } catch (Exception ignored) {
        }
        handler.postDelayed(this::retry, 10_000);
    }

    private void ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel c = new NotificationChannel(
                    CHANNEL_ID, "Kiosk", NotificationManager.IMPORTANCE_MIN);
            NotificationManager nm = (NotificationManager)
                    getSystemService(Context.NOTIFICATION_SERVICE);
            if (nm != null) nm.createNotificationChannel(c);
        }
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
