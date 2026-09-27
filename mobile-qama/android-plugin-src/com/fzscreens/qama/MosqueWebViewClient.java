package com.fzscreens.qama;

import android.net.Uri;
import android.util.Base64;
import android.util.Log;
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
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLConnection;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

public class MosqueWebViewClient extends BridgeWebViewClient {
    private static final String TAG = "MosqueWebViewClient";
    private static final String[] APP_HOSTS = {
        "qama.fzscreens.com", "www.fzscreens.com", "fzscreens.com"
    };
    // CDN assets the map shell depends on — cached so offline launches work.
    private static final String[] CDN_HOSTS = {"unpkg.com", "cdn.jsdelivr.net"};

    // Raster tile path shape: .../{z}/{x}/{y}[@2x][.ext] (cartocdn, OSM, Mapbox).
    private static final Pattern TILE_PATH = Pattern.compile(
        ".*\\d+/\\d+/\\d+(@2x)?(\\.(png|jpe?g|webp))?$", Pattern.CASE_INSENSITIVE);

    // Transparent 1x1 PNG — served when a tile can't be fetched and isn't
    // cached, so Leaflet fails fast instead of leaving a hanging request.
    private static final byte[] EMPTY_TILE = Base64.decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        + "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", Base64.DEFAULT);

    private final File webcacheDir;
    private final File tileDir;
    private final String userAgent;
    private boolean triedCacheFallback = false;

    public MosqueWebViewClient(Bridge bridge, File filesDir) {
        super(bridge);
        this.webcacheDir = new File(filesDir, "webcache");
        this.tileDir = new File(filesDir, "tiles");
        // Capture UA on the main thread — WebView methods cannot be called
        // from shouldInterceptRequest's background thread.
        String ua = null;
        try {
            ua = bridge.getWebView().getSettings().getUserAgentString();
        } catch (Exception ignored) {}
        this.userAgent = ua;
    }

    /**
     * If the main page fails to load (offline, server down), retry once from
     * the WebView HTTP cache so the app shell can still come up.
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
        // Restore normal revalidation so API fetches and future loads hit the
        // network when it's available.
        view.getSettings().setCacheMode(WebSettings.LOAD_DEFAULT);
        super.onPageFinished(view, url);
    }

    @Override
    public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri url = request.getUrl();
        String method = request.getMethod() != null ? request.getMethod() : "GET";
        if (!"GET".equals(method)) {
            return super.shouldInterceptRequest(view, request);
        }
        // Map tiles are immutable — cache each one permanently the first time
        // it's fetched, then never hit the network for it again.
        if (isTileRequest(url)) {
            return tileResponse(url);
        }
        // App shell, /static/ assets, CDN libs, and the mosque-times API:
        // network-first, but every success is snapshotted to disk and served
        // as the offline fallback.
        if (isAppRequest(url, request)) {
            WebResourceResponse res = fetchThroughCache(request, url);
            if (res != null) return res;
        }
        return super.shouldInterceptRequest(view, request);
    }

    private boolean isTileRequest(Uri url) {
        String path = url.getPath();
        return path != null && TILE_PATH.matcher(path).matches();
    }

    private boolean isAppRequest(Uri url, WebResourceRequest request) {
        String host = url.getHost();
        if (host == null) return false;
        for (String cdn : CDN_HOSTS) {
            if (host.endsWith(cdn)) return true;
        }
        for (String app : APP_HOSTS) {
            if (host.equals(app)) {
                if (request.isForMainFrame()) return true;
                String path = url.getPath();
                return path != null && (
                    path.startsWith("/static/")
                    || path.startsWith("/mosque-map")
                    || path.startsWith("/api/public/mosques/")
                    || path.equals("/manifest.webmanifest"));
            }
        }
        return false;
    }

    /**
     * Disk-first tile fetch: serve the cached copy, or fetch once and store
     * permanently. A failed fetch yields a transparent placeholder tile.
     */
    private WebResourceResponse tileResponse(Uri url) {
        File file = tileFileFor(url);
        if (file.exists() && file.length() > 0) {
            try {
                return tileHeaders(guessMime(url), file.length(), new FileInputStream(file));
            } catch (Exception e) {
                Log.w(TAG, "failed to serve cached tile " + file, e);
            }
        }
        byte[] body = fetchBytes(url, conn -> {}, 8 * 1024 * 1024);
        if (body != null && body.length > 0) {
            writeAtomic(file, body);
            return tileHeaders(guessMime(url), body.length, new ByteArrayInputStream(body));
        }
        return tileHeaders("image/png", EMPTY_TILE.length, new ByteArrayInputStream(EMPTY_TILE));
    }

    private WebResourceResponse tileHeaders(String mime, long length, InputStream body) {
        Map<String, String> headers = new HashMap<>();
        headers.put("Content-Type", mime);
        headers.put("Content-Length", String.valueOf(length));
        headers.put("Cache-Control", "public, max-age=31536000, immutable");
        return new WebResourceResponse(mime, null, 200, "OK", headers, body);
    }

    private File tileFileFor(Uri url) {
        String host = url.getHost() != null ? url.getHost() : "";
        // cartocdn a./b./c./d. subdomains serve identical tiles — strip the
        // letter so the same tile is cached once, not four times.
        host = host.replaceAll("^[a-d]\\.", "");
        String key = host + url.getPath() + "|" + (url.getQuery() != null ? url.getQuery() : "");
        String ext = "";
        String path = url.getPath() != null ? url.getPath() : "";
        int dot = path.lastIndexOf('.');
        if (dot >= 0 && path.length() - dot <= 6) ext = path.substring(dot);
        if (ext.isEmpty()) ext = ".png";
        return new File(tileDir, md5(key) + ext);
    }

    /**
     * GET the resource and, on success, store it under filesDir/webcache.
     * Returns body+mime on success, null on any failure.
     */
    private byte[] fetchBytes(Uri url, java.util.function.Consumer<HttpURLConnection> configure, int max) {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(url.toString()).openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(15000);
            conn.setInstanceFollowRedirects(true);
            conn.setRequestProperty("Accept-Encoding", "identity");
            if (userAgent != null) conn.setRequestProperty("User-Agent", userAgent);
            configure.accept(conn);
            int code = conn.getResponseCode();
            if (code >= 200 && code < 300) {
                return readFully(conn.getInputStream(), max);
            }
            Log.w(TAG, "fetch HTTP " + code + " for " + url);
        } catch (Exception e) {
            Log.i(TAG, "fetch failed for " + url + ": " + e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
        }
        return null;
    }

    /**
     * Network-first for shell/API/CDN: on success return the fresh body and
     * snapshot it; on any failure serve the last stored copy.
     */
    private WebResourceResponse fetchThroughCache(WebResourceRequest request, Uri url) {
        File cacheFile = cacheFileFor(url);
        byte[] body = fetchBytes(url, conn -> {
            Map<String, String> reqHeaders = request.getRequestHeaders();
            if (reqHeaders != null) {
                for (Map.Entry<String, String> h : reqHeaders.entrySet()) {
                    String k = h.getKey();
                    if (k == null || h.getValue() == null) continue;
                    String lk = k.toLowerCase(Locale.US);
                    if (lk.equals("host") || lk.equals("connection")
                            || lk.equals("accept-encoding") || lk.equals("user-agent")) continue;
                    conn.setRequestProperty(k, h.getValue());
                }
            }
        }, 8 * 1024 * 1024);
        if (body != null && body.length > 0) {
            writeAtomic(cacheFile, body);
            String mime = guessMime(url);
            Map<String, String> headers = new HashMap<>();
            headers.put("Content-Type", mime);
            headers.put("Cache-Control", "no-cache");
            headers.put("Content-Length", String.valueOf(body.length));
            return new WebResourceResponse(mime, encodingFor(mime), 200, "OK",
                    headers, new ByteArrayInputStream(body));
        }
        if (cacheFile.exists() && cacheFile.length() > 0) {
            try {
                Log.i(TAG, "serving snapshot " + cacheFile.getName() + " for " + url);
                String mime = guessMime(url);
                Map<String, String> headers = new HashMap<>();
                headers.put("Content-Type", mime);
                headers.put("Cache-Control", "no-cache");
                headers.put("Content-Length", String.valueOf(cacheFile.length()));
                return new WebResourceResponse(mime, encodingFor(mime), 200, "OK",
                        headers, new FileInputStream(cacheFile));
            } catch (Exception e) {
                Log.w(TAG, "failed to serve snapshot " + cacheFile, e);
            }
        }
        return null;
    }

    private File cacheFileFor(Uri url) {
        String host = url.getHost() != null ? url.getHost() : "";
        String path = url.getPath();
        if (path == null || path.isEmpty()) path = "/";
        String name = (host + path).replaceAll("^/+", "").replaceAll("/+$", "")
                .replaceAll("[^A-Za-z0-9._-]", "_");
        if (name.isEmpty()) name = "index";
        if (!name.contains(".")) name = name + ".html";
        // Query dropped — ?v= is our own cache-buster; snapshot survives bumps.
        return new File(webcacheDir, name);
    }

    private String guessMime(Uri url) {
        String path = url.getPath() != null ? url.getPath() : "";
        if (path.endsWith(".webmanifest")) return "application/manifest+json";
        String mime = URLConnection.guessContentTypeFromName(path);
        if (mime == null) {
            String ext = MimeTypeMap.getFileExtensionFromUrl(path);
            if (ext != null) {
                mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase());
            }
        }
        return mime != null ? mime : "application/octet-stream";
    }

    private String encodingFor(String mime) {
        if (mime == null) return null;
        if (mime.startsWith("text/") || mime.contains("javascript")
                || mime.contains("json") || mime.contains("svg")) {
            return "utf-8";
        }
        return null;
    }

    private byte[] readFully(InputStream in, int max) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n, total = 0;
        while ((n = in.read(buf)) > 0) {
            total += n;
            if (total > max) { in.close(); return null; }
            bos.write(buf, 0, n);
        }
        in.close();
        return bos.toByteArray();
    }

    private void writeAtomic(File target, byte[] body) {
        File tmp = new File(target.getParentFile(), target.getName() + ".tmp");
        FileOutputStream fos = null;
        try {
            File dir = target.getParentFile();
            if (dir != null && !dir.exists()) dir.mkdirs();
            fos = new FileOutputStream(tmp);
            fos.write(body);
            fos.close();
            fos = null;
            if (!tmp.renameTo(target)) {
                Log.w(TAG, "rename failed for " + target);
                tmp.delete();
            }
        } catch (Exception e) {
            Log.w(TAG, "failed to write " + target, e);
            if (tmp.exists()) tmp.delete();
        } finally {
            if (fos != null) {
                try { fos.close(); } catch (Exception ignored) {}
            }
        }
    }

    private static String md5(String s) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] d = md.digest(s.getBytes("UTF-8"));
            StringBuilder sb = new StringBuilder();
            for (byte b : d) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            return Integer.toHexString(s.hashCode());
        }
    }
}
