# Roadmap

Every milestone ends with the same documents running in three places, against
a local `cvcpkg server` or the dev registry:

- **stock** `ari` with the FTXUI backend;
- **stock** `ari` with the tvision backend;
- ari's xterm.js page in the browser (FTXUI on wasm).

**The terminal is the primary target.** A feature isn't done until it works in
both backends and an `ari snapshot` test covers it. The browser runs the same
terminal UI, so there is no separate browser design. Where the web pages draw
something graphical, such as the downloads chart, the terminal draws it with
half-block or braille cells.

Because the client is documents only, any feature it needs from a host has to
be a **generic** Ariadne feature in libcvc, available through host flags or the
document itself. Those features are the L-items below. Most of them are the
same features nicotina needs, and they keep nicotina's numbers. Server-side
work on cvcpkg is tracked as C-items in
[cy-pca/cvcpkg](https://github.com/cy-pca/cvcpkg).

## libcvc features the client needs

| # | Feature | Status | Needed by |
|---|---------|--------|-----------|
| L1 | Hosts can turn on the HTTP verbs and the `http(s)://` URI handler, with an origin allowlist that denies by default (`--net-allow`) | transfix/libcvc#888 open | M0 |
| L2 | Host-owned credentials: a Bearer header for bound origins only, a token captured from a reply and redacted, and optional 0600 persistence. Tokens never enter state | transfix/libcvc#888 open | M2 |
| L2a | Use L2 with cvcpkg's tokens. #888 covers capturing `access_token` from `/v1/auth/device/token`, sending it, and signing out. Still needed: (a) capturing or redacting `refresh_token` too, which #888 leaves visible to the document; (b) sending a stored credential in a form field, for the refresh at `/v1/auth/token`; (c) a way to supply a `cvctok_` token, such as a host flag that reads it from an environment variable | partly covered by #888 | M2 |
| L3 | `json-parse` / `json-encode`, so documents can read REST replies | transfix/libcvc#883 open | M0 |
| L4 | The HTTP verbs work on the single-threaded wasm page (`-sASYNCIFY`, no pthreads), so the browser needs no COOP/COEP. #887 links `-sFETCH`, and #888 runs the verbs inline there. No browser test makes a request through #887's page with #888's `--net`. A call that runs inline blocks its program until the reply arrives | likely works; untested | M0 (browser) |
| L5 | A scrolling, virtualized list or table, wrapped text, and a filter box, in **both terminal backends** and FTXUI on wasm | open | M0 |
| L6 | A general WebSocket verb whose frames arrive as `on_signal`, natively and in wasm | open | M1 |
| L8 | ari's xterm.js page runs `?src=<same-origin .ari URL>`, with host flags taken from `ariadne.config.json` | transfix/libcvc#887 open | M0 (browser) |
| L10 | ari's xterm.js page as a cvcpkg package, so a registry can serve it (#887 ships it in `arigl-web`) | transfix/libcvc#887 open | M5 |
| L11 | Terminal helpers: copy to the clipboard with OSC 52, OSC 8 hyperlinks, and a half-block QR code for the pairing URL | open | M2 |

`ari` itself is already packaged. The xterm.js page has been live since
transfix/libcvc#710.

## cvcpkg features the client needs

| # | Feature | Needed by |
|---|---------|-----------|
| C1 | The registry serves the documents and ari's xterm.js page at `/apps/cypkg/`, with a config that passes `--net-allow {origin}` | M0 (browser) |
| C2 | Check that every action the web pages do through cookie forms also has a Bearer JSON endpoint. Tokens, org members and admin stats do (`/v1/tokens`, `/v1/orgs/{slug}/members`, `/v1/admin/*`). Add the ones that don't | M3 |
| C3 | Add the `cypkg` recipe to the shared recipe set | M5 |
| C4 | One package's dependencies and dependents. `/v1/deps` returns the whole catalog's graph (1.75 MB on cvcpkg.org), which is too much to fetch for one package page. For now the package page shows nothing for dependencies | M1 |

## Milestones

- **M0, browse** (in progress; see M0 status below): anonymous and read-only. Search with the web page's
  filters; a package page with versions, variants, dependencies and the
  `cvcpkg install` lines. Works in FTXUI, tvision and the browser. Ship the
  `bin/cypkg` launcher with `--server` and `--tvision`. Add `ari snapshot`
  tests to CI. Measure the wasm page's size and time to first frame.
- **M1, live:** builders, the paged build list, a build's details with a live
  log tail, and the activity feed, all over `/v1/live/ws`. Fall back to
  polling on close code 4004. Also orgs, tags and the recipe list.
- **M2, sign in:** a pairing code (`/v1/auth/device`), shown as a URL, a code
  and a QR code. Also: a pasted `cvctok_` token, `whoami`, private orgs, and
  refresh when a session expires. Persistence is native only; in the browser
  the session lasts as long as the page.
- **M3, act:** publisher actions on builds: cancel, pause and resume. Mint
  and revoke tokens, list and revoke sessions, and manage org members. Browse
  a recipe's files and show the downloads chart.
- **M4, admin:** registry stats, health, the audit log, principals, and
  approving token requests.
- **M5, ship:** publish the cvcpkg recipe for every platform `ari` is
  packaged for. cvcpkg.org serves `/apps/cypkg/`. CI runs an end-to-end
  smoke test against a local registry.
- **M6, maybe:** the same documents in `arigl`, if they need nothing
  terminal-only.

## M0 status

Done, and checked with an `ari` built from libcvc master plus #888 and #883:

- `share/cypkg/main.ari`. **Search:** a query and the platform, arch and link
  filters, paged 10 rows at a time, sent with `facets=true` so that the
  package count covers every match. **Package page:** description, latest
  version, license, homepage, tags, the `cvcpkg install` line, and its builds
  a page at a time. Results are build rows, as on the web page.
- `bin/cypkg` and `bin/cypkg.cmd`. Each allows only the registry's origin
  (`--net-allow`). `cypkg.cmd` has not been run on Windows.
- `tests/snapshot.sh`: 7 cases against the fixture registry, all passing.
- Checked by hand:
  - FTXUI and tvision in a 100x30 tmux pane: typing a query, Enter to search,
    Tab to a row's Open, and Back;
  - both views against https://cvcpkg.org.

To do for M0:

- **CI.** It waits for an `ari` package with #888 and #883. Until then the
  tests run locally.
- **The browser path**: #887's xterm.js page with `"flags": ["--net"]`, served
  by C1. Untested: see L4.
- **Wrapped text (L5).** Until it lands, long descriptions are cut at 89
  characters.
- Measure the wasm page's size and time to first frame.
