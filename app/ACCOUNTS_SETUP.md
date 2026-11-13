# Switching on accounts and ratings

Everything is in the app already. These steps are in the Supabase dashboard for
the **fish-rooms** project (supabase.com → fish-rooms). Each sign-in method
appears in the app by itself once it is on; nothing needs redeploying.

## 1. Ratings and profiles: run the SQL once

**SQL Editor → New query** → paste all of `scripts4/profile_rpc.sql` → **Run**.
Safe to run again. Until this has run, the app says ratings aren't switched on
and everyone plays unrated.

## 2. Email and password (Gmail or any address)

**Authentication → Sign In / Providers → Email**: make sure it is enabled, and
turn **Confirm email OFF**.

Why off: Supabase's built-in email service only delivers to members of your
own Supabase organisation, so a confirmation link would never reach a player.
With confirmation off, sign-up works at once. If you later add your own email
sender (**Authentication → Emails → SMTP settings**, e.g. a free Resend
account), you can turn confirmation back on; the app already handles "check
your email".

## 3. Where sign-in may return to

**Authentication → URL Configuration**:

- **Site URL**: `https://fish-engine.vercel.app/play/`
- **Redirect URLs**: add `https://fish-engine.vercel.app/play/` and `fish://auth`

Needed for Google and Apple; harmless otherwise.

## 4. Google (optional)

1. console.cloud.google.com → create a project → **APIs & Services →
   Credentials → Create credentials → OAuth client ID → Web application**.
2. **Authorized redirect URI**: `https://<your-project-ref>.supabase.co/auth/v1/callback`
   (the exact value is shown on Supabase's Google provider page).
3. Copy the client ID and secret into **Authentication → Sign In / Providers →
   Google**, and enable it.

On the website the Google button appears straight away. In the iPhone app it
appears only once **Apple** is on as well, because App Review guideline 4.8
requires Sign in with Apple wherever Google sign-in is offered.

## 5. Apple (optional; needs the $99 Apple Developer account)

**Authentication → Sign In / Providers → Apple**, following Supabase's steps
(a Services ID and a key from developer.apple.com).

## 6. Phone number (optional; costs per text)

**Authentication → Sign In / Providers → Phone** with an SMS provider (Twilio,
MessageBird, Vonage or Textlocal). Each text costs a few cents through them.

## Guests

Nothing to set up. Guests choose a name and play every table, unrated. Ratings
and the leaderboard are for accounts only, which is also what stops a closed
account from simply coming back as a fresh guest with a fresh rating.
