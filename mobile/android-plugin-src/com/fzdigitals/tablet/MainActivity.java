package com.fzdigitals.tablet;

import android.os.Bundle;
import android.webkit.WebSettings;
import com.getcapacitor.BridgeActivity;
import com.fzdigitals.tablet.plugins.MediaDownloaderPlugin;
import java.io.File;

public class MainActivity extends BridgeActivity {
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

        File base = new File(getFilesDir(), "slideshow");
        bridge.getWebView().setWebViewClient(new LocalMediaWebViewClient(bridge, base));
    }
}
