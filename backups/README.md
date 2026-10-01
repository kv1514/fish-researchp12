# leakcheck-backup-2026-08-24.json

A dump of the `LeakCheck` Supabase project (ref `fgxhqypimwjvkfdfduul`), taken
immediately before that project was deleted on 2026-08-24 to free a slot in the
organisation's two-project free tier for `fish-rooms`.

Deleting it was asked for explicitly. Taking the dump first was not, and is here
because a project deletion is not reversible and "there was nothing in it" is a
claim worth being able to check rather than assert.

What was actually in it, verified by `count(*)` rather than by the row estimates
`list_tables` reports:

  leads       0 rows   -- the table estimate said 1; the count said 0
  pageviews  45 rows   -- privacy-respecting analytics, last entry 2026-08-19

So no business contacts were lost. The pageviews are page path, referrer,
coarse device class and viewport width, with no cookie, IP, user id or
fingerprint, from `leakcheck-site.vercel.app`.

Restoring means recreating the two tables and reinserting from the JSON; the
schema is implied by the rows and the table comments are reproduced below.

  leads:      "Inbound leads from leakcheck-site. side=warehouse means they run
               a 3PL and want a leak check; side=brand means they pay a 3PL and
               want an invoice audit."
  pageviews:  "Privacy-respecting page views from leakcheck-site. No cookies,
               no IP, no user id, no fingerprint. Only: which page, where the
               visit came from, coarse device class, viewport width. Purpose:
               tell the difference between nobody visiting and visitors
               bouncing."
