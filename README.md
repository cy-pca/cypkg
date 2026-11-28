# cypkg

**cypkg** is a terminal client for [cvcpkg](https://cvcpkg.org) registries,
written as
[Ariadne](https://github.com/transfix/libcvc/blob/master/docs/ARIADNE.md)
documents. It is an alternative to the registry's web pages: you can search
packages, read recipes, watch builders and build logs live, and manage tokens,
orgs and the registry. The same documents run natively in a terminal and in
the browser, where https://cy-pca.github.io/cypkg/ offers them graphically
(`arigl`) or in a terminal (FTXUI or tvision on xterm.js).

> **Status: M0 in progress.** Search and package pages work in both terminal
> backends, in `arigl` and in the browser. They need `ari` 3.7.6 or newer (the first
> release with what they use), and in the browser the `arigl-web` package,
> 4.0.9 or newer. No registry serves `/apps/cypkg/` yet. See [docs/ROADMAP.md](docs/ROADMAP.md).

## How it runs

The client is **documents only**: `.ari` files plus `.ari` components. It runs
in the **unmodified** `ari` host from cvcpkg, with no custom host binary,
compiled-in widget or patch.

```bash
cvcpkg install cypkg
cypkg                              # https://cvcpkg.org
cypkg --server https://my.registry.example
cypkg --tvision                    # the tvision desktop instead of FTXUI
```

The `cypkg` package depends on `ari`. It installs:

- `share/cypkg/`: the documents, components and a network policy file.
- `bin/cypkg` (`cypkg.cmd` on Windows): a launcher script. It runs the main
  document with `ari run`, passing the host flags the client needs. One such
  flag allows network access to the chosen registry and nothing else. It runs
  over SSH and in either of ari's terminal backends, FTXUI (the default) and
  tvision.

**The terminal is the primary target.** Every feature has to work, and be
tested, in `ari` with both backends. CI renders frames with `ari snapshot`.
The same documents run in `arigl` (Dear ImGui) too, which the browser build
offers; CI checks there only that the app starts and searches (M6 in the
roadmap).

**In the browser**, the single-threaded `arigl-web` package (4.0.9 or newer)
ships three clients in `share/arigl-web/`, and the site offers all three
from a landing page:

- `arigl.html`: `arigl`, Dear ImGui on WebGL (the package's `index.html`).
- `ari.html`: ari's FTXUI backend in an xterm.js terminal (transfix/libcvc#887).
- `ari_tvision.html`: ari's tvision desktop in the same terminal.

A registry serves the site at `https://<registry>/apps/cypkg/`. Because that
is the registry's own origin, it needs no CORS.

- `tools/site.sh ARI_WEB OUT` assembles that directory from the package's
  page files, `share/cypkg/` and the landing page, `web/index.html`.
- `web/ariadne.config.json`, which all three pages read, pins the document to
  `main.ari` and turns the network on for the page's own origin only (`--net`).
- The config also passes `--server {origin}`, so cypkg browses the registry
  that serves it.
- Host flags come only from that file, never from the URL.
- The page runs under a strict Content-Security-Policy: no inline code or
  style, no eval, nothing from another origin.

**GitHub Pages, for now.** Until a registry serves it, CI publishes the page
from `main` to https://cy-pca.github.io/cypkg/, on each push and on a `test` run
started by hand on `main` (which moves the page to the newest `arigl-web`).
- That build uses `web/ariadne.config.pages.json`, which browses
  https://cvcpkg.org: `--net-allow https://cvcpkg.org` and
  `--server https://cvcpkg.org`.
- That's another origin, so cvcpkg.org allows `https://cy-pca.github.io`
  with CORS (`CVCPKG_CORS_ORIGINS`). Without that, the page loads and says
  "search failed: ... (network or CORS)".
- The site also carries the package's `LICENSE` and `THIRD_PARTY_NOTICES.md`
  (as `.txt`, so a browser shows them), which the landing page links: the
  clients are libcvc's LGPL-2.1 builds.

To try it, serve a site with the fixture registry and open
`http://127.0.0.1:8766/apps/cypkg/`:

```bash
cvcpkg install arigl-web --platform wasm --arch wasm32 --link static --prefix ./web
tools/site.sh ./web/share/arigl-web site
python3 tests/registry/fixture_registry.py --port 8766 --site site
```

## What it talks to

The client uses only a registry's public API, the same one the `cvcpkg` CLI
and the web pages use:

- the REST API under `/v1`, documented at `/docs` on any registry and in
  cvcpkg's `docs/api-reference.md`;
- the `/v1/live/ws` WebSocket, for the activity, builders and builds topics
  and live build logs;
- sign-in with a pairing code (`POST /v1/auth/device`, approved at `/link`),
  which works over SSH and in the browser. It gives the same `cvcses_`
  sessions as `cvcpkg login --code`. A pasted `cvctok_` API token also works.

Auth tokens are held by the host, never by the documents, so they can't leak
into state that Ariadne replicates or logs. In the browser the session lasts
only as long as the page.

In the stock `ari` host cypkg doesn't install anything: where the web pages
show install commands, it shows the same `cvcpkg install` lines to copy. In a
scripting host (`arix`, `ariglx`) it adds the Prefixes window, which installs
and removes packages with cvcpkg's own installer ([below](#prefixes)).

## Layout

```
share/cypkg/      the documents:
                    main.ari     the app: its arguments, and the component, loaded once
                    cypkg.ari    the component: its windows, menu, signing in and out;
                                 another document loads it the same way (below)
                    search.ari   the search module: its state, view and requests
                    package.ari  the package module: its state, view and requests
                    builders.ari the fleet, a card each; builder.ari one builder
                    builds.ari, activity.ari, account.ari  the other windows' modules
                    lib.ari      the logic, as functions the modules import
                    net.ari      requests and the live feed, which the modules import
                    views.ari    the views, as units the modules include
                    mainx.ari    main.ari for a scripting host: the same app plus prefixes.ari
                    prefixes.ari the Prefixes window, its own component (it needs Python)
                    python/pkg_bridge.py  the Prefixes window's calls into cvcpkg's library
bin/              the launchers: cypkg (sh) and cypkg.cmd
tools/            site.sh (the browser site), stage-python.sh (cvcpkg's client, for a checkout)
web/              the browser site's landing page (index.html, index.css) and page configs
tests/            snapshot tests and a fixture registry
recipes/cypkg/    the cvcpkg recipe: documents and launchers, one noarch build
docs/ROADMAP.md   milestones and the libcvc and cvcpkg features each one needs
```

## Packaging

`recipes/cypkg/` is the cvcpkg recipe. cypkg is documents and launchers, so
one `platform: any` build serves every platform. It depends on `ari` at run
time, and the launcher runs the `ari` beside it in the prefix. From the repo
root:

```bash
cvcpkg build cypkg --local --platform any --prefix ./prefix
```

It needs `ari` 3.7.6 or later. `.github/workflows/publish.yml`, started by hand on
main, packs it and publishes it to cvcpkg.org under the cy-pca organisation.

## One component

Everything cypkg does is in one component, `share/cypkg/cypkg.ari`: its windows, its menu, and
signing in and out. `main.ari` only declares the command line and loads it, and any other
document can load it the same way, as nicotina's site client is loaded:

```yaml
windows:
  - load: cypkg.ari
    as: cypkg
    name: cvcpkg.org            # its menu's name in the host's bar
    link:
      args: { to: args, mode: ro }   # server, q, package, ...; any may be left out
```

It needs no link: with none it runs against https://cvcpkg.org with the defaults, so it runs the
same loaded, on its own, and later as an application of libcvc's shell
(`docs/roadmap/ARIADNE_SHELL.md`, whose mounts get no links).

## Menus and windows

The menu bar has **cypkg** (Quit) and the component's menu, named by the registry's host
(`cvcpkg.org`), with **Search**, **Builders**, **Builds**, **Activity** and **Account**. Its
items are ticked while their window is open, and toggle it; Restart and Quit restart or close
the component (Windows > Applications brings it back). F10 opens the menu bar from the keyboard.

| Window | Shows | Refreshes |
|---|---|---|
| Search | The search and package pages | On request; Next and Prev come from pages already fetched |
| Builders | The fleet, a card each, as the web app's: name, status, platform, version; jobs and CPU, memory and disk meters; last heartbeat, org, labels. **Details** (or a click on the card, outside a terminal) opens the Builder window | Live: each builder as it changes; "12 s ago" ages between messages |
| Builder | One builder: id, version, jobs, heartbeat, org, namespaces, affinity, who registered it; its host (cores, load, memory, disk, OS, Python, uptimes); labels, cross-platform targets and flags; its active and recent jobs | Live: redrawn when the builder changes; its jobs reload when one of them changes |
| Builds | Build jobs, newest first, by status, a page at a time | Live: jobs on the page change in place; a new one reloads the first page |
| Activity | What was published, yanked, unyanked, deleted and nuked, as the web app's page: when, the package, the platform and link, the org, who and why, a publish's size. Filter by kind and name, Pause, page back | Live: a new event goes in at the top; paused, filtered or on an older page, they're counted ("Show 3 new") |
| Account | Who the registry says you are; sign in (a browser pairing, or OpenID Connect) and out | When opened |

- **Modules:** each window is its own module (`share/cypkg/<window>.ari`). A
  closed window's module doesn't start until the window is first opened.
- **Progress:** each window draws a progress bar at its bottom while a request
  is in flight.
- **Live updates:** while open, the Builders, Builds and Activity windows
  follow the registry's `/v1/live/ws` feed, with libcvc's `ws-*` verbs
  (transfix/libcvc#923), natively and in the browser. The status line ends in
  `· live`. Without a feed they poll about every 10 s and try the feed again,
  and say `· polling`. Without the verbs, with `--live off`, or when the
  server closes with 4004 (no live updates), they only poll.
- **Signing in with OpenID Connect:** the Account window's **Sign in with OIDC** uses Ariadne's
  `oidc-sign-in`, with the registry as the issuer and `cypkg` its public client
  (cy-pca/cvcpkg#639). The registry's own sign-in opens in a browser (a loopback redirect
  natively, the page's redirect in a browser); the host keeps the session as the credential
  `cvcpkg.oidc` and refreshes it, and with `--credential-store` (the launcher's default) the next
  start resumes it without a browser. It asks for the `publisher` role. Sign out revokes it.
- **Signing in with an API token:** pass `--token-env VAR`, where `VAR` holds a
  `cvctok_` token (default `CYPKG_TOKEN`, if it's set).
  - The launcher hands it to `ari` with `--credential-env`, bound to the
    registry's origin by a policy file written for the run.
  - `ari` adds the Bearer header to every request, so the documents never see
    the token. Private orgs' packages then show up in search.
  - A token the registry refuses (401) is dropped, and the windows go back to
    anonymous requests.
- **Signing in with a browser:** this is cvcpkg's OIDC route for a terminal,
  device pairing. Account > Sign in with a browser shows a code and a URL; open
  the URL anywhere, sign in, and approve the code.
  - The window polls `/v1/auth/device/token` and the host captures the
    session's access and refresh tokens, so the documents never see them.
  - It works over SSH, since the browser can be on another machine.
  - `bin/cypkg` keeps the sign-in for the next run in ari's credential store
    (`~/.config/cvc/credentials/cypkg`, 0600), as `cvcpkg login` keeps its
    session; `--no-remember` keeps it for this run only.
  - Sign out ends the session on the server too.
  - Pairing needs `sha256-hex` and `random-token` (transfix/libcvc#911).

## Prefixes

With a scripting host, cypkg has a **Prefixes** menu too: what a cvcpkg prefix holds, and
installing and removing packages there.

```bash
cvcpkg install arix cypkg --prefix ~/opt/cypkg
tools/stage-python.sh ~/opt/cypkg/bin/python3.12     # from a checkout; see cvcpkg's client below
CYPKG_ARI=~/opt/cypkg/bin/arix bin/cypkg --open prefixes
```

`arix` is Linux x86_64 only for now (`ariglx` too); Windows, macOS and the rest follow with
transfix/libcvc#1554.

- **Any prefix:** type its path, or pick one used before, and Open. A directory with no lockfile
  is empty, and an install there makes the prefix.
- **Installed:** a row per package (version, size) with a box to tick. **Remove** takes the
  ticked ones, and is refused while other packages need them; **Remove with dependents** takes
  those too. Files another package still ships stay.
- **Add:** name packages (spaces or commas). **Plan** shows what installing them brings, with
  their dependencies: versions, sizes, install or upgrade, and the download. **Install** installs
  the plan a package at a time with progress; **Cancel** stops after the package it is on.
- **Never the prefix cypkg runs from:** replacing the libraries the host has loaded would crash
  it. That prefix shows, read-only.

It is cvcpkg's own installer, not a copy: `share/cypkg/python/pkg_bridge.py` runs in the host's
embedded Python (ARIADNE.md §9.6) and drives cvcpkg's library, the same steps as `cvcpkg install`
and `cvcpkg uninstall` (the catalog, the resolver, each bundle's sha256, the lockfile, the CMake
config and the activation scripts). So a prefix cypkg changes is one the cvcpkg CLI reads, and the
other way round. The long calls run on the host's pool, awaited from the window's tick, so the
window keeps drawing through an install of many minutes.

- **cvcpkg's client:** the window imports `cvcpkg` from the host's Python. Without it, the window
  says so and offers no installer.
  - From a checkout, `tools/stage-python.sh` stages a pinned cvcpkg release (with PyYAML and
    click) in `share/cypkg/python/site`, using the `python3.12` beside `arix`.
  - For an installed cypkg, the plan is a `cvcpkg-cp312` package. That package isn't published
    yet. It would put the client in the host's own site-packages, beside pycvc, as `click-cp312`
    and `pyyaml-cp312` do.
- **Why its own component:** the stock hosts have no Python, and warn on any document with a
  `python:` block. So `main.ari` (stock hosts) leaves `prefixes.ari` out, and `mainx.ari` loads it
  beside `cypkg.ari`. `bin/cypkg` runs `mainx.ari` when `CYPKG_ARI` is `arix` or `ariglx`.
- **Loading it elsewhere:** only the top document's `python:` block runs (a `load:`ed module's
  doesn't yet, ARIADNE.md §11). So a document that loads `prefixes.ari` carries the same block, as
  `mainx.ari` does.

## Running from a checkout

`CYPKG_ARI` names the `ari` to run: the cvcpkg package, 3.7.6 or newer
(`cvcpkg install ari --prefix P`, then `CYPKG_ARI=P/bin/ari`).

```bash
CYPKG_ARI=/path/to/ari bin/cypkg --q zlib
CYPKG_ARI=/path/to/ari bin/cypkg --tvision --package zstd
```

Document flags: `--q`, `--platform`, `--arch`, `--link`, `--offset`,
`--package`, `--pkg-offset`, `--page`, `--open` (windows to open at start,
e.g. `--open builders,activity`) and `--builder ID` (open that builder's window). `--now`
pins the clock for "12 s ago" (the snapshot tests pass it). `--progress off` waits for replies without
a progress bar, for a browser `ari` without libcvc's async fetch
(transfix/libcvc#914). `--live off` polls instead of following the live feed.
The launcher adds `--server`, `--tvision` and
`--token-env`. `bin/cypkg --help` lists them.

## Tests

`tests/run.sh` runs four layers, stopping at the first that fails. `ARI` names
the `ari` to run.

| Layer | Script | What it catches |
|---|---|---|
| 1. static | `tests/check.sh` | `ari check` on every document: YAML errors, functions the host lacks, bad `args:`, unknown units, and any `(str (state-get ...))` (it quotes the text). `prefixes.ari` and `mainx.ari` are checked with `ARIX` (an `arix`), and skipped without it |
| 2a. units | `tests/unit.sh` | Each view in `views.ari`, included in a test document over hand-seeded state, with no network: cut names, wide glyphs, empty results, hidden pagers, one view at a time |
| 2b. functions | `tests/lib.sh` | 16 `ari test` tests of `lib.ari`'s functions (`tests/lib/lib_test.ari`): values in, values out, no network or state |
| 2c. modules | `tests/modules.sh` | 17 `ari test` tests in `tests/modules/`, each document mounting one module alone against the fixture registry through the holes `main.ari` grants (9 search, 8 package). Each test sets the module's state the way its view does, waits for its `seq` counter to count a finished request, and asserts on what its view reads |
| 3a. whole document | `tests/snapshot.sh` | `main.ari` against the fixture registry, from start-up flags: filters, paging edges, nulls, Unicode, and faults (HTTP 500, bad JSON, the wrong shape, connection refused) |
| 3b. whole document | `tests/interactive.sh` | Real keys in a tmux pane, on FTXUI and tvision: typing, Enter, a filter, Open, Next, Back, the menu's Builders, a card's Details, Ctrl-C |
| 3c. browser | `tests/browser.mjs` | The wasm page in headless Chrome, served with the fixture API from one origin under a strict CSP. Real keys over DevTools, through the same steps as 3b; it reads the terminal's text. Runs when `ARI_WEB` and `CHROME` are set |
| 3d. integration | `tests/integration.sh` | cypkg against a real registry instead of the fixture: cy-pca/cvcpkg's own `cvcpkg-server`, installed into a venv (pinned to a commit), run on SQLite in a temp dir, with no database server. It packs the recipes in `tests/integration/recipes/` with `cvcpkg pack`, publishes them with `cvcpkg publish` and the publish API (14 builds of 3 packages; one has 12 builds across platforms, arches and link modes, one has no description, license, homepage or tags), then runs the contract check against it, 14 `ari test` module tests (`tests/integration/modules/`) and 9 snapshots (`tests/integration/expected/`). It asserts what the real server does: an unknown package is 200 with no builds, and `package_count` counts every match only with `facets=true`. With `ARIX`, 10 `arix test` tests of the Prefixes window (`tests/integration/prefixes/`) then plan, install and remove the published packages in a temporary prefix with cvcpkg's own installer. Skipped when cvcpkg can't be installed |
| 4. contract | `tests/contract.py` | The live registry still sends every field cypkg reads, with the types it expects, and the fixture matches it. Needs the network, so it runs only with `tests/run.sh --live` |

The fixture registry (`tests/registry/fixture_registry.py`, Python stdlib
only) serves 193 real builds of 7 packages, captured from cvcpkg.org with
`tests/registry/capture.py`. It also serves three synthetic edge-case packages
(`edge.json`) and faults chosen by name (`fault-500`, `fault-badjson`,
`fault-shape`, `fault-empty`). It checks the integer parameters (`builder_id`,
`limit`, `offset`) as cvcpkg's FastAPI routes do, with their bounds, and
answers a bad one 422 with the same detail.

```bash
ARI=/path/to/ari tests/run.sh
ARI=/path/to/ari tests/snapshot.sh --update   # rewrite the expected frames
ARI=/path/to/ari tests/unit.sh --show search_rows
ARI=/path/to/ari CVCPKG_VENV=~/.cache/cypkg-cvcpkg tests/integration.sh   # keep the venv
```

The integration layer takes about 20 seconds once cvcpkg is installed (the
install takes about a minute). It keeps the server's state on `/dev/shm` when
there is one, because SQLite syncs every commit. Its frames mask the server's
port and the publish dates. `CVCPKG_REF` installs another cvcpkg commit.

Snapshots are frame-for-frame text and fail on any warning. Layer 3b is the
only one that checks input and the tvision backend, because `ari snapshot`
can't send keys and always lays out with FTXUI.

How the pieces fit:

- `main.ari` only composes. It mounts `search.ari` and `package.ari` with
  `load:` and grants each three holes: `args` (read-only), `view` (which
  module shows) and `nav` (the package Open hands from search to package).
- Each module owns its state, which lives at `includes.<as>` in the parent.
  It imports its view from `views.ari` and its logic from `lib.ari`, and runs
  its own requests in its `on_tick` (transfix/libcvc#904). Its view binds
  reach a parsed reply through holes that grant a whole subtree (#905).
- A hidden mount doesn't run until it is first shown. So Open sets `view` to
  "package" as well as `nav.open`, and that starts the package module.
- The logic is pure `functions:` in `lib.ari` (#900), so layer 2b tests each
  function directly. Binds can't call functions, so the views keep a few
  formatting expressions inline.
- `ari test` takes no document arguments. So `tests/modules.sh` writes a copy
  of each module test beside it, with the fixture's URL in place of
  `@SERVER@`, and runs `ari test` on the copies.

### CI

`.github/workflows/test.yml` runs `tests/run.sh` on every push and PR:

- The test job installs the `ari` package from cvcpkg.org
  (`cvcpkg install ari`), as a person would, and checks it has what cypkg
  uses (json-parse, `ari test`, functions:, the ws-* verbs, sha256-hex): 3.7.6
  is the first release with them all.
- It installs the `arix` package too (`ARIX`), for the Prefixes window's check and integration
  tests.
- The browser job installs the single-threaded `arigl-web` package the same
  way, assembles the site from its pages and runs `tests/browser.mjs` in the
  runner's Chrome: the landing page's links, arigl's start and first search,
  tvision's first search, then the whole walk on FTXUI.
- `tests/run.sh` runs the integration layer too, installing cvcpkg-server from
  cy-pca/cvcpkg. In CI a failed install fails the job instead of skipping it.
- A daily job runs the contract check against cvcpkg.org; `workflow_dispatch`
  runs it too, with the test and browser jobs.

## License

MIT. See [LICENSE](LICENSE). The Ariadne hosts and libcvc are LGPL-2.1, and
are installed separately through cvcpkg. The browser site carries the
`arigl-web` package's builds of them unchanged, with its license and notices.
