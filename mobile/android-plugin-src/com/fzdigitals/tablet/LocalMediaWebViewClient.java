package com.fzdigitals.tablet;

import android.net.Uri;
import android.webkit.MimeTypeMap;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;
import java.io.File;
import java.io.FileInputStream;
import java.net.URLConnection;

public class LocalMediaWebViewClient extends BridgeWebViewClient {
    private static final String LOCAL_HOST = "media.fzscreens.com";
    private static final String LOCAL_PATH = "/tablet-local/";
    private final File base;

    public LocalMediaWebViewClient(Bridge bridge, File base) {
        super(bridge);
        this.base = base;
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri url = request.getUrl();
        if (LOCAL_HOST.equals(url.getHost()) && url.getPath() != null && url.getPath().startsWith(LOCAL_PATH)) {
            String name = url.getPath().substring(LOCAL_PATH.length());
            File file = new File(base, name);
            if (file.exists() && file.isFile()) {
                String mime = URLConnection.guessContentTypeFromName(file.getName());
                if (mime == null || mime.isEmpty()) {
                    String ext = MimeTypeMap.getFileExtensionFromUrl(file.getName());
                    if (ext != null) {
                        mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase());
                    }
                    if (mime == null || mime.isEmpty()) {
                        mime = "application/octet-stream";
                    }
                }
                try {
                    return new WebResourceResponse(mime, null, new FileInputStream(file));
                } catch (Exception e) {
                    // fall through to default handling
                }
            }
        }
        return super.shouldInterceptRequest(view, request);
    }
}
