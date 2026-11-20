# Fish: the phone apps (start here)

This folder is the **iPhone app** and the **Android app**. If you were sent this
repository to put Fish on the App Store or Google Play, this page is for you.
You don't need to know anything about the rest of the repository; it's the
research engine and the website.

## What this is

Fish is a [Capacitor](https://capacitorjs.com) app: a native iOS project
(Xcode, Swift) and a native Android project (Android Studio, Java), each
showing the game's screens, which live in `public/play/` and are copied into
the app when you build it. The website and both apps show the same screens.
The app talks to the game server at `https://fish-engine.vercel.app`, which is
already running. **You don't need any server access, database keys or
passwords to build the iPhone app.**

| | iPhone | Android |
| --- | --- | --- |
| Project | `app/ios/` (open with Xcode) | `app/android/` (open with Android Studio) |
| App ID | `com.fishengine.fish` | `com.fishengine.fish` |
| Version | 1.0.0 (build 1) | 1.0.0 (version code 1) |
| Store name | Fish: Team Card Game | Fish: Team Card Game |
| Step-by-step guide | **[APP_STORE.md](APP_STORE.md)** | **[PLAY_STORE.md](PLAY_STORE.md)** |
| Screenshots, ready to upload | `app/store/ios/screenshots/` (1320×2868, iPhone 6.9") | `app/store/play/screenshots/` (1080×1920) |
| Other store graphics | the icon is built into the app | `app/store/play/icon-512.png`, `feature-graphic.png` |
| Built and tested on every change | GitHub Actions → **ios** | GitHub Actions → **android** |

Privacy policy (both stores):
`https://fish-engine.vercel.app/play/privacy.html`
Account deletion page (Google asks for it):
`https://fish-engine.vercel.app/play/delete-account.html`

## iPhone in five steps

You need a Mac with **Xcode 16+**, **Node.js 20+**, and an **Apple Developer
Program** membership.

```bash
git clone https://github.com/kv1514/fish-researchp12
cd fish-researchp12/app
npm install
npm run ios        # copies the game in and opens the project in Xcode
```

1. Xcode → **App** target → **Signing & Capabilities** → *Team*: your team.
   Leave the bundle identifier as `com.fishengine.fish`.
2. Register that bundle ID: developer.apple.com → Certificates, Identifiers &
   Profiles → Identifiers → **+** → App IDs → `com.fishengine.fish`.
3. App Store Connect → My Apps → **+ New App**: name `Fish: Team Card Game`,
   bundle ID `com.fishengine.fish`, SKU `fish-1`.
4. Xcode: device menu → **Any iOS Device (arm64)** → **Product → Archive** →
   **Distribute App → App Store Connect → Upload**. Try it with
   **TestFlight** first.
5. Fill in the listing (every answer, ready to paste, is in
   [APP_STORE.md](APP_STORE.md#4-the-listing-ready-to-paste)), add the screenshots from
   `app/store/ios/screenshots/`, and **Submit for Review**.

## Android in short

**[PLAY_STORE.md](PLAY_STORE.md)** has every step and every form answer. To
build it yourself you need Android Studio (or JDK 21 + the Android SDK):

```bash
cd fish-researchp12/app
npm install
npm run android    # copies the game in and opens Android Studio
```

## What is *not* in this repository, on purpose

- **The Android upload key** (`fish-upload.jks` and its password). It's a
  secret, so it must never be committed. The owner has it, along with a
  ready-signed `fish-1.0.0-upload-to-play.aab`, and sends them to you
  privately. If nothing has been uploaded to Google Play yet, you can make
  your own key instead: whoever uploads first sets it.
- **Apple and Google developer accounts.** The app is listed under whichever
  account uploads it.
- **Server keys.** Nobody needs them to build or upload the app.

## Don't change

- **The app ID `com.fishengine.fish`.** It can't be changed once an app is
  uploaded, and the two stores and the sign-in links expect it.
- **The game files inside `ios/` or `android/`.** They're overwritten from
  `public/play/` on every build. Change the game in `public/play/` and run
  `npm run sync`.

## Updating the app later

Every new upload needs a higher number: in Xcode, bump **Build** (App target →
General); for Android, `FISH_VERSION_CODE` (the GitHub workflow does this
itself). Changes to the server (`api/`) need no new app at all: they go live
when merged.

## Remaking the store images

```bash
python3 scripts4/devserve.py 8420          # from the repo root, in another window
node store/make-screenshots.js             # Google Play
FISH_SHOT_OS=ios node store/make-screenshots.js   # App Store
node store/make-assets.js                  # Android icons + Play graphics
```

(`make-screenshots.js` uses Playwright: `npm install playwright` once.)
