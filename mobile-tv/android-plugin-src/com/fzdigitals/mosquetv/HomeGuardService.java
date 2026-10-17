package com.fzdigitals.mosquetv;

import android.accessibilityservice.AccessibilityService;
import android.content.Intent;
import android.view.accessibility.AccessibilityEvent;

/**
 * Install-only kiosk enforcement: when the stock launcher (or the
 * setup wizard) comes to the foreground, immediately bring the app
 * back. The user enables this once in
 * Settings → Accessibility → Takbir Home Guard.
 *
 * Apps with a running accessibility service may start activities from
 * the background — this is the documented exemption kiosk apps rely on.
 */
public class HomeGuardService extends AccessibilityService {

    private static final String[] SUPPRESSED = {
            "com.google.android.apps.tv.launcherx",
            "com.google.android.tungsten.setupwraith",
            "com.google.android.tvrecommendations",
            "com.google.android.tv.setup",
    };

    private static final long BOUNCE_INTERVAL_MS = 1500;
    private long lastBounce = 0;

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) return;
        if (event.getEventType()
                != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return;
        String pkg = event.getPackageName().toString();
        if (!isSuppressed(pkg)) return;

        long now = System.currentTimeMillis();
        if (now - lastBounce < BOUNCE_INTERVAL_MS) return;
        lastBounce = now;

        Intent launch = new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                        | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT
                        | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        try {
            startActivity(launch);
        } catch (Exception ignored) {
        }
    }

    private boolean isSuppressed(String pkg) {
        for (String s : SUPPRESSED) {
            if (s.equals(pkg)) return true;
        }
        return false;
    }

    @Override
    public void onInterrupt() {
    }
}
