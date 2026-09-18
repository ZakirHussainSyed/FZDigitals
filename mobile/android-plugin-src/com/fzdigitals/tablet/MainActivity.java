package com.fzdigitals.tablet;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
import com.fzdigitals.tablet.plugins.MediaDownloaderPlugin;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(MediaDownloaderPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
