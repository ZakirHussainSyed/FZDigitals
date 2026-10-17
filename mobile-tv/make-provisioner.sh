#!/usr/bin/env bash
# Build a self-contained kiosk provisioner for ONN / Android TV sticks.
#
#   ./make-provisioner.sh <path-to-mosquetv.apk> [output.sh]
#
# Produces ONE file (default: provision-stick.sh) containing the APK +
# all logic. Copy that single file to any operator laptop and run:
#
#   bash provision-stick.sh 10.0.0.209:40061          # connect + provision
#   bash provision-stick.sh --pair 10.0.0.209:40141 225282
#
# The stick needs Wireless debugging ON (Settings > System > Developer
# Options). First-time pairing needs --pair once; later runs just connect.

set -euo pipefail

APK="${1:?usage: $0 <apk-path> [output.sh]}"
OUT="${2:-provision-stick.sh}"
[ -f "$APK" ] || { echo "APK not found: $APK"; exit 1; }

cat > "$OUT" << 'SCRIPT_EOF'
#!/usr/bin/env bash
# Self-contained Mosque TV kiosk provisioner (ONN / Android TV stick).
# Embeds the signed APK — nothing else to copy. Requires: bash, curl.
set -euo pipefail

APP_PKG="com.fzdigitals.mosquetv"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say() { echo "== $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

# --- adb: use PATH, else download platform-tools into the temp dir ---
ADB="$(command -v adb || true)"
if [ -z "$ADB" ]; then
    say "adb not found — downloading platform-tools"
    case "$(uname -sm)" in
        "Darwin arm64"|"Darwin x86_64") PT=https://dl.google.com/android/repository/platform-tools-latest-darwin.zip ;;
        "Linux x86_64")  PT=https://dl.google.com/android/repository/platform-tools-latest-linux.zip ;;
        *) die "unsupported OS for auto adb — install platform-tools manually" ;;
    esac
    curl -fsSL "$PT" -o "$WORK/pt.zip"
    unzip -q "$WORK/pt.zip" -d "$WORK"
    ADB="$WORK/platform-tools/adb"
fi

# --- extract embedded APK payload ---
awk '/^__APK_PAYLOAD_BELOW__$/{flag=1;next}flag' "$0" | base64 -d > "$WORK/mosquetv.apk"
[ -s "$WORK/mosquetv.apk" ] || die "embedded APK payload missing/corrupt"

usage() {
    echo "usage:"
    echo "  $0 <ip>:<connect-port>            connect & provision"
    echo "  $0 --pair <ip>:<pair-port> <code> pair once, then provision"
    echo "  $0                                auto-discover via mDNS"
}

# --- pairing (only needed the very first time per laptop) ---
if [ "${1:-}" = "--pair" ]; then
    [ $# -ge 3 ] || { usage; exit 1; }
    say "Pairing $2"
    "$ADB" pair "$2" "$3" || die "pairing failed — is the pair dialog still open on the TV?"
    shift 3
    say "Paired. Opening Wireless debugging screen on the stick to learn the connect port..."
    sleep 3
fi

# --- resolve target ip:port ---
TARGET="${1:-}"
if [ -z "$TARGET" ]; then
    say "Auto-discovering via mDNS..."
    for i in 1 2 3 4 5; do
        TARGET=$("$ADB" mdns services | awk '/_adb\._tcp/{print $NF; exit}')
        [ -n "$TARGET" ] || TARGET=$("$ADB" mdns services | awk '/tls-connect/{print $NF; exit}')
        [ -n "$TARGET" ] && break
        sleep 2
    done
fi
[ -n "$TARGET" ] || { usage; die "no target — pass <ip>:<port> or enable Wireless debugging"; }
IP="${TARGET%%:*}"

say "Connecting to $TARGET"
"$ADB" connect "$TARGET" || true
"$ADB" -s "$TARGET" wait-for-device
"$ADB" -s "$TARGET" shell getprop ro.build.version.release >/dev/null 2>&1 \
    || die "connected but device not ready — check 'unauthorized' prompt on TV"

say "Installing Mosque TV APK"
"$ADB" -s "$TARGET" install -r -d "$WORK/mosquetv.apk" || die "install failed"

# --- consumer apps: hide for kiosk. Per-user disable; survives reboot,
#     NOT factory reset. Low-risk packages first, system-ish ones last.
CONSUMER_PKGS=(
    com.google.android.youtube.tv
    com.google.android.videos
    com.netflix.ninja
    com.amazon.amazonvideo.livingroom
    com.google.android.play.games
    com.google.android.titanium.media
    com.walmart.onn.setup
    com.google.android.tv.setup
)
SYSTEM_PKGS=(          # can drop adbd/framework — disable LAST
    com.google.android.katniss
    com.google.android.tungsten.setupwraith
    com.google.android.tvrecommendations
)
disable_list() {
    for pkg in "$@"; do
        if "$ADB" -s "$TARGET" shell pm list packages | grep -q "^package:$pkg$"; then
            echo "  disabling $pkg"
            "$ADB" -s "$TARGET" shell pm disable-user --user 0 "$pkg" \
                || "$ADB" -s "$TARGET" shell pm uninstall -k --user 0 "$pkg" \
                || echo "    could not remove $pkg"
        fi
    done
}
say "Disabling consumer apps"
disable_list "${CONSUMER_PKGS[@]}"

say "Setting Mosque TV as home"
"$ADB" -s "$TARGET" shell cmd package set-home-activity "$APP_PKG" || true

# Stock launcher holds a preferred-default that beats set-home-activity —
# disabling it makes our app the only home candidate. Reversible via
# 'pm enable com.google.android.apps.tv.launcherx'.
for LAUNCHER in com.google.android.apps.tv.launcherx com.google.android.tvlauncher; do
    if "$ADB" -s "$TARGET" shell pm list packages | grep -q "^package:$LAUNCHER$"; then
        say "Disabling stock launcher $LAUNCHER"
        "$ADB" -s "$TARGET" shell pm disable-user --user 0 "$LAUNCHER" || true
    fi
done

# verify Home lands on our app
"$ADB" -s "$TARGET" shell input keyevent KEYCODE_HOME || true
sleep 3
TOP=$("$ADB" -s "$TARGET" shell dumpsys activity activities 2>/dev/null \
    | grep -oE 'topResumedActivity=ActivityRecord\{[^ ]+ [^ ]+/\.[^ ]+' | head -1)
echo "  foreground after HOME: ${TOP:-unknown}"
case "$TOP" in
    *"$APP_PKG"*) echo "  kiosk OK — app owns Home" ;;
    *) echo "  WARNING: another app still owns Home — check manually" ;;
esac

say "Disabling system-ish packages (may drop adb — safe to ignore errors)"
disable_list "${SYSTEM_PKGS[@]}" || true

say "Rebooting"
"$ADB" -s "$TARGET" reboot || true
echo "Done. The stick should boot straight into the Mosque TV app."
exit 0

__APK_PAYLOAD_BELOW__
SCRIPT_EOF

# append the APK as base64 payload
base64 -i "$APK" >> "$OUT"
chmod +x "$OUT"
echo "Built $OUT ($(du -h "$OUT" | cut -f1) — embedded $(basename "$APK"))"
