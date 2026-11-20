# Putting Fish on the App Store

New here? Start with [README.md](README.md). This page is the iPhone half:
build, TestFlight, and every answer App Store Connect asks for, ready to paste.

What's already done:

- `ios/`: a real Xcode project (Swift Package Manager, no CocoaPods), iPhone
  only, portrait, iOS 14+, bundle ID `com.fishengine.fish`, version 1.0.0
  (build 1)
- the app icon (1024×1024, no transparency, as Apple requires) and launch screen
- native **haptics**, the native **share sheet** for invite codes, and
  `fish://join/ABCD` **deep links** (plus `fish://play` for a game against the
  bots and `fish://watch` for one the bots play by themselves)
- the export-compliance flag (`ITSAppUsesNonExemptEncryption = NO`: the app
  only uses HTTPS, which is exempt), so App Store Connect skips the encryption
  question
- Apple's privacy manifests, which ship inside Capacitor itself
- screenshots at 1320×2868 in `app/store/ios/screenshots/`
- privacy, support and account-deletion pages on the live site
- the game server, already running at `https://fish-engine.vercel.app`

## 1. What you need

- A **Mac** with **Xcode 16 or newer** (free, Mac App Store)
- **Node.js 20+** (nodejs.org)
- An **Apple Developer Program** membership ($99/year,
  developer.apple.com/programs)

## 2. Build it on your Mac

```bash
git clone https://github.com/kv1514/fish-researchp12
cd fish-researchp12/app
npm install
npm run ios          # copies public/play into the app, syncs, opens Xcode
```

In Xcode:

1. Click **App** in the left sidebar, then the **App** target.
2. **Signing & Capabilities** → *Team*: pick your developer team. Leave
   "Automatically manage signing" on.
3. **Bundle Identifier** is `com.fishengine.fish`, the same ID as the Android
   app. Register it in your developer account: developer.apple.com →
   Certificates, Identifiers & Profiles → Identifiers → **+** → App IDs → App →
   *Explicit*, `com.fishengine.fish`, no extra capabilities. It's permanent once
   the app is live.
4. Pick an iPhone simulator at the top and press **▶ Run**. Play a game.
5. Optional: plug in an iPhone, select it, press ▶ again. (First time: on the
   phone, Settings → Privacy & Security → Developer Mode on, then trust the
   developer under Settings → General → VPN & Device Management.)

## 3. Upload, and TestFlight first

1. App Store Connect (appstoreconnect.apple.com) → **Apps → + → New App**:
   - Platform **iOS**, Name **`Fish: Team Card Game`**, Primary language
     **English (U.S.)**, Bundle ID **`com.fishengine.fish`**, SKU **`fish-1`**,
     User access **Full Access**.
2. In Xcode: device menu → **Any iOS Device (arm64)**, then **Product →
   Archive**. When it finishes: **Distribute App → App Store Connect →
   Distribute**.
3. After 10–30 minutes the build shows up under **TestFlight**. Add yourself
   (and friends) as testers; they install the **TestFlight** app and play.
   Internal testers need no review.

Every new upload needs a higher **Build** number (App target → General →
Identity), then Archive again.

## 4. The listing, ready to paste

### App Information

| Field | Answer |
| --- | --- |
| Name | `Fish: Team Card Game` |
| Subtitle | `3 vs 3 cards, memory, teamwork` |
| Category | Primary **Games**, subcategories **Card** and **Strategy** |
| Content Rights | *Does not contain, show, or access third-party content* |
| Age Rating | see below |

### Pricing and Availability

Price **Free** (USD 0.00). Available in all countries.

### Version 1.0.0

**Screenshots**: the six files in `app/store/ios/screenshots/`, in order, in
the **iPhone 6.9" Display** slot. Smaller iPhone sizes are scaled from these.
The app is iPhone only, so no iPad screenshots are needed.

**Promotional Text** (170 max):

```
Two teams of three, one deck, and only the last two moves on screen. Remember who asked for what, and be the first team to win five sets.
```

**Description**:

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

**Keywords** (100 max, no spaces after commas):

```
literature,canadian,card game,team,memory,multiplayer,friends,bots,strategy,party,deduction
```

