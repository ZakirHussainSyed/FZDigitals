# New TV Setup — Onn / Google TV Stick

Install-only kiosk setup. No laptop, no adb, no scripts, nothing disabled.

## 1. First-run setup (stock)

1. Plug in the stick, pair the remote, connect to the mosque Wi-Fi.
2. Complete the Google sign-in / first-run screens as normal.

## 2. Install the app

1. Open the Play Store on the TV → install **Downloader** (by AFTVnews).
2. Allow Downloader to "Install unknown apps" when prompted.
3. In Downloader, open:
   `https://github.com/ZakirHussainSyed/FZDigitals/releases/latest/download/app-release-signed.apk`
   → Download → Install.
   (Always-latest permalink — no need to look up version numbers.)

## 3. First launch → auto-update (clears Android 14's sideload restriction)

1. Open **Takbir-al-Ula Mosque** and sign in / pick the mosque.
2. Within ~30 s the app checks GitHub for a newer build. If one exists,
   an **Update** sheet appears → press **OK**.
   The session-based update clears Android 14's "restricted settings"
   flag, which is what allows step 4 to work on-device.
   If no update is offered, you're already on the newest build — the
   next release will clear it automatically the same way.
3. If Android asks "Allow install from this source" once → allow it.

## 4. Enable the Home Guard (one toggle, ever)

1. Re-open the app — it takes you to **Settings → Accessibility**.
2. Select **Takbir-al-Ula Mosque** → toggle **Enable** → OK.
3. Press Back to return to the app.

## 5. Verify

- Press **Home** → stock launcher flashes, app returns within ~2 s.
- **Unplug power → replug** → app comes up on its own within ~15 s.
- Gear button → Settings (Wi-Fi stays reachable from the remote).

## Notes

- Nothing is disabled — Wi-Fi, remote, and every stock feature keep working.
- **Never run `pm disable` on Onn/Google TV builds.** Disabling
  `launcherx`, `setupwraith`, `katniss`, or `tvrecommendations` wedges
  HOME/Wi-Fi/BT remote and forces a factory reset (hit twice). The
  accessibility Home Guard achieves the same kiosk behavior with zero
  risk — it just bounces the launcher when it appears.
- Android 14 blocks accessibility toggles for sideloaded apps until the
  app has updated once via a session install (step 3). This is an OS
  rule; a Play Store listing would remove the step entirely.
- Future updates: the app self-prompts on launch. No re-setup needed.
