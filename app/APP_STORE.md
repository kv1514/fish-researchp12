# Getting Fish onto the App Store

This folder is the iOS app. It is a [Capacitor](https://capacitorjs.com) shell
around the web client in `public/play/` — the website and the app ship the exact
same files, so a change to the game is made once.

What's already done here:

- `ios/` — a real Xcode project (Swift Package Manager, no CocoaPods needed)
- the app icon (1024×1024, no transparency, as Apple requires) and launch screen
- native **haptics**, the native **share sheet** for invite codes, and
  `fish://join/ABCD` **deep links**
- portrait-only on iPhone, dark status bar, and the export-compliance flag set
  (the app only uses HTTPS, which is exempt — so App Store Connect won't stall
  on the encryption question)
- a privacy policy at `/play/privacy.html`

What you have to do yourself, because it needs your Mac and your Apple account,
is below.

---

## Before anything: online play has to be switched on

The app talks to `https://fish-engine.vercel.app`. **Apple's reviewers will tap
Quick Play.** If online tables aren't running, they see "Online tables aren't
switched on", and an app with a dead main button gets rejected (guideline 2.1,
incomplete functionality). So first:

1. **Merge the pull request** so the live site has the new `/api/t_*` routes
   and the CORS rule that lets the app call it. Until then the iOS app is
   talking to a server that doesn't know about tables.
2. **Unpause your Supabase project `fish-rooms`** (supabase.com → the project
   → *Restore*). Free organizations can only have two active projects, and you
   currently have two (SideSpace Marketplace, hedgeos), so you may need to
   pause one or upgrade.
3. In the Supabase **SQL editor**, run `scripts4/room_schema.sql` from this
   repo (safe to run twice — skip if the `fish_rooms` table is already there).
4. In **Vercel → fish-engine → Settings → Environment Variables**, add for
   Production *and* Preview:
   - `SUPABASE_URL` = `https://guqeesmrveijysuveuke.supabase.co`
   - `SUPABASE_SERVICE_KEY` = Supabase → Project Settings → API Keys → the
     **secret / service_role** key. Paste it only into Vercel. Never commit it
     or put it in the app — it bypasses every database rule.
5. Redeploy (Vercel → Deployments → ⋯ → Redeploy), then open
   `/play/` and press Quick Play. If you get a table, you're live.

---

## 1. What you need

- A **Mac** with **Xcode 16 or newer** (free, Mac App Store)
- **Node.js 20+** (nodejs.org)
- An **Apple Developer Program** membership — $99/year,
  developer.apple.com/programs. Enrolment can take a day or two.

## 2. Build it on your Mac

```bash
git clone https://github.com/kv1514/fish-researchp12
cd fish-researchp12/app
npm install
npm run ios          # copies public/play into the app, syncs, opens Xcode
```

In Xcode:

1. Click **App** in the left sidebar, then the **App** target.
2. **Signing & Capabilities** → *Team*: pick your developer team.
3. **Bundle Identifier**: change `com.example.fish` to something you own,
   like `com.yourname.fish`. It's permanent once the app is live, so pick
   carefully. Put the same value in `capacitor.config.json` → `appId`.
4. Pick an iPhone simulator at the top and press **▶ Run**. Play a game.
5. Plug in your own iPhone, select it, press ▶ again. (First time: on the
   phone, Settings → General → VPN & Device Management → trust yourself.)

## 3. TestFlight first — play it with your friends

1. App Store Connect (appstoreconnect.apple.com) → **My Apps → +  → New App**.
   - Name: must be unique on the whole store. "Fish" is certainly taken;
     try something like **"Fish: Team Card Game"** or **"Fish Table"**.
   - Bundle ID: the one you chose above. SKU: anything, e.g. `fish-1`.
2. In Xcode: top bar device → **Any iOS Device (arm64)**, then
   **Product → Archive**. When it finishes: **Distribute App → App Store
   Connect → Upload**.
3. After ~15 minutes the build appears under **TestFlight**. Add yourself and
   friends as testers (up to 100 by email, no review needed for internal
   testers). They install the TestFlight app and play.

Every new build: bump the **Build** number (App target → General), then
Archive again.

## 4. Submit for review

In App Store Connect, on your app's page:

- **Screenshots**: iPhone 6.9" (1320×2868) is required. Take them in the
  iPhone 16 Pro Max simulator with ⌘S. Good ones: the home screen, a lobby with
  a code, a table mid-game with the countdown ring, the ask sheet, the win
  screen.
- **Description / keywords**: e.g. "Fish (also called Literature) is a 6-player
  team card game. Quick-play public tables, private tables with a join code,
  turn timers, or practice against the bots."
- **Privacy Policy URL**: `https://fish-engine.vercel.app/play/privacy.html`
- **Support URL**: `https://fish-engine.vercel.app/` (or any page you control)
- **App Privacy** questionnaire: the honest answers are — no tracking; the only
  data is the **display name** the player types, which is shown to other players
  and deleted with the table within 6 hours; not linked to identity. (Category:
  *User Content → Other User Content*, used for *App Functionality*.)
- **Age rating**: no gambling, no chat, no violence → it should come out 4+.
  Answer "No" to simulated gambling: there are no bets or chips, only sets won.
- **App Review notes**: "Online tables: press Quick Play. If no one else is
  online, the table fills with bots after 30 seconds. To test a private table,
  press Private Table, then join its 4-letter code from a second device or the
  simulator."

Then **Add for Review → Submit**. Review usually takes a day or two.

## What could get it rejected, and what's been done about it

| Risk | Guideline | Status |
|---|---|---|
| Online play down during review | 2.1 | **Your step** — see the top of this file |
| "It's just a website" | 4.2 | UI is bundled in the app, not loaded from a URL; native haptics, share sheet and deep links; real-time multiplayer |
| Strangers talking to each other | 1.2 | No free-text chat at all — only preset emoji reactions. Names are cleaned of invisible characters. If a reviewer asks about offensive names, add a word filter or a "report player" button |
| Copying another app's look | 5.2 | Layout is the general poker-table style; name, colours, icon and art are original. Don't use another app's name or screenshots in the listing |
| Gambling | 5.3 | No money, chips or betting — make sure the description doesn't say "poker" |

## Updating the app later

- **Server changes** (anything in `api/`) go live when merged — no new app
  build needed.
- **Game screen changes** (anything in `public/play/`) need `npm run sync`,
  a new build number, Archive, and a new review.

## Android (later)

```bash
npm install @capacitor/android
npx cap add android
npx cap open android      # needs Android Studio
```

Google Play costs $25 once. The same web files and the same API work there.
