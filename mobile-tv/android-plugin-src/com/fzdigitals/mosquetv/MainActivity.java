package com.fzdigitals.mosquetv;

import android.app.role.RoleManager;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.KeyEvent;
import android.view.WindowManager;
import android.webkit.WebSettings;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private static final int REQ_HOME_ROLE = 42;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(MediaDownloaderPlugin.class);
        super.onCreate(savedInstanceState);

        // Keep the screen on while the app is foregrounded — Android/Google TV
        // ambient screensaver never engages. Auto-released when the app leaves
        // the foreground, so no WAKE_LOCK permission is needed.
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        WebSettings settings = bridge.getWebView().getSettings();
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        // Muted slideshow videos must autoplay; on TV there is no user gesture.
        settings.setMediaPlaybackRequiresUserGesture(false);

        bridge.getWebView().setWebViewClient(
                new MosqueWebViewClient(bridge, getFilesDir()));

        maybeRequestHomeRole();
        UpdateChecker.schedule(this);
    }

    @Override
    protected void onResume() {
        super.onResume();
        // If an OTA confirm sheet was blocked while the app was
        // frozen/backgrounded, surface it now.
        UpdateChecker.showPendingConfirm(this);
    }

    /**
     * Kiosk without adb: make sure this app is the default home. Prefer the
     * official role dialog (one remote press). On firmware where the HOME
     * role grant doesn't actually change routing (Google TV Onn builds),
     * fall back to enabling the accessibility Home Guard — it bounces any
     * other home app back to us and needs no adb, no commands, no disable.
     */
    private void maybeRequestHomeRole() {
        if (isDefaultHome()) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            RoleManager rm = getSystemService(RoleManager.class);
            if (rm != null && rm.isRoleAvailable(RoleManager.ROLE_HOME)
                    && !rm.isRoleHeld(RoleManager.ROLE_HOME)) {
                startActivityForResult(
                        rm.createRequestRoleIntent(RoleManager.ROLE_HOME),
                        REQ_HOME_ROLE);
                return;
            }
        }
        // Role grant didn't move HOME routing — offer the guard toggle.
        if (!isGuardEnabled()) {
            try {
                startActivity(new Intent(
                        Settings.ACTION_ACCESSIBILITY_SETTINGS));
            } catch (android.content.ActivityNotFoundException ignored) {
            }
        }
    }

    /** True while the user has enabled our accessibility Home Guard. */
    private boolean isGuardEnabled() {
        String enabled = Settings.Secure.getString(getContentResolver(),
                Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        return enabled != null && enabled.contains("HomeGuardService");
    }

    /** True when Android resolves the HOME intent to us. */
    private boolean isDefaultHome() {
        Intent home = new Intent(Intent.ACTION_MAIN)
                .addCategory(Intent.CATEGORY_HOME);
        android.content.pm.ResolveInfo ri = getPackageManager()
                .resolveActivity(home,
                        android.content.pm.PackageManager.MATCH_DEFAULT_ONLY);
        return ri != null && ri.activityInfo != null
                && getPackageName().equals(ri.activityInfo.packageName);
    }

    /**
     * Remote Settings (gear) button: open system Settings directly so Wi-Fi
     * and network stay reachable from the remote even in kiosk mode. With the
     * Home Guard enabled, returning bounces back to this app automatically.
     */
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getAction() == KeyEvent.ACTION_UP
                && event.getKeyCode() == KeyEvent.KEYCODE_SETTINGS) {
            startActivity(new Intent(Settings.ACTION_SETTINGS));
            return true;
        }
        return super.dispatchKeyEvent(event);
    }
}
