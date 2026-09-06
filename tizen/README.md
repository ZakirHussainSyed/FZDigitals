# FZ Screens — Samsung TV (Tizen) App

A thin Tizen web app that loads `https://www.fzscreens.com/tablet/` — the same
pairing + slideshow page used by the Android app.

## Files

- `config.xml` — Tizen widget manifest (app id, icon, network permissions)
- `index.html` — redirects to the hosted tablet page
- `icon.png` — app icon shown on the TV home screen

## One-time setup (on your Mac)

1. Install **Tizen Studio** with the **TV extension**:
   https://developer.samsung.com/smarttv/develop/getting-started/setting-up-sdk.html
2. Create a **Samsung account** (free) — needed for certificates.
3. In Tizen Studio: **Tools → Certificate Manager → +** → create a
   **Samsung certificate profile** (author + distributor). For the distributor
   certificate, connect the TV first so its DUID is registered.

## On the TV (one-time)

1. Open **Apps** → enter `12345` on the remote → **Developer mode: ON**.
2. Enter your Mac's local IP address as the host PC.
3. Reboot the TV.

## Build & install

```bash
# Package the .wgt (run inside this tizen/ folder)
tizen package -t wgt -s <your-cert-profile> -- .

# Connect to the TV (TV and Mac on same network)
sdb connect <TV-IP>

# Install
tizen install -n FZScreens1.wgt -t <TV-device-name>
```

Or use Tizen Studio IDE: import `tizen/` as a Tizen Web project,
right-click → **Run As → Tizen Web Application** on the connected TV.

## Notes

- The app needs internet access — already declared via `<access>` in `config.xml`.
- Pairing code entry uses the TV's on-screen keyboard.
- To publish on the Samsung TV store later, the same project is submitted via
  the Samsung Seller Office.
