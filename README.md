# cypkg

**cypkg** is a terminal client for [cvcpkg](https://cvcpkg.org) registries,
written as
[Ariadne](https://github.com/transfix/libcvc/blob/master/docs/ARIADNE.md)
documents. It is an alternative to the registry's web pages: you can search
packages, read recipes, watch builders and build logs live, and manage tokens,
orgs and the registry. The same documents run natively in a terminal and in
the browser on xterm.js.

> **Status: M0 in progress.** Search and package pages work in both terminal
> backends and in the browser. They need an `ari` built with open libcvc PRs
> (`.github/workflows/test.yml` lists them), and no registry serves
> `/apps/cypkg/` yet. See [docs/ROADMAP.md](docs/ROADMAP.md).

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
Running in `arigl` (ImGui) is a possible later extra, not a goal; see M6 in
the roadmap.

**In the browser**, the same documents run in ari's xterm.js page, the FTXUI
backend built for wasm (transfix/libcvc#887). A registry serves both at
`https://<registry>/apps/cypkg/`. Because that is the registry's own origin,
it needs no CORS.

- `tools/site.sh ARI_WEB OUT` assembles that directory from ari's page files
  and `share/cypkg/`.
- `web/ariadne.config.json` pins the document to `main.ari` and turns the
  network on for the page's own origin only (`--net`).
- The config also passes `--server {origin}`, so cypkg browses the registry
  that serves it.
- Host flags come only from that file, never from the URL.
- The page runs under a strict Content-Security-Policy: no inline code or
  style, no eval, nothing from another origin.

To try it, serve a site with the fixture registry and open
`http://127.0.0.1:8766/apps/cypkg/`:

```bash
tools/site.sh /path/to/ari-web site
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

cypkg doesn't install anything. Where the web pages show install commands, it
shows the same `cvcpkg install` lines to copy.

## Layout

```
share/cypkg/      the documents:
                    main.ari     composes the two modules and wires their holes
                    search.ari   the search module: its state, view and requests
                    package.ari  the package module: its state, view and requests
                    lib.ari      the logic, as functions the modules import
                    views.ari    the two views, as units the modules include
bin/              the launchers: cypkg (sh) and cypkg.cmd
tests/            snapshot tests and a fixture registry
recipe/           the cvcpkg recipe (M5)
docs/ROADMAP.md   milestones and the libcvc and cvcpkg features each one needs
```

## Running from a checkout

`CYPKG_ARI` names the `ari` to run. Until #883 merges, that is an `ari` built
from libcvc master with #883 merged in.

```bash
CYPKG_ARI=/path/to/ari bin/cypkg --q zlib
CYPKG_ARI=/path/to/ari bin/cypkg --tvision --package zstd
```

Document flags: `--q`, `--platform`, `--arch`, `--link`, `--offset`,
`--package`, `--pkg-offset` and `--page`. `bin/cypkg --help` lists them.

## Tests

`tests/run.sh` runs four layers, stopping at the first that fails. `ARI` names
the `ari` to run.

| Layer | Script | What it catches |
|---|---|---|
| 1. static | `tests/check.sh` | `ari check` on every document: YAML errors, functions the host lacks, bad `args:`, unknown units |
| 2a. units | `tests/unit.sh` | Each view in `views.ari`, included in a test document over hand-seeded state, with no network: cut names, wide glyphs, empty results, hidden pagers, one view at a time |
| 2b. functions | `tests/lib.sh` | 16 `ari test` tests of `lib.ari`'s functions (`tests/lib/lib_test.ari`): values in, values out, no network or state |
| 2c. modules | `tests/modules.sh` | 17 `ari test` tests in `tests/modules/`, each document mounting one module alone against the fixture registry through the holes `main.ari` grants (9 search, 8 package). Each test sets the module's state the way its view does, waits for its `seq` counter to count a finished request, and asserts on what its view reads |
| 3a. whole document | `tests/snapshot.sh` | `main.ari` against the fixture registry, from start-up flags: filters, paging edges, nulls, Unicode, and faults (HTTP 500, bad JSON, the wrong shape, connection refused) |
| 3b. whole document | `tests/interactive.sh` | Real keys in a tmux pane, on FTXUI and tvision: typing, Enter, a filter, Open, Next, Back, Ctrl-C |
| 3c. browser | `tests/browser.mjs` | The wasm page in headless Chrome, served with the fixture API from one origin under a strict CSP. Real keys over DevTools, through the same steps as 3b; it reads the terminal's text. Runs when `ARI_WEB` and `CHROME` are set |
| 4. contract | `tests/contract.py` | The live registry still sends every field cypkg reads, with the types it expects, and the fixture matches it. Needs the network, so it runs only with `tests/run.sh --live` |

The fixture registry (`tests/registry/fixture_registry.py`, Python stdlib
only) serves 193 real builds of 7 packages, captured from cvcpkg.org with
`tests/registry/capture.py`. It also serves three synthetic edge-case packages
(`edge.json`) and faults chosen by name (`fault-500`, `fault-badjson`,
`fault-shape`, `fault-empty`).

```bash
ARI=/path/to/ari tests/run.sh
ARI=/path/to/ari tests/snapshot.sh --update   # rewrite the expected frames
ARI=/path/to/ari tests/unit.sh --show search_rows
```

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

- No `ari` package yet has the libcvc PRs cypkg needs, so the workflow builds
  `ari` from libcvc master with them merged on top (`LIBCVC_PRS`: currently
  #883, #896, #900, #902, #904 and #905), skipping any that have merged.
- libcvc's dependencies come from cvcpkg, as in libcvc's own CI.
- The built `ari` is cached by its libcvc source tree, so an unchanged libcvc
  isn't rebuilt.
- A second job builds ari's single-threaded wasm page the same way (with
  #887 too, from cvcpkg's emsdk and wasm deps), assembles the site and runs
  `tests/browser.mjs` in the runner's Chrome.
- `tools/libcvc.sh` does the fetching and merging for both jobs. When two of
  the PRs conflict in a way `tools/libcvc-resolve.py` knows (today, #887 and
  #896 in `src/ari/main.cpp`), it resolves it; any other conflict fails.
- A daily job runs the contract check against cvcpkg.org.
- `workflow_dispatch` takes another libcvc ref or list of PRs.

## License

MIT. See [LICENSE](LICENSE). The Ariadne hosts and libcvc are LGPL-2.1, and
are installed separately through cvcpkg.
