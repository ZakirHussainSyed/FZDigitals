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

    // Built at bind: every package that offers a HOME activity — covers
    // Google TV (launcherx), Android TV (tvlauncher), Fire TV
    // (com.amazon.tv.launcher), AOSP boxes (launcher3 / vendor launchers)
    // and setup wizards — without hardcoding per-device names.
    private java.util.Set<String> suppressed = new java.util.HashSet<>();

    private void buildSuppressed() {
        Intent home = new Intent(Intent.ACTION_MAIN)
                .addCategory(Intent.CATEGORY_HOME);
        for (android.content.pm.ResolveInfo ri : getPackageManager()
                .queryIntentActivities(home, 0)) {
            if (ri.activityInfo != null
                    && ri.activityInfo.packageName != null
                    && !ri.activityInfo.packageName
                            .equals(getPackageName())) {
                suppressed.add(ri.activityInfo.packageName);
            }
        }
    }

    // Only bounce real home/recovery screens. Panels like the launcherx
    // quick-settings dropdown share the suppressed package name but a
    // different window class — bouncing those kills Wi-Fi/settings UI.
    private static final String[] HOME_CLASS_HINTS = {
            "HomeActivity", "RecoveryActivity", "DeferredActivity",
    };

    private static final long BOUNCE_INTERVAL_MS = 1500;
    private long lastBounce = 0;

    // Last window class seen per suppressed package — lets the watchdog
    // tell "home screen" apart from a transient panel (quick settings).
    private final java.util.Map<String, String> lastClassByPkg =
            new java.util.HashMap<>();

    /**
     * Bind happens after the launcher is already front-most (boot),
     * so no window event ever fires — inspect the current window
     * directly and re-check while the launcher settles, then keep a
     * slow watchdog so any later launcher appearance also recovers.
     */
    @Override
    protected void onServiceConnected() {
        buildSuppressed();
        checkForegroundNow();
        final android.os.Handler h = new android.os.Handler(getMainLooper());
        h.postDelayed(this::checkForegroundNow, 3_000);
        h.postDelayed(this::checkForegroundNow, 10_000);
        h.postDelayed(this::checkForegroundNow, 30_000);
        h.postDelayed(new Runnable() {
            @Override
            public void run() {
                checkForegroundNow();
                h.postDelayed(this, 15_000);
            }
        }, 15_000);
    }

    private void checkForegroundNow() {
        android.view.accessibility.AccessibilityNodeInfo root =
                getRootInActiveWindow();
        if (root == null || root.getPackageName() == null) return;
        String pkg = root.getPackageName().toString();
        if (!isSuppressed(pkg)) return;
        String cls = lastClassByPkg.get(pkg);
        // No event ever recorded (fresh boot, launcher already front) or
        // last event was the home activity itself — bounce. A non-home
        // class means a panel (e.g. quick settings) is open: leave it.
        if (cls == null || isHomeClass(cls)) {
            bounce();
        }
    }

    private void bounce() {
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

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) return;
        if (event.getEventType()
                != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return;
        String pkg = event.getPackageName().toString();
        if (!isSuppressed(pkg)) return;
        if (event.getClassName() != null) {
            lastClassByPkg.put(pkg, event.getClassName().toString());
        }
        if (event.getClassName() != null
                && !isHomeClass(event.getClassName().toString())) return;
        bounce();
    }

    private boolean isHomeClass(String cls) {
        for (String hint : HOME_CLASS_HINTS) {
            if (cls.contains(hint)) return true;
        }
        return false;
    }

    private boolean isSuppressed(String pkg) {
        return suppressed.contains(pkg);
    }

    @Override
    public void onInterrupt() {
    }
}
