package com.fzdigitals.tablet;

import android.net.Uri;
import android.webkit.MimeTypeMap;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeWebViewClient;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import android.util.Log;

public class LocalMediaWebViewClient extends BridgeWebViewClient {
    private static final String TAG = "LocalMediaWebViewClient";
    private static final String LOCAL_HOST = "media.fzscreens.com";
    private static final String LOCAL_PATH = "/tablet-local/";
    private static final String APP_HOST = "www.fzscreens.com";
    private static final String APP_HOST_ALT = "fzscreens.com";
    private final Bridge bridgeRef;
    private final File base;
    private boolean triedCacheFallback = false;

    public LocalMediaWebViewClient(Bridge bridge, File base) {
        super(bridge);
        this.bridgeRef = bridge;
        this.base = base;
    }

    /**
     * If the main page fails to load (offline, server down, flaky DNS), retry
     * once from the WebView HTTP cache so the app shell still comes up and can
     * play locally synced media. The page is served with Cache-Control:
     * no-cache, so online loads always revalidate — this only kicks in when
     * the network load itself fails.
     */
    @Override
    public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
        if (request.isForMainFrame() && !triedCacheFallback) {
            triedCacheFallback = true;
            Log.i(TAG, "main frame load failed (" + error.getDescription() + "), retrying from cache");
            view.getSettings().setCacheMode(WebSettings.LOAD_CACHE_ELSE_NETWORK);
            view.loadUrl(request.getUrl().toString());
            return;
        }
        super.onReceivedError(view, request, error);
    }

    @Override
    public void onPageFinished(WebView view, String url) {
        // Restore normal revalidation so API fetches and future page loads
        // always hit the network when it's available.
        view.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
        super.onPageFinished(view, url);
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri url = request.getUrl();
        String method = request.getMethod() != null ? request.getMethod() : "GET";
        if (LOCAL_HOST.equals(url.getHost()) && url.getPath() != null && url.getPath().startsWith(LOCAL_PATH)) {
            String name = url.getPath().substring(LOCAL_PATH.length());
            File file = new File(base, name);
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
        // App shell + static assets: fetch through our own disk snapshot so the
        // app can launch offline. Every successful online load refreshes the
        // snapshot; any failure serves the last good copy. This does not depend
        // on the WebView HTTP cache or server cache headers.
        if (isAppShellRequest(url, request, method)) {
            WebResourceResponse res = fetchThroughCache(view, request, url);
            if (res != null) return res;
        }
        return super.shouldInterceptRequest(view, request);
    }

    private boolean isAppShellRequest(Uri url, WebResourceRequest request, String method) {
        if (!"GET".equals(method)) return false;
        String host = url.getHost();
        if (!APP_HOST.equals(host) && !APP_HOST_ALT.equals(host)) return false;
        if (request.isForMainFrame()) return true;
        String path = url.getPath();
        return path != null && (path.startsWith("/static/") || path.equals("/manifest.webmanifest"));
    }

    /**
     * GET the resource ourselves: on success store a copy under
     * filesDir/webcache and return it; on any failure serve the stored copy.
     * Returns null only when there is no network AND no snapshot.
     */
    private WebResourceResponse fetchThroughCache(WebView view, WebResourceRequest request, Uri url) {
        File cacheFile = cacheFileFor(url);
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(url.toString()).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(15000);
            conn.setInstanceFollowRedirects(true);
            conn.setRequestProperty("Accept-Encoding", "identity");
            // Mirror the WebView's own request so CDN/bot protection sees the
            // same client — otherwise our fetch can get a challenge page while
            // the WebView load would have succeeded, and no snapshot is saved.
            String ua = view.getSettings().getUserAgentString();
            if (ua != null) conn.setRequestProperty("User-Agent", ua);
            Map<String, String> reqHeaders = request.getRequestHeaders();
            if (reqHeaders != null) {
                for (Map.Entry<String, String> h : reqHeaders.entrySet()) {
                    String k = h.getKey();
                    if (k == null || h.getValue() == null) continue;
                    String lk = k.toLowerCase(Locale.US);
                    if (lk.equals("host") || lk.equals("connection") || lk.equals("accept-encoding") || lk.equals("user-agent")) continue;
                    conn.setRequestProperty(k, h.getValue());
                }
            }
            int code = conn.getResponseCode();
            if (code >= 200 && code < 300) {
                byte[] body = readFully(conn.getInputStream(), 8 * 1024 * 1024);
                if (body != null && body.length > 0) {
                    writeAtomic(cacheFile, body);
                    Log.i(TAG, "snapshot saved " + cacheFile.getName() + " (" + body.length + " bytes)");
                    String mime = contentMime(conn.getContentType(), url);
                    Map<String, String> headers = new HashMap<>();
                    headers.put("Content-Type", mime);
                    headers.put("Cache-Control", "no-cache");
                    headers.put("Content-Length", String.valueOf(body.length));
                    return new WebResourceResponse(mime, encodingFor(mime), 200, "OK", headers, new ByteArrayInputStream(body));
                }
            } else {
                Log.w(TAG, "shell fetch HTTP " + code + " for " + url);
            }
        } catch (Exception e) {
            Log.i(TAG, "shell fetch failed for " + url + ": " + e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
        }
        if (cacheFile.exists() && cacheFile.length() > 0) {
            try {
                Log.i(TAG, "serving snapshot " + cacheFile.getName() + " for " + url);
                String mime = guessMime(url);
                Map<String, String> headers = new HashMap<>();
                headers.put("Content-Type", mime);
                headers.put("Cache-Control", "no-cache");
                headers.put("Content-Length", String.valueOf(cacheFile.length()));
                return new WebResourceResponse(mime, encodingFor(mime), 200, "OK", headers, new FileInputStream(cacheFile));
            } catch (Exception e) {
                Log.w(TAG, "failed to serve snapshot " + cacheFile, e);
            }
        }
        return null;
    }

    private File cacheFileFor(Uri url) {
        String path = url.getPath();
        if (path == null || path.isEmpty()) path = "/";
        String name = path.replaceAll("^/+", "").replaceAll("/+$", "").replace('/', '_');
        if (name.isEmpty()) name = "index";
        if (!name.contains(".")) name = name + ".html";
        // Query string is intentionally dropped: ?v= is our own cache-buster
        // and the snapshot should survive version bumps.
        return new File(new File(base.getParentFile(), "webcache"), name);
    }

    private String contentMime(String contentType, Uri url) {
        if (contentType != null) {
            int semi = contentType.indexOf(';');
            String mime = (semi > 0 ? contentType.substring(0, semi) : contentType).trim();
            if (!mime.isEmpty()) return mime;
        }
        return guessMime(url);
    }

    private String guessMime(Uri url) {
        String path = url.getPath() != null ? url.getPath() : "";
        if (path.endsWith(".webmanifest")) return "application/manifest+json";
        String mime = URLConnection.guessContentTypeFromName(path);
        return mime != null ? mime : "application/octet-stream";
    }

    private String encodingFor(String mime) {
        if (mime == null) return null;
        if (mime.startsWith("text/") || mime.contains("javascript") || mime.contains("json") || mime.contains("svg")) {
            return "utf-8";
        }
        return null;
    }

    private byte[] readFully(InputStream in, int max) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        int total = 0;
        while ((n = in.read(buf)) > 0) {
            total += n;
            if (total > max) {
                in.close();
                return null;
            }
            bos.write(buf, 0, n);
        }
        in.close();
        return bos.toByteArray();
    }

    private void writeAtomic(File target, byte[] body) {
        FileOutputStream fos = null;
        File tmp = new File(target.getParentFile(), target.getName() + ".tmp");
        try {
            File dir = target.getParentFile();
            if (dir != null && !dir.exists()) dir.mkdirs();
            fos = new FileOutputStream(tmp);
            fos.write(body);
            fos.close();
            fos = null;
            if (!tmp.renameTo(target)) {
                Log.w(TAG, "snapshot rename failed for " + target);
                tmp.delete();
            }
        } catch (Exception e) {
            Log.w(TAG, "failed to write snapshot " + target, e);
            if (tmp.exists()) tmp.delete();
        } finally {
            if (fos != null) {
                try { fos.close(); } catch (IOException ignored) {}
            }
        }
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
