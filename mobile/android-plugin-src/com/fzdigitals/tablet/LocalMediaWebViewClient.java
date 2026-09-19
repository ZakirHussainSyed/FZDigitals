package com.fzdigitals.tablet;

import android.net.Uri;
import android.webkit.MimeTypeMap;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebView;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;
import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import android.util.Log;

public class LocalMediaWebViewClient extends BridgeWebViewClient {
    private static final String TAG = "LocalMediaWebViewClient";
    private static final String LOCAL_HOST = "media.fzscreens.com";
    private static final String LOCAL_PATH = "/tablet-local/";
    private final Bridge bridgeRef;
    private final File base;

    public LocalMediaWebViewClient(Bridge bridge, File base) {
        super(bridge);
        this.bridgeRef = bridge;
        this.base = base;
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri url = request.getUrl();
        if (LOCAL_HOST.equals(url.getHost()) && url.getPath() != null && url.getPath().startsWith(LOCAL_PATH)) {
            String name = url.getPath().substring(LOCAL_PATH.length());
            File file = new File(base, name);
            String method = request.getMethod() != null ? request.getMethod() : "GET";
            jsLog(url, file, "request", null);
            if (!file.exists() || !file.isFile()) {
                jsLog(url, file, "missing", "not found");
                Log.i(TAG, "missing file: " + file.getAbsolutePath());
                return plainTextResponse(404, "Not Found", "Not found: " + name);
            }
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
            long total = file.length();
            String range = request.getRequestHeaders().get("Range");
            Log.i(TAG, "request " + method + " " + url + " range=" + range + " mime=" + mime + " total=" + total + " headers=" + request.getRequestHeaders());
            if ("OPTIONS".equals(method)) {
                return corsResponse(mime, 0, new ByteArrayInputStream(new byte[0]), 204, "No Content", null);
            }
            if ("HEAD".equals(method)) {
                return corsResponse(mime, total, new ByteArrayInputStream(new byte[0]), 200, "OK", null);
            }
            try {
                if (range != null && range.startsWith("bytes=")) {
                    String spec = range.substring(6);
                    int comma = spec.indexOf(',');
                    if (comma >= 0) spec = spec.substring(0, comma).trim();
                    String[] parts = spec.split("-", -1);
                    long start;
                    long end = total - 1;
                    if (!parts[0].isEmpty()) {
                        start = Long.parseLong(parts[0]);
                        if (parts.length > 1 && !parts[1].isEmpty()) {
                            end = Long.parseLong(parts[1]);
                        }
                    } else if (parts.length > 1 && !parts[1].isEmpty()) {
                        long suffix = Long.parseLong(parts[1]);
                        start = Math.max(0, total - suffix);
                    } else {
                        start = 0;
                    }
                    if (end >= total) end = total - 1;
                    if (start < 0 || start >= total || end < start) {
                        Map<String, String> headers = corsHeaders(mime, 0);
                        headers.put("Content-Range", "bytes */" + total);
                        jsLog(url, file, "serving-416", null);
                        Log.i(TAG, "serving-416 range=" + range + " total=" + total);
                        return new WebResourceResponse(mime, null, 416, "Requested Range Not Satisfiable", headers, new ByteArrayInputStream(new byte[0]));
                    }
                    // Always answer range requests with 206, including "bytes=0-".
                    // Replying 200 to a range probe tells the media stack the resource
                    // is not seekable, and mixing 200/206 responses makes it retry.
                    long length = end - start + 1;
                    FileInputStream fis = new FileInputStream(file);
                    fis.getChannel().position(start);
                    Map<String, String> headers = corsHeaders(mime, length);
                    headers.put("Content-Range", "bytes " + start + "-" + end + "/" + total);
                    jsLog(url, file, "serving-206", null);
                    Log.i(TAG, "serving-206 start=" + start + " end=" + end + " length=" + length + " total=" + total + " mime=" + mime);
                    return new WebResourceResponse(mime, null, 206, "Partial Content", headers, new BoundedInputStream(fis, length));
                }
                jsLog(url, file, "serving-200", null);
                Log.i(TAG, "serving-200 total=" + total + " mime=" + mime);
                return corsResponse(mime, total, new FileInputStream(file), 200, "OK", null);
            } catch (Exception e) {
                Log.w(TAG, "error serving " + file.getAbsolutePath(), e);
                jsLog(url, file, "error", e.getMessage());
                return plainTextResponse(500, "Internal Server Error", "Server error: " + e.getMessage());
            }
        }
        return super.shouldInterceptRequest(view, request);
    }

    private void jsLog(Uri url, File file, String action, String error) {
        StringBuilder detail = new StringBuilder();
        detail.append("{");
        detail.append("\"url\":\"").append(escape(url.toString())).append("\",");
        detail.append("\"path\":\"").append(escape(file != null ? file.getAbsolutePath() : "")).append("\",");
        detail.append("\"exists\":").append(file != null && file.exists()).append(",");
        detail.append("\"size\":").append(file != null ? file.length() : 0).append(",");
        detail.append("\"action\":\"").append(escape(action)).append("\",");
        detail.append("\"error\":\"").append(escape(error != null ? error : "")).append("\"");
        detail.append("}");
        final String js = "window.dispatchEvent(new CustomEvent('localMediaLog',{detail:" + detail.toString() + "}));";
        bridgeRef.getWebView().post(() -> bridgeRef.getWebView().evaluateJavascript(js, null));
    }

    private String escape(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r");
    }

    private Map<String, String> corsHeaders(String mime, long length) {
        Map<String, String> headers = new HashMap<>();
        headers.put("Content-Type", mime);
        headers.put("Access-Control-Allow-Origin", "*");
        headers.put("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
        headers.put("Accept-Ranges", "bytes");
        headers.put("Content-Length", String.valueOf(length));
        // The mtime query param busts cache on change, so let the WebView cache the
        // response. This is needed for large videos, otherwise the media stack cannot
        // write them to disk and playback fails.
        headers.put("Cache-Control", "public, max-age=31536000, immutable");
        return headers;
    }

    private WebResourceResponse corsResponse(String mime, long length, InputStream body, int code, String reason, Map<String, String> extra) {
        Map<String, String> headers = corsHeaders(mime, length);
        if (extra != null) headers.putAll(extra);
        return new WebResourceResponse(mime, null, code, reason, headers, body);
    }

    private WebResourceResponse plainTextResponse(int code, String reason, String body) {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        Map<String, String> headers = new HashMap<>();
        headers.put("Content-Type", "text/plain; charset=utf-8");
        headers.put("Access-Control-Allow-Origin", "*");
        headers.put("Content-Length", String.valueOf(bytes.length));
        headers.put("Cache-Control", "no-store, no-cache, must-revalidate");
        return new WebResourceResponse("text/plain", "utf-8", code, reason, headers, new ByteArrayInputStream(bytes));
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