| Field | Answer |
| --- | --- |
| Support URL | `https://fish-engine.vercel.app/play/support.html` |
| Marketing URL | leave empty, or `https://fish-engine.vercel.app/play/` |
| Version | `1.0.0` |
| Copyright | `2026` followed by the owner's name |
| Build | the one uploaded in step 3 |
| Sign-in required | **No** (the whole app works as a guest) |
| Contact information | the person Apple should call or email about the review |
| Release | *Automatically release this version* (or manually, if you'd rather pick the day) |

**App Review notes**:

```
No account is needed: tap "Play as guest" on the first screen, then "Play vs Bots" for a game against the computer.

Online tables: tap "Quick Play". If no one else is online, the table fills with bots after about 30 seconds. To test a private table, tap "Private Table", then join its 4-letter code from a second device.

Accounts (optional, for ratings): tap "Create account" on the first screen (or, as a guest, the name at the top of the home screen) and use any email address and password. No confirmation email is needed. To delete the account: tap the name at the top of the home screen to open the profile, then "Delete account".

There is no free-text chat; players can only send a fixed set of emoji. Players can be reported from their profile.
```

### App Privacy

**Privacy Policy URL**: `https://fish-engine.vercel.app/play/privacy.html`

Answer **Yes, we collect data**, and **No** to tracking. Each type below is
**linked to the user** (to their in-game profile, not a real identity) and
used only for **App Functionality** (Apple counts fraud prevention as part of
it):

- *Contact Info → Email Address* (and *Phone Number* only if phone sign-in is
  ever switched on): how an account signs in. Guests give neither.
- *Identifiers → User ID*: the account's profile ID.
- *User Content → Other User Content*: the display name.
- *User Content → Gameplay Content*: rating, results, recent games.
- *Usage Data → Product Interaction*: move times, and whether the app left the
  screen during the player's turn, kept for fair-play checks.

Nothing else is collected: no location, contacts, photos, ads, analytics or
crash data.

### Age Rating

Answer **None / No** to everything: violence, sexual content, profanity,
horror, drugs, medical, gambling, simulated gambling, contests, loot boxes,
ads, and unrestricted web access. Fish is a card game with no betting or chips:
sets are won, not money. On **messaging and chat**: **No**, because players can
only send preset emoji. If asked about **user-generated content**: the only
kind is the display name each player picks, which other players see and can
report. It should come out at one of the youngest ratings.

## 5. Submit

On the version page: **Add for Review → Submit to App Review**. Review usually
takes a day or two. If Apple replies with a question, answer it in App Store
Connect's **App Review** messages.

## What could get it rejected, and what's been done about it

| Risk | Guideline | Status |
| --- | --- | --- |
| Online play down during review | 2.1 | Server is live; check `https://fish-engine.vercel.app/api/health` says `"room_backend": "postgres-rpc"` before submitting |
| "It's just a website" | 4.2 | Screens are built into the app, not loaded from a URL; native haptics, share sheet and deep links; real-time multiplayer |
| Strangers talking to each other | 1.2 | No free-text chat at all, only preset emoji. Names are cleaned of invisible characters. Any signed-in player can be reported (cheating or offensive name) from their profile |
| Account deletion | 5.1.1(v) | In the app: Profile → Delete account (removes the sign-in too) |
| Guest access | 5.1.1 | Every table can be played as a guest, unrated |
| Sign in with Apple | 4.8 | Only needed if Google sign-in is offered. It's off; and if it's ever switched on, the iPhone app hides Google until Apple sign-in is on too |
| Copying another app's look | 5.2 | Name, colours, icon and art are original. Don't use another app's name or screenshots in the listing |
| Gambling | 5.3 | No money, chips or betting. Don't call it "poker" in the listing |

## No Mac?

`.github/workflows/ios.yml` builds the app on one of GitHub's Macs every time
`app/` or `public/play/` changes: it launches it in an iPhone simulator, checks
the home screen drew, then films a whole game the bots play on the live server
(**Actions → ios**; the screenshots and `game.mp4` are attached to each run).
It doesn't sign or upload. That workflow can be extended to upload to
TestFlight once the developer account exists. It needs an **App Store Connect
API key** (Users and Access → Integrations → App Store Connect API) stored as
repository secrets.

## Updating the app later

- **Server changes** (anything in `api/`) go live when merged. No new app
  build is needed.
- **Game screen changes** (anything in `public/play/`) need `npm run sync`, a
  higher Build number, Archive, upload, and a new review.

## For the owner: the server behind the app

Not needed for uploading. Online play runs on Supabase project **fish-rooms**
and Vercel project **fish-engine** (which has `SUPABASE_URL`,
`SUPABASE_PUBLISHABLE_KEY` and `FISH_DB_KEY`). `FISH_DB_KEY` is a narrow key
that only reaches the `fish_store_*` room functions; the database stores only
its SHA-256. It is *not* the Supabase service key, which is never needed.

**Free Supabase projects pause after a week with no traffic.** If online play
stops working after a quiet spell, open supabase.com → fish-rooms → Restore.
Do this before submitting if the site has been quiet.

**To rotate the key:** make a new random value of 32+ characters, put its
SHA-256 (hex) into the database:

```sql
update fish_private.store_key set key_sha256 = '<sha256 hex of the new key>' where id = 1;
```

then set `FISH_DB_KEY` in Vercel to the new value and redeploy.
