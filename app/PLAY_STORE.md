# Putting Fish on Google Play

New here? Start with [README.md](README.md). This page is the Android half.

Everything Google asks for is ready: the app bundle, the store graphics, the
screenshots, and the answers to every form, below, to copy and paste. What only
you can do is make the account, click through the forms, and find 12 testers.

| What | Where |
| --- | --- |
| App bundle to upload (`.aab`) | the signed `fish-1.0.0-upload-to-play.aab` the owner sends you privately, or build your own (see the end of this page) |
| App ID (package name) | `com.fishengine.fish` (permanent once uploaded) |
| Store icon, 512×512 | `app/store/play/icon-512.png` |
| Feature graphic, 1024×500 | `app/store/play/feature-graphic.png` |
| Phone screenshots, 1080×1920 | `app/store/play/screenshots/` (6) |
| Privacy policy | https://fish-engine.vercel.app/play/privacy.html |
| Account deletion page | https://fish-engine.vercel.app/play/delete-account.html |
| Support page | https://fish-engine.vercel.app/play/support.html |

## 1. The developer account (once, $25)

1. Go to **play.google.com/console** and sign in with the Google account that
   should own the app.
2. Choose **Yourself** (a personal account), pay the one-time **$25**, and
   verify your identity. Google may also ask you to confirm you have an
   Android phone, through the Play Console app.

A personal account made after November 2023 has to run a **closed test with at
least 12 testers for 14 days in a row** before the app can go public (step 5).
An organisation account skips that, but needs a D-U-N-S number, which can take
weeks.

## 2. Create the app

**Play Console → Create app**

- App name: `Fish: Team Card Game`
- Default language: English (United States)
- App or game: **Game**
- Free or paid: **Free**
- Tick the two declarations → **Create app**

## 3. The forms (Dashboard → "Set up your app")

**App access**: *All functionality is available without any access
restrictions.* (Anyone can play as a guest, and anyone can make an account.)

**Ads**: *No, my app does not contain ads.*

**Content rating**: start the questionnaire, enter your email, category
**Game**, then:

- Violence, blood, sexual content, nudity, crude humour, fear: **No**
- Gambling: real-money gambling **No**; simulated gambling **No** (Fish is a
  card game with no betting, chips or casino games)
- Controlled substances, profanity: **No**
- Do users interact or exchange content? **Yes**: players see each other's
  chosen names and quick emoji reactions. There is **no** free-text chat.
- Shares the user's location: **No**. Digital purchases: **No**.

Expected result: rated for everyone (PEGI 3 / ESRB Everyone), with "Users
Interact".

