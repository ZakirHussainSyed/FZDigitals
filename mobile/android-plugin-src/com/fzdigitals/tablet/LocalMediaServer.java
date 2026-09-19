package com.fzdigitals.tablet;

import android.net.Uri;
import android.util.Log;
import android.webkit.MimeTypeMap;
import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Tiny HTTP/1.1 server bound to 127.0.0.1 that serves the downloaded slideshow
 * media with proper Range support. The WebView's shouldInterceptRequest path
 * proved unreliable for video range requests, so media URLs point at this
 * server instead and the media stack gets real HTTP responses.
 */
public class LocalMediaServer {
    private static final String TAG = "LocalMediaServer";
    private static final String LOCAL_PATH = "/tablet-local/";

    private final File base;
    private final ExecutorService pool = Executors.newCachedThreadPool();
    private ServerSocket serverSocket;
    private Thread acceptThread;
    private volatile int port = -1;

    public LocalMediaServer(File base) {
        this.base = base;
    }

    public synchronized int start() {
        if (port > 0) return port;
        try {
            serverSocket = new ServerSocket(0, 50, InetAddress.getByName("127.0.0.1"));
            port = serverSocket.getLocalPort();
            acceptThread = new Thread(this::acceptLoop, "LocalMediaServer");
            acceptThread.setDaemon(true);
            acceptThread.start();
            Log.i(TAG, "listening on 127.0.0.1:" + port + " base=" + base.getAbsolutePath());
        } catch (IOException e) {
            Log.e(TAG, "failed to start", e);
            port = -1;
        }
        return port;
    }

    public int getPort() {
        return port;
    }

    private void acceptLoop() {
        while (serverSocket != null && !serverSocket.isClosed()) {
            try {
                Socket s = serverSocket.accept();
                pool.execute(() -> handle(s));
            } catch (IOException e) {
                if (!serverSocket.isClosed()) Log.w(TAG, "accept failed", e);
            }
        }
    }

    private void handle(Socket socket) {
        try (Socket s = socket) {
            s.setSoTimeout(30000);
            InputStream in = new BufferedInputStream(s.getInputStream());
            OutputStream out = s.getOutputStream();

            String requestLine = readLine(in);
            if (requestLine == null || requestLine.isEmpty()) return;
            Map<String, String> headers = new HashMap<>();
            String line;
            while ((line = readLine(in)) != null && !line.isEmpty()) {
                int idx = line.indexOf(':');
                if (idx > 0) {
                    headers.put(line.substring(0, idx).trim().toLowerCase(Locale.US), line.substring(idx + 1).trim());
                }
            }

            String[] parts = requestLine.split(" ");
            if (parts.length < 2) {
                respond(out, 400, "Bad Request", "text/plain", null, null);
                return;
            }
            String method = parts[0];
            String path = Uri.parse(parts[1]).getPath();
            if (path == null) path = "/";

            if ("OPTIONS".equals(method)) {
                respond(out, 204, "No Content", "text/plain", null, null);
                return;
            }
            if (!"GET".equals(method) && !"HEAD".equals(method)) {
                respond(out, 405, "Method Not Allowed", "text/plain", null, null);
                return;
            }
            if (!path.startsWith(LOCAL_PATH)) {
                respond(out, 404, "Not Found", "text/plain", "Not found".getBytes(StandardCharsets.UTF_8), null);
                return;
            }
            String name = path.substring(LOCAL_PATH.length());
            if (name.isEmpty() || name.contains("..") || name.contains("/")) {
                respond(out, 403, "Forbidden", "text/plain", null, null);
                return;
            }
            File file = new File(base, name);
            if (!file.exists() || !file.isFile()) {
                Log.i(TAG, "missing: " + file.getAbsolutePath());
                respond(out, 404, "Not Found", "text/plain", ("Not found: " + name).getBytes(StandardCharsets.UTF_8), null);
                return;
            }

            long total = file.length();
            String mime = guessMime(file.getName());
            String range = headers.get("range");
            Log.i(TAG, "request " + method + " " + name + " range=" + range + " total=" + total);
            logBoxes(file);

            long start = 0;
            long end = total - 1;
            boolean partial = false;
            if (range != null && range.startsWith("bytes=")) {
                String spec = range.substring(6);
                int comma = spec.indexOf(',');
                if (comma >= 0) spec = spec.substring(0, comma).trim();
                int dash = spec.indexOf('-');
                try {
                    if (dash == 0) {
                        long suffix = Long.parseLong(spec.substring(1).trim());
                        start = Math.max(0, total - suffix);
                    } else if (dash > 0) {
                        start = Long.parseLong(spec.substring(0, dash).trim());
                        String endStr = spec.substring(dash + 1).trim();
                        if (!endStr.isEmpty()) end = Long.parseLong(endStr);
                    }
                } catch (NumberFormatException e) {
                    respond(out, 416, "Requested Range Not Satisfiable", "text/plain", null, "bytes */" + total);
                    return;
                }
                if (end >= total) end = total - 1;
                if (start < 0 || start >= total || end < start) {
                    respond(out, 416, "Requested Range Not Satisfiable", "text/plain", null, "bytes */" + total);
                    return;
                }
                partial = true;
            }

            long length = end - start + 1;
            Map<String, String> extra = new HashMap<>();
            if (partial) extra.put("Content-Range", "bytes " + start + "-" + end + "/" + total);
            int code = partial ? 206 : 200;
            String reason = partial ? "Partial Content" : "OK";
            Log.i(TAG, "serving-" + code + " " + name + " start=" + start + " end=" + end + " length=" + length);
            writeHeaders(out, code, reason, mime, length, extra);
            if ("GET".equals(method)) {
                streamFile(out, file, start, length);
            }
            out.flush();
        } catch (IOException e) {
            Log.w(TAG, "connection error: " + e.getMessage());
        }
    }

