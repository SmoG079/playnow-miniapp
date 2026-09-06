# PlayNow frontend prototype

Phase 1 only: six core pages and the message empty state, using uni-app,
Vue 3, TypeScript, Pinia and Wot UI 2.3.2. The native mini-program is untouched.

## Run and verify

```sh
npm ci
npm run dev:prototype
npm run typecheck
npm test
npm run wot:lint
npm run build:prototype
npm run build:mp-preview
```

Open http://127.0.0.1:5188/. Desktop view retains a phone-width layout.
The H5 build is in dist/build/h5; the WeChat preview is in
dist/build/mp-weixin. No real AppID or upload credentials are included.
`npm run build:mp-weixin` intentionally fails until business migration and
acceptance are complete. Do not remove this guard to publish prototype data.

The CLI component check uses the Wot toolchain installed at the repository
root. Run root `npm ci` first on another machine.

## Included flows

- Home: feed tabs, combined date/NTRP filters, reset and empty results.
- Courts: search and sort, detail navigation, 30-minute slot selection.
- Booking: adjacent slots on one court, one-hour minimum, price summary,
  confirmation and a session-only booking record on the profile page.
- Activities: detail and capacity-aware, duplicate-safe simulated joining.
- Publish: required title and price, time validation, new activity in the feed.
- Profile: session bookings/registrations/posts, demonstrative role menu.
- Messages: explicit unavailable service state, no fabricated conversations.

All records are fictitious and memory-only; refreshing resets them. No API,
location permission, real account login, payment or user notifications occur.
The selectable slots are demonstration inventory, not live availability.

## Browser verification

`tests/prototype.cjs` uses Playwright with the installed Edge browser. Supply
PLAYWRIGHT_MODULE when using a shared Playwright installation, then run:

```sh
node tests/prototype.cjs artifacts
```

It checks 375/390/430px layouts, images, filters, booking, joining, publishing,
desktop framing, runtime errors and absence of external requests. Long-page
review screenshots anchor the persistent navigation to the export's bottom;
interactive previews retain normal fixed viewport navigation.

WeChat compilation is verified, but developer-tools and iOS/Android physical
device acceptance have not been performed. Production CI/CD and the remaining
business pages are deliberately deferred until visual approval.

## Asset sources

The sample photos do not represent actual listed venues:

- Court: https://images.unsplash.com/photo-1578966663421-00f3bfebfa89
- Tennis: https://images.unsplash.com/photo-1554068865-24cecd4e34b8

## Approval checkpoint

Review the six-page prototype before proceeding with the 30-page migration.
Keep existing local staged changes and the native frontend intact. Preserve
backend contracts when replacing prototype fixtures with real services.
