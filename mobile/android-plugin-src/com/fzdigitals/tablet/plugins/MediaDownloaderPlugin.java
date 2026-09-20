package com.fzdigitals.tablet.plugins;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.fzdigitals.tablet.LocalMediaServer;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.json.JSONObject;

@CapacitorPlugin(name = "MediaDownloader")
public class MediaDownloaderPlugin extends Plugin {
    private static final String TAG = "MediaDownloader";
    private static final String SUBDIR = "slideshow";
    private static final String PREFS = "media_sync";
    private static final String KEY_MANIFEST = "manifest";
    private static LocalMediaServer mediaServer;

    @Override
    public void load() {
        File base = new File(getContext().getFilesDir(), SUBDIR);
        if (!base.exists()) base.mkdirs();
        mediaServer = new LocalMediaServer(base);
        mediaServer.start();
    }

    @PluginMethod
    public void sync(PluginCall call) {
        JSArray files = call.getArray("files", new JSArray());
        Context ctx = getContext();
        final File base = new File(ctx.getFilesDir(), SUBDIR);
        if (!base.exists() && !base.mkdirs()) {
            call.reject("Cannot create slideshow directory");
            return;
        }

        // Diff-based sync: download only new/changed files, delete only ids
        // that disappeared upstream. Never wipe the whole cache first — a
        // partial sync must leave the previous slideshow playable.
        final List<JSONObject> fileList = new ArrayList<>();
        final List<String> keepIds = new ArrayList<>();
        for (int i = 0; i < files.length(); i++) {
            try {
                JSONObject f = files.getJSONObject(i);
                fileList.add(f);
                String id = f.optString("id", "");
                if (!id.isEmpty()) keepIds.add(id);
            } catch (Exception e) {
                Log.w(TAG, "bad file object at index " + i, e);
            }
        }

        final JSONObject manifest = loadManifest(ctx);

        int threads = Math.max(1, Math.min(fileList.size(), 4));
        ExecutorService executor = Executors.newFixedThreadPool(threads);
        List<Future<JSObject>> futures = new ArrayList<>();
        for (int i = 0; i < fileList.size(); i++) {
            final JSONObject f = fileList.get(i);
            futures.add(executor.submit(new Callable<JSObject>() {
                public JSObject call() {
                    return downloadOne(base, f, manifest);
                }
            }));
        }

        try {
            JSArray out = new JSArray();
            for (Future<JSObject> f : futures) {
                try {
                    out.put(f.get());
                } catch (Exception e) {
                    Log.e(TAG, "download task failed", e);
                    JSObject err = new JSObject();
                    err.put("status", "error");
                    err.put("error", e.getMessage());
                    out.put(err);
                }
            }

            // Downloads are done (some may have failed — old files stay in
            // place). Now drop files whose id is no longer desired, and prune
            // the manifest to match what is actually on disk.
            cleanFiles(base, keepIds);
            pruneManifest(manifest, keepIds, fileList, base);
            saveManifest(ctx, manifest);

            JSObject result = new JSObject();
            result.put("files", out);
            call.resolve(result);
        } catch (Exception e) {
            Log.e(TAG, "sync failed", e);
            call.reject("Sync failed: " + e.getMessage());
        } finally {
            executor.shutdown();
        }
    }

    @PluginMethod
    public void cleanup(PluginCall call) {
        Context ctx = getContext();
        final File base = new File(ctx.getFilesDir(), SUBDIR);
        JSArray files = call.getArray("keep", new JSArray());
        List<String> keep = new ArrayList<>();
        for (int i = 0; i < files.length(); i++) {
            try {
                keep.add(files.getString(i));
            } catch (Exception e) {
                Log.w(TAG, "bad keep id at index " + i, e);
            }
        }
        cleanFiles(base, keep);
        JSObject result = new JSObject();
        result.put("status", "ok");
        call.resolve(result);
    }

    private void cleanFiles(File base, List<String> keep) {
        File[] existing = base.listFiles();
        if (existing != null) {
            for (File file : existing) {
                String name = file.getName();
                int dot = name.lastIndexOf('.');
                String fileId = dot > 0 ? name.substring(0, dot) : name;
                if (!keep.contains(fileId) && !name.endsWith(".tmp")) {
                    file.delete();
                }
            }
        }
    }

    private String localUrl(File out, String id, String type) {
        String ext = type.startsWith("video") ? ".mp4" : ".jpg";
        int port = mediaServer != null ? mediaServer.getPort() : -1;
        if (port > 0) {
            return "http://127.0.0.1:" + port + "/tablet-local/" + id + ext + "?mtime=" + out.lastModified();
        }
        // Fallback to the intercepted host if the server failed to start.
        return "https://media.fzscreens.com/tablet-local/" + id + ext + "?mtime=" + out.lastModified();
    }

    private long getContentLength(HttpURLConnection conn) {
        String cl = conn.getHeaderField("Content-Length");
        if (cl != null) {
            try { return Long.parseLong(cl.trim()); } catch (NumberFormatException e) {}
        }
        return -1;
    }