    private String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int c;
        boolean any = false;
        while ((c = in.read()) != -1) {
            if (c == '\n') { any = true; break; }
            buf.write(c);
            any = true;
        }
        if (!any && c == -1) return null;
        String line = buf.toString("UTF-8");
        if (line.endsWith("\r")) line = line.substring(0, line.length() - 1);
        return line;
    }

    private void respond(OutputStream out, int code, String reason, String mime, byte[] body, String contentRange) throws IOException {
        Map<String, String> extra = null;
        if (contentRange != null) {
            extra = new HashMap<>();
            extra.put("Content-Range", contentRange);
        }
        writeHeaders(out, code, reason, mime, body != null ? body.length : 0, extra);
        if (body != null) out.write(body);
        out.flush();
    }

    private void writeHeaders(OutputStream out, int code, String reason, String mime, long length, Map<String, String> extra) throws IOException {
        StringBuilder sb = new StringBuilder();
        sb.append("HTTP/1.1 ").append(code).append(' ').append(reason).append("\r\n");
        sb.append("Content-Type: ").append(mime).append("\r\n");
        sb.append("Content-Length: ").append(length).append("\r\n");
        sb.append("Accept-Ranges: bytes\r\n");
        sb.append("Access-Control-Allow-Origin: *\r\n");
        sb.append("Access-Control-Allow-Methods: GET, HEAD, OPTIONS\r\n");
        sb.append("Access-Control-Allow-Headers: *\r\n");
        // Required for Private Network Access preflights from the public https page.
        sb.append("Access-Control-Allow-Private-Network: true\r\n");
        sb.append("Cache-Control: public, max-age=31536000, immutable\r\n");
        sb.append("Connection: close\r\n");
        if (extra != null) {
            for (Map.Entry<String, String> e : extra.entrySet()) {
                sb.append(e.getKey()).append(": ").append(e.getValue()).append("\r\n");
            }
        }
        sb.append("\r\n");
        out.write(sb.toString().getBytes(StandardCharsets.ISO_8859_1));
    }

    private void streamFile(OutputStream out, File file, long start, long length) throws IOException {
        try (FileInputStream fis = new FileInputStream(file)) {
            fis.getChannel().position(start);
            byte[] buf = new byte[65536];
            long remaining = length;
            while (remaining > 0) {
                int n = fis.read(buf, 0, (int) Math.min(buf.length, remaining));
                if (n < 0) break;
                out.write(buf, 0, n);
                remaining -= n;
            }
        }
    }

    private String guessMime(String name) {
        String mime = URLConnection.guessContentTypeFromName(name);
        if (mime == null || mime.isEmpty()) {
            String ext = MimeTypeMap.getFileExtensionFromUrl(name);
            if (ext != null) {
                mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext.toLowerCase());
            }
            if (mime == null || mime.isEmpty()) {
                mime = "application/octet-stream";
            }
        }
        return mime;
    }

    /** Logs the top-level MP4 box layout so we can verify moov position in logcat. */
    private void logBoxes(File file) {
        if (!file.getName().endsWith(".mp4")) return;
        try (FileInputStream fis = new FileInputStream(file)) {
            long total = file.length();
            long pos = 0;
            StringBuilder sb = new StringBuilder();
            while (pos + 8 <= total && sb.length() < 200) {
                fis.getChannel().position(pos);
                byte[] b = new byte[8];
                if (fis.read(b) != 8) break;
                long size = ((b[0] & 0xffL) << 24) | ((b[1] & 0xffL) << 16) | ((b[2] & 0xffL) << 8) | (b[3] & 0xffL);
                String type = new String(b, 4, 4, StandardCharsets.ISO_8859_1);
                sb.append(type).append('@').append(pos).append('+').append(size).append(' ');
                if (size <= 8) break;
                pos += size;
            }
            Log.i(TAG, "boxes " + file.getName() + " total=" + total + " :: " + sb);
        } catch (Exception e) {
            Log.w(TAG, "box scan failed for " + file.getName(), e);
        }
    }
}
