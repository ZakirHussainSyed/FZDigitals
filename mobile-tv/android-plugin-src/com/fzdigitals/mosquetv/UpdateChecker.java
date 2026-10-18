package com.fzdigitals.mosquetv;

import android.app.DownloadManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.content.pm.PackageInstaller;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Over-the-air APK update with no laptop:
 * once per launch, fetch the latest GitHub release; if its tag
 * (tv-<versionCode>) is newer than the installed build, download the
 * signed APK and open the system install sheet. One remote press
 * applies the update — same signature, so settings and the Home Guard
 * toggle survive.
 */
public final class UpdateChecker {

    private static final String TAG = "UpdateChecker";
    private static final String RELEASE_API =
            "https://api.github.com/repos/ZakirHussainSyed/FZDigitals/releases/latest";
    private static final long CHECK_DELAY_MS = 20_000;
    private static boolean ran = false;

    private UpdateChecker() {
    }

    /** Fire-and-forget update check; call once from MainActivity. */
    public static void schedule(final Context ctx) {
        if (ran) return;
        ran = true;
        final Context app = ctx.getApplicationContext();
        new Handler(Looper.getMainLooper())
                .postDelayed(() -> check(app), CHECK_DELAY_MS);
    }

    private static void check(Context ctx) {
        new Thread(() -> {
            try {
                JSONObject rel = get(RELEASE_API);
                if (rel == null) return;
                int remote = parseVersion(rel.optString("tag_name", ""));
                int local = versionCode(ctx);
                Log.i(TAG, "installed=" + local + " latest=" + remote);
                if (remote <= local) return;
                String apk = findApkAsset(rel);
                if (apk == null) return;
                download(ctx, apk);
            } catch (Exception e) {
                Log.w(TAG, "update check failed", e);
            }
        }).start();
    }

    private static JSONObject get(String url) {
        try {
            HttpURLConnection c = (HttpURLConnection)
                    new URL(url).openConnection();
            c.setConnectTimeout(10_000);
            c.setReadTimeout(10_000);
            c.setRequestProperty("Accept", "application/vnd.github+json");
            c.setRequestProperty("User-Agent", "mosquetv-updater");
            if (c.getResponseCode() != 200) return null;
            StringBuilder sb = new StringBuilder();
            try (BufferedReader r = new BufferedReader(
                    new InputStreamReader(c.getInputStream()))) {
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
            }
            return new JSONObject(sb.toString());
        } catch (Exception e) {
            return null;
        }
    }

    private static String findApkAsset(JSONObject rel) {
        JSONArray assets = rel.optJSONArray("assets");
        if (assets == null) return null;
        for (int i = 0; i < assets.length(); i++) {
            JSONObject a = assets.optJSONObject(i);
            if (a != null && a.optString("name", "").endsWith(".apk")) {
                return a.optString("browser_download_url", null);
            }
        }
        return null;
    }

    private static int parseVersion(String tag) {
        StringBuilder digits = new StringBuilder();
        for (char c : tag.toCharArray()) {
            if (Character.isDigit(c)) digits.append(c);
        }
        try {
            return Integer.parseInt(digits.toString());
        } catch (Exception e) {
            return 0;
        }
    }

