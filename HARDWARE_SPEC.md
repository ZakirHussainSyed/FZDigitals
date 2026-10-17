# FZDigitals Mosque TV Device — ODM Firmware Requirements

## 1. Product

HDMI stick or set-top box ("the Device") sold exclusively for use in mosques. It must boot directly into the FZDigitals Mosque TV application and expose no other applications, stores, or settings to the end user.

## 2. Hardware requirements

| Item | Requirement |
|------|-------------|
| SoC | Amlogic S905Y4 / S905X4, or Rockchip RK3528 (or equivalent 4K-capable) |
| RAM / Storage | 2 GB / 16 GB minimum (4K video + offline media cache) |
| Video | 4K @ 60fps H.264/H.265 decode; HDMI 2.0 out; HDMI-CEC desirable |
| Network | Dual-band Wi-Fi (2.4/5 GHz) + 10/100 Ethernet |
| Power | 5V/2A USB-C or barrel; auto-power-on (no power button required) |
| Remote | IR/BT remote not required for normal operation (kiosk); optional for setup |
| Misc | Watchdog timer; RTC; status LED controllable by app |

## 3. OS / firmware

- **AOSP Android 11+** — NOT Android TV with GMS/Play Store.
- **No Google Mobile Services.** No Play Store, YouTube, Chrome, Google Play Services.
- **No browser, no file manager, no app installer** of any kind.
- FZDigitals Mosque TV APK (`com.fzdigitals.mosquetv`) installed as the **only launcher/home app** and auto-started at boot (kiosk single-app mode).
- Status bar, nav bar, recents, and safe-mode boot disabled.
- USB debugging (ADB) disabled or password-protected in production builds.
- Sideloading blocked: `INSTALL_PACKAGES` not granted to user apps; package installer removed.
- Factory reset via recovery **password-protected** or disabled; reset allowed only via our remote management command.
- Signed firmware images; recovery accepts only OTA packages signed with FZDigitals/ODM keys.

## 4. Device app behavior (already built — for context)

- Capacitor WebView app rendering `https://www.fzscreens.com/mosque-tv/<device_id>/`.
- Downloads slideshow media to local storage and serves it via embedded HTTP server for offline playback.
- Authenticates via device id + token: `GET /api/device/<id>/slideshow/?token=...`.
- Needs: `android.permission.INTERNET`, media autoplay without user gesture, mixed content allowed, hardware acceleration.

## 5. Provisioning & pairing

- Each unit ships with a unique serial/device ID readable by the app (e.g., `Settings.Secure.ANDROID_ID` stable across reboots, or provisioned ID in `/persist` or efuse-backed storage readable via a vendor API).
- First boot shows pairing code screen (app-side); admin pairs device to a mosque via web admin.
- No keyboard required: all configuration done remotely via our API/MDM channel.

## 6. Remote management (must-have for support)

- OTA updates for **both** the APK and full firmware image, initiated by our server.
- Remote command channel (FCM-free: MQTT, or HTTPS long-poll — must work without Google services): reboot, relaunch app, clear cache, report status/logs.
- Device heartbeat with: app version, firmware version, uptime, storage free, last sync time.
- Rollback-safe A/B OTA preferred.

## 7. Certification & supply

- CE, FCC, RoHS certified; HDMI logo licensed.
- MOQ and per-unit pricing tiers at 500 / 2,000 / 10,000 units.
- Lead time for re-flash of custom firmware on repeat orders.
- Custom branding: boot logo + casing print/label.
- 12-month warranty, DOA replacement policy.

## 8. Tablet variant (phase 2)

- Same firmware policy applied to a white-label 8–10" Android tablet (AOSP, single-app kiosk, no GMS) for the FZDigitals Tablet app.

## 9. Deliverables from ODM

1. Sample units (2) with firmware installed for FZDigitals QA.
2. Firmware source/build support or firmware customization service agreement.
3. OTA server integration spec (endpoints, signing, package format).
4. Provisioning tool for serial/device ID assignment.
