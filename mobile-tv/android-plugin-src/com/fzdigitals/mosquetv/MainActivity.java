package com.fzdigitals.mosquetv;

import android.os.Bundle;
import android.webkit.WebSettings;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(MediaDownloaderPlugin.class);
        super.onCreate(savedInstanceState);

        WebSettings settings = bridge.getWebView().getSettings();
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        // Muted slideshow videos must autoplay; on TV there is no user gesture.
        settings.setMediaPlaybackRequiresUserGesture(false);

        bridge.getWebView().setWebViewClient(
                new MosqueWebViewClient(bridge, getFilesDir()));
    }
}
