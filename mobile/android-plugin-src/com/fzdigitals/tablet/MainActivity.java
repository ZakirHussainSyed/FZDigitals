package com.fzdigitals.tablet;

import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.webkit.WebSettings;
import com.getcapacitor.BridgeActivity;
import com.fzdigitals.tablet.plugins.MediaDownloaderPlugin;
import java.io.File;

public class MainActivity extends BridgeActivity {
    private static final String TAG = "MainActivity";
    private static final String PREFS = "app_cache";
    private static final String KEY_VERSION_CODE = "version_code";

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(MediaDownloaderPlugin.class);
        super.onCreate(savedInstanceState);

        WebSettings settings = bridge.getWebView().getSettings();
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        settings.setAllowFileAccess(true);
        settings.setAllowFileAccessFromFileURLs(true);
        settings.setAllowUniversalAccessFromFileURLs(true);

        clearCacheOnUpgrade();

        File base = new File(getFilesDir(), "slideshow");
        bridge.getWebView().setWebViewClient(new LocalMediaWebViewClient(bridge, base));
    }

    /**
     * Clears the WebView HTTP cache only when the installed app version changes,
     * so normal reopens keep cached pages/media and work on flaky networks.
     */
    private void clearCacheOnUpgrade() {
        try {
            PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
            long version = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
                ? info.getLongVersionCode()
                : info.versionCode;
            SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
            long seen = prefs.getLong(KEY_VERSION_CODE, -1);
            if (seen != version) {
                bridge.getWebView().clearCache(true);
                prefs.edit().putLong(KEY_VERSION_CODE, version).apply();
                Log.i(TAG, "app version changed " + seen + " -> " + version + ", cleared WebView cache");
            }
        } catch (Exception e) {
            Log.w(TAG, "version check failed; leaving WebView cache intact", e);
        }
    }
}
