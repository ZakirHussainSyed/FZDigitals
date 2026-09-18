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
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URLConnection;
import java.util.HashMap;
import java.util.Map;
import android.util.Log;

public class LocalMediaWebViewClient extends BridgeWebViewClient {
    private static final String TAG = "LocalMediaWebViewClient";
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
        Log.i(TAG, "request " + url.toString());
        if (LOCAL_HOST.equals(url.getHost()) && url.getPath() != null && url.getPath().startsWith(LOCAL_PATH)) {
            String name = url.getPath().substring(LOCAL_PATH.length());
            File file = new File(base, name);
            Log.i(TAG, "resolved " + file.getAbsolutePath() + " exists=" + file.exists() + " size=" + file.length());
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
                    Log.i(TAG, "serving " + file.getAbsolutePath() + " size=" + file.length());
                    long total = file.length();
                    String range = request.getRequestHeaders().get("Range");
                    if (range != null && range.startsWith("bytes=")) {
                        String[] parts = range.substring(6).split("-");
                        long start = Long.parseLong(parts[0]);
                        long end = total - 1;
                        if (parts.length > 1 && !parts[1].isEmpty()) {
                            end = Long.parseLong(parts[1]);
                        }
                        if (end >= total) end = total - 1;
                        if (start < 0 || start >= total || end < start) {
                            Map<String, String> err = new HashMap<>();
                            err.put("Content-Range", "bytes */" + total);
                            return new WebResourceResponse(mime, null, 416, "Range Not Satisfiable", err, null);
                        }
                        long length = end - start + 1;
                        FileInputStream fis = new FileInputStream(file);
                        fis.getChannel().position(start);
                        Map<String, String> headers = new HashMap<>();
                        headers.put("Content-Type", mime);
                        headers.put("Accept-Ranges", "bytes");
                        headers.put("Content-Length", String.valueOf(length));
                        headers.put("Content-Range", "bytes " + start + "-" + end + "/" + total);
                        headers.put("Cache-Control", "no-store, no-cache, must-revalidate");
                        headers.put("Pragma", "no-cache");
                        headers.put("Expires", "0");
                        return new WebResourceResponse(mime, null, 206, "Partial Content", headers, new BoundedInputStream(fis, length));
                    }
                    Map<String, String> headers = new HashMap<>();
                    headers.put("Content-Type", mime);
                    headers.put("Accept-Ranges", "bytes");
                    headers.put("Content-Length", String.valueOf(total));
                    headers.put("Cache-Control", "no-store, no-cache, must-revalidate");
                    headers.put("Pragma", "no-cache");
                    headers.put("Expires", "0");
                    return new WebResourceResponse(mime, null, 200, "OK", headers, new FileInputStream(file));
                } catch (Exception e) {
                    // fall through to default handling
                }
            } else {
                Log.w(TAG, "missing " + file.getAbsolutePath() + " for " + url.toString());
            }
        }
        return super.shouldInterceptRequest(view, request);
    }

    private static class BoundedInputStream extends FilterInputStream {
        private long remaining;

        BoundedInputStream(InputStream in, long length) {
            super(in);
            this.remaining = length;
        }

        @Override
        public int read() throws IOException {
            if (remaining <= 0) return -1;
            int b = in.read();
            if (b >= 0) remaining--;
            return b;
        }

        @Override
        public int read(byte[] b, int off, int len) throws IOException {
            if (remaining <= 0) return -1;
            int toRead = (int) Math.min(len, remaining);
            int n = in.read(b, off, toRead);
            if (n > 0) remaining -= n;
            return n;
        }

        @Override
        public long skip(long n) throws IOException {
            long toSkip = Math.min(n, remaining);
            long skipped = super.skip(toSkip);
            remaining -= skipped;
            return skipped;
        }

        @Override
        public int available() throws IOException {
            return (int) Math.min(super.available(), remaining);
        }
    }
}
