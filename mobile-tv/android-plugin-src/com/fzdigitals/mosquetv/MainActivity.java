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
    }

    /**
     * Kiosk without adb: ask the system to make this app the default home.
     * Shows the official "Set as home app" dialog — one remote press and the
     * stick boots into us forever after. Re-asked on each launch until held,
     * so declining once doesn't permanently break the kiosk setup.
     */
    private void maybeRequestHomeRole() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            RoleManager rm = getSystemService(RoleManager.class);
            if (rm != null && rm.isRoleAvailable(RoleManager.ROLE_HOME)
                    && !rm.isRoleHeld(RoleManager.ROLE_HOME)) {
                startActivityForResult(
                        rm.createRequestRoleIntent(RoleManager.ROLE_HOME),
                        REQ_HOME_ROLE);
            }
        }
    }

    /**
     * Remote Settings (gear) button: the stock launcher normally consumes this
     * key, but it is disabled in kiosk mode. Open system Settings directly so
     * Wi-Fi and network stay reachable from the remote; pressing Home returns
     * here because this app is the home activity.
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
