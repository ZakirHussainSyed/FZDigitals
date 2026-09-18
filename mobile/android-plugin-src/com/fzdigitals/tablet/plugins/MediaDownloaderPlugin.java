package com.fzdigitals.tablet.plugins;

import android.content.Context;
import android.util.Log;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
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

    @PluginMethod
    public void sync(PluginCall call) {
        JSArray files = call.getArray("files", new JSArray());
        Context ctx = getContext();
        final File base = new File(ctx.getFilesDir(), SUBDIR);
        if (!base.exists() && !base.mkdirs()) {
            call.reject("Cannot create slideshow directory");
            return;
        }

        final List<JSONObject> fileList = new ArrayList<>();
        for (int i = 0; i < files.length(); i++) {
            try {
                fileList.add(files.getJSONObject(i));
            } catch (Exception e) {
                Log.w(TAG, "bad file object at index " + i, e);
            }
        }

        int threads = Math.max(1, Math.min(fileList.size(), 4));
        ExecutorService executor = Executors.newFixedThreadPool(threads);
        List<Future<JSObject>> futures = new ArrayList<>();
        for (int i = 0; i < fileList.size(); i++) {
            final JSONObject f = fileList.get(i);
            futures.add(executor.submit(new Callable<JSObject>() {
                public JSObject call() {
                    return downloadOne(base, f);
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

            // Clean up files not in the new list
            List<String> keep = new ArrayList<>();
            for (JSONObject f : fileList) {
                String id = f.optString("id", null);
                if (id != null) keep.add(id);
            }
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

    private JSObject downloadOne(File base, JSONObject f) {
        String id = f.optString("id", "");
        String url = f.optString("url", "");
        String type = f.optString("type", "image");
        String ext = type.startsWith("video") ? ".mp4" : ".jpg";
        File out = new File(base, id + ext);

        JSObject result = new JSObject();
        result.put("id", id);
        result.put("url", url);

        if (out.exists() && out.length() > 0) {
            result.put("status", "cached");
            result.put("localPath", out.getAbsolutePath());
            return result;
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
                if (tmp.renameTo(out)) {
                    result.put("status", "downloaded");
                    result.put("localPath", out.getAbsolutePath());
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
        return result;
    }
}