**Target audience**: ages **13–15, 16–17 and 18+**. (Leave the under-13 groups
unticked; they bring Google's extra Families rules.) "Could the app
unintentionally appeal to children?" → **No**.

**News app**: No. **Government app**: No. **Financial features**: none.
**Health**: none.

**Advertising ID**: *No* (the app does not use it).

**Data safety**:

- Does your app collect or share any of the required user data types? **Yes**
- Is all user data encrypted in transit? **Yes**
- Do you provide a way for users to request that their data be deleted?
  **Yes**. Delete account URL:
  `https://fish-engine.vercel.app/play/delete-account.html`
- Account creation: **Username and password**, plus **OAuth** if you turn on
  Google or Apple sign-in, and **Phone number** only if you turn on phone
  sign-in.

Data types. For each: **collected**, **not shared**, **not processed
ephemerally**:

| Type | Required? | Purposes |
| --- | --- | --- |
| Personal info → **Name** (the name shown at the table) | Required | App functionality, Account management |
| Personal info → **Email address** | Optional (guests give none) | Account management |
| Personal info → **Phone number** (only if phone sign-in is on) | Optional | Account management |
| Personal info → **User IDs** (profile id) | Optional | App functionality, Account management |
| App activity → **App interactions** (games, rating, move times, whether the app left the screen during your turn) | Required | App functionality, Fraud prevention, security, and compliance |
| Device or other IDs (a random key per signed-in device) | Optional | Account management, Fraud prevention, security, and compliance |

Not collected: location, contacts, photos, files, audio, financial info,
health, messages, browsing history, crash logs, diagnostics. "Shared" means
handing data to a third party for its own use. Supabase (accounts and
database) and Vercel (the server) are service providers acting for the app,
which Google does not count as sharing.

## 4. Store listing (Grow users → Store presence → Main store listing)

**App name** (30 max): `Fish: Team Card Game`

**Short description** (80 max):

```
The 3 vs 3 card game of memory and teamwork. Play bots, friends or rated games.
```

**Full description**:

```
Fish is the classic team card game, also known as Literature or Canadian Fish: two teams of three, one deck, and a lot to remember.

HOW IT WORKS
The deck is split into nine sets of six cards. On your turn, ask an opponent for a card from a set you hold. If they have it, it's yours and you go again; if not, the turn passes to them. When your team holds all six cards of a set, declare it, and say which teammate holds each card. Get it right and your team wins the set. The first team to five sets wins.

ONLY THE LAST TWO MOVES
Every ask is public, but Fish only shows the last two moves. Everything before that is up to your memory. Who asked for what, who said no, who must be holding which card: keep track, and outplay the table.

PLAY YOUR WAY
• Quick Play: join a public table in seconds. Every move has a 20-second clock.
• Private tables: share a four-letter code with friends. The host picks the time per move and an optional time bank, and empty seats are filled by bots.
• Practice against bots: play the same engine the game was built around, at your own pace.

RATINGS AND FAIR PLAY
Create an account to get a rating, a profile and a place on the leaderboard. Public games are rated by team, with built-in fair-play checks. Or play as a guest with just a name.

No ads. No tracking. Delete your account any time from your profile.
```

**Graphics**: upload `app/store/play/icon-512.png` as the app icon,
`app/store/play/feature-graphic.png` as the feature graphic, and the six
files in `app/store/play/screenshots/` as phone screenshots, in order.

**Category**: Games → **Card**. Tags: Card, Multiplayer, Strategy.
**Contact details**: your email (required, shown publicly); website
`https://fish-engine.vercel.app/play/`.
**Privacy policy** (App content → Privacy policy):
`https://fish-engine.vercel.app/play/privacy.html`

## 5. Closed test: 12 testers, 14 days

1. **Test and release → Testing → Closed testing → Create track**. The
   default "Alpha" is fine.
2. **Testers** tab → *Create email list* → add **at least 12** Gmail addresses
   (friends, family) → Save. Leave a few spare: the 14 days count only while
   12 or more stay opted in.
3. **Releases** tab → *Create new release*.
   - When asked about **app signing**, keep **"Use Google-generated key"**.
     The key in this repo's setup is your *upload* key; Google holds the key
     that signs what players install.
   - Upload `app-release.aab`. Release name: `1.0.0`. Release notes:
     ```
     First release: play Fish 3 vs 3 against bots, with friends at a private table, or in rated public games.
     ```
   - **Review release → Start rollout to Closed testing**.
4. Back on **Testers**, copy the **opt-in link** and send it to your testers.
   Each opens it, taps *Become a tester*, then installs Fish from Google Play.
   The first review of a new app can take a few days.
5. Ask them to play now and then. After **14 days** with 12+ testers opted in,
   **Dashboard → Apply for production**: answer the questions about the test
   (who tested, what feedback you got, what you changed).

## 6. Production

Once production access is approved: **Production → Create new release → Add
from library** (the same bundle) → rollout. Reviews of updates usually take
hours to a couple of days.

## Updates later

Every upload needs a **higher version code**. The android workflow numbers
its builds 100 + the run number, so each run is higher than the last. For it to
sign builds, add two repository secrets (GitHub → Settings → Secrets and
variables → Actions → *New repository secret*):

- `ANDROID_UPLOAD_KEYSTORE_BASE64`: the upload key file, base64-encoded:
  `base64 -w0 fish-upload.jks` (Mac: `base64 -i fish-upload.jks`)
- `ANDROID_UPLOAD_KEYSTORE_PASSWORD`: its password, from
  `keystore.properties`

Then each run's *fish-android* artifact has a signed `app-release.aab`, ready to
upload.

**Keep the upload key and its password safe and private**, and never commit
them. If you lose it, Play Console (*Setup → App signing → Request upload key
reset*) can replace it, but that takes a few days.

## Building on your own computer

With Android Studio installed: `cd app && npm install && npm run android`. For
a signed release, put `keystore.properties` (storeFile, storePassword, keyAlias,
keyPassword) in `app/android/`; it is git-ignored. Then:

```
cd app/android && ./gradlew bundleRelease
```

The bundle is in `app/android/app/build/outputs/bundle/release/`.

## Images

`node app/store/make-assets.js` redraws every Android icon and the store
graphics from `public/play/icon-square.svg`.
`node app/store/make-screenshots.js` retakes the screenshots against a local
server (`python3 scripts4/devserve.py 8420`).