    /** Manifest of {id: version} for files we have fully downloaded. */
    private JSONObject loadManifest(Context ctx) {
        try {
            SharedPreferences prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String raw = prefs.getString(KEY_MANIFEST, null);
            if (raw != null) return new JSONObject(raw);
        } catch (Exception e) {
            Log.w(TAG, "manifest load failed", e);
        }
        return new JSONObject();
    }

    private void saveManifest(Context ctx, JSONObject manifest) {
        try {
            ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_MANIFEST, manifest.toString())
                .apply();
        } catch (Exception e) {
            Log.w(TAG, "manifest save failed", e);
        }
    }

    /**
     * After a sync pass, drop manifest entries for ids no longer desired and
     * record the server version for every file that is now on disk.
     */
    private void pruneManifest(JSONObject manifest, List<String> keepIds, List<JSONObject> fileList, File base) {
        try {
            List<String> stale = new ArrayList<>();
            Iterator<String> it = manifest.keys();
            while (it.hasNext()) {
                String id = it.next();
                if (!keepIds.contains(id)) stale.add(id);
            }
            for (String id : stale) manifest.remove(id);

            for (JSONObject f : fileList) {
                String id = f.optString("id", "");
                String version = f.optString("version", "");
                if (id.isEmpty() || version.isEmpty()) continue;
                String ext = f.optString("type", "image").startsWith("video") ? ".mp4" : ".jpg";
                File out = new File(base, id + ext);
                if (out.exists() && out.length() > 0) {
                    manifest.put(id, version);
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "manifest prune failed", e);
        }
    }

    private JSObject downloadOne(File base, JSONObject f, JSONObject manifest) {
        String id = f.optString("id", "");
        String url = f.optString("url", "");
        String type = f.optString("type", "image");
        String version = f.optString("version", "");
        long size = f.optLong("size", -1);
        String ext = type.startsWith("video") ? ".mp4" : ".jpg";
        File out = new File(base, id + ext);

        JSObject result = new JSObject();
        result.put("id", id);
        result.put("url", url);

        if (out.exists() && out.length() > 0) {
            String cachedVersion = manifest.optString(id, null);
            boolean fresh;
            if (!version.isEmpty() && version.equals(cachedVersion)) {
                // Manifest confirms we already have this exact version.
                fresh = true;
            } else if (size > 0 && out.length() == size) {
                // File predates the manifest (or server sent no version) but
                // its size matches the server — adopt it, don't re-download.
                fresh = true;
            } else if (version.isEmpty() && size <= 0) {
                // Server sent no markers at all. Media ids are immutable (a
                // new upload is a new id), so an existing file is current.
                fresh = true;
            } else {
                fresh = false;
            }
            if (fresh) {
                result.put("status", "cached");
                result.put("localPath", out.getAbsolutePath());
                result.put("localUrl", localUrl(out, id, type));
                return result;
            }
            Log.i(TAG, "re-downloading " + id + " version changed (cached=" + cachedVersion + " remote=" + version + ")");
        }

        HttpURLConnection conn = null;
        File tmp = null;
        try {
            URL u = new URL(url);
            conn = (HttpURLConnection) u.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(30000);
            conn.setReadTimeout(60000);
            conn.setDoInput(true);
            int code = conn.getResponseCode();
            if (code >= 200 && code < 300) {
                tmp = new File(base, id + ".tmp");
                InputStream in = conn.getInputStream();
                FileOutputStream fos = new FileOutputStream(tmp);
                byte[] buf = new byte[16384];
                int n;
                while ((n = in.read(buf)) > 0) {
                    fos.write(buf, 0, n);
                }
                fos.close();
                in.close();
                long expected = getContentLength(conn);
                if (tmp.length() == 0 || (expected >= 0 && tmp.length() != expected)) {
                    result.put("status", "error");
                    result.put("error", tmp.length() == 0 ? "empty download" : "size mismatch");
                    if (tmp.exists()) tmp.delete();
                } else if (tmp.renameTo(out) && out.length() > 0) {
                    result.put("status", "downloaded");
                    result.put("localPath", out.getAbsolutePath());
                    result.put("localUrl", localUrl(out, id, type));
                } else {
                    result.put("status", "error");
                    result.put("error", "rename failed");
                }
            } else {
                result.put("status", "error");
                result.put("error", "HTTP " + code);
            }
        } catch (Exception e) {
            Log.e(TAG, "download error " + url, e);
            result.put("status", "error");
            result.put("error", e.getMessage());
        } finally {
            if (conn != null) conn.disconnect();
            if (tmp != null && tmp.exists()) tmp.delete();
        }

        // On failure keep the previous file usable: report its local URL so
        // playback can continue with the stale copy instead of going blank.
        if ("error".equals(result.optString("status")) && out.exists() && out.length() > 0) {
            result.put("localPath", out.getAbsolutePath());
            result.put("localUrl", localUrl(out, id, type));
        }
        return result;
    }
}
