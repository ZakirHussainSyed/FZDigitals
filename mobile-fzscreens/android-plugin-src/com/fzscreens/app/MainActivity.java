package com.fzscreens.app;

import android.os.Bundle;
import android.webkit.WebSettings;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        WebSettings settings = bridge.getWebView().getSettings();
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        bridge.getWebView().setWebViewClient(
                new SiteWebViewClient(bridge, getFilesDir()));

        UpdateChecker.schedule(this);
    }

    @Override
    public void onResume() {
        super.onResume();
        // If an OTA confirm sheet was blocked while the app was
        // frozen/backgrounded, surface it now.
        UpdateChecker.showPendingConfirm(this);
    }
}