    private static int versionCode(Context ctx) {
        try {
            android.content.pm.PackageInfo pi = ctx.getPackageManager()
                    .getPackageInfo(ctx.getPackageName(), 0);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                return (int) pi.getLongVersionCode();
            }
            return pi.versionCode;
        } catch (Exception e) {
            return 0;
        }
    }

    private static void download(final Context ctx, String url) {
        final DownloadManager dm = (DownloadManager)
                ctx.getSystemService(Context.DOWNLOAD_SERVICE);
        if (dm == null) return;
        DownloadManager.Request req =
                new DownloadManager.Request(Uri.parse(url))
                        .setTitle("Mosque TV update")
                        .setNotificationVisibility(DownloadManager.Request
                                .VISIBILITY_HIDDEN)
                        .setDestinationInExternalFilesDir(ctx,
                                Environment.DIRECTORY_DOWNLOADS,
                                "update.apk")
                        .setAllowedOverMetered(true);
        final long id;
        try {
            id = dm.enqueue(req);
        } catch (Exception e) {
            Log.w(TAG, "download enqueue failed", e);
            return;
        }
        BroadcastReceiver done = new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent i) {
                if (i.getLongExtra(DownloadManager.EXTRA_DOWNLOAD_ID, -1)
                        != id) return;
                try {
                    c.unregisterReceiver(this);
                } catch (Exception ignored) {
                }
                Uri apk = dm.getUriForDownloadedFile(id);
                if (apk == null) return;
                sessionInstall(c, apk);
            }
        };
        IntentFilter f = new IntentFilter(
                DownloadManager.ACTION_DOWNLOAD_COMPLETE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ctx.registerReceiver(done, f, Context.RECEIVER_NOT_EXPORTED);
        } else {
            ctx.registerReceiver(done, f);
        }
    }

    private static final String ACTION_INSTALL_STATUS =
            "com.fzdigitals.mosquetv.INSTALL_STATUS";

    /**
     * Session-based install (PackageInstaller). Unlike file-manager
     * installs, a session install is not flagged "restricted" on
     * Android 13+ — so an OTA update self-clears the sideload block
     * and the Home Guard toggle becomes usable on-device. Falls back
     * to the plain install intent if the session can't open.
     */
    private static void sessionInstall(Context c, Uri apk) {
        try {
            PackageInstaller pi = c.getPackageManager()
                    .getPackageInstaller();
            PackageInstaller.SessionParams params =
                    new PackageInstaller.SessionParams(
                            PackageInstaller.SessionParams
                                    .MODE_FULL_INSTALL);
            params.setAppPackageName(c.getPackageName());
            PackageInstaller.Session session =
                    pi.openSession(pi.createSession(params));
            try (java.io.InputStream in =
                         c.getContentResolver().openInputStream(apk);
                 java.io.OutputStream out =
                         session.openWrite("base.apk", 0, -1)) {
                byte[] buf = new byte[65536];
                int n;
                while (in != null && (n = in.read(buf)) >= 0) {
                    out.write(buf, 0, n);
                }
                session.fsync(out);
            }
            InstallStatusReceiver receiver = new InstallStatusReceiver();
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                c.registerReceiver(receiver,
                        new IntentFilter(ACTION_INSTALL_STATUS),
                        Context.RECEIVER_NOT_EXPORTED);
            } else {
                c.registerReceiver(receiver,
                        new IntentFilter(ACTION_INSTALL_STATUS));
            }
            Intent callback = new Intent(ACTION_INSTALL_STATUS)
                    .setPackage(c.getPackageName());
            PendingIntent pending = PendingIntent.getBroadcast(c, 0,
                    callback,
                    PendingIntent.FLAG_UPDATE_CURRENT
                            | PendingIntent.FLAG_MUTABLE);
            session.commit(pending.getIntentSender());
            session.close();
        } catch (Exception e) {
            Log.w(TAG, "session install failed, falling back", e);
            Intent install = new Intent(Intent.ACTION_VIEW)
                    .setDataAndType(apk,
                            "application/vnd.android.package-archive")
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_GRANT_READ_URI_PERMISSION);
            try {
                c.startActivity(install);
            } catch (Exception ex) {
                Log.w(TAG, "install intent failed", ex);
            }
        }
    }

    /** Receives PackageInstaller commit status; opens the confirm sheet. */
    public static class InstallStatusReceiver extends BroadcastReceiver {
        @Override
        public void onReceive(Context c, Intent i) {
            int status = i.getIntExtra(PackageInstaller.EXTRA_STATUS, -1);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                Intent confirm = i.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirm == null) return;
                confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                try {
                    c.startActivity(confirm);
                } catch (Exception e) {
                    Log.w(TAG, "confirm sheet failed", e);
                }
            } else {
                Log.i(TAG, "install status=" + status);
            }
        }
    }
}
