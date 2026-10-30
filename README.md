# cypkg

**cypkg** is a terminal client for [cvcpkg](https://cvcpkg.org) registries,
written as
[Ariadne](https://github.com/transfix/libcvc/blob/master/docs/ARIADNE.md)
documents. It is an alternative to the registry's web pages: you can search
packages, read recipes, watch builders and build logs live, and manage tokens,
orgs and the registry. The same documents run natively in a terminal and in
the browser on xterm.js.

> **Status: M0 in progress.** Search and package pages work in both terminal
> backends, but only in an `ari` built with two unmerged libcvc PRs,
> transfix/libcvc#888 (network flags) and #883 (JSON). The browser path is
> still to do. See [docs/ROADMAP.md](docs/ROADMAP.md).

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
backend built for wasm. A registry serves both at
`https://<registry>/apps/cypkg/`. Because that is the registry's own origin,
it needs no CORS.

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
share/cypkg/      the .ari documents (main.ari)
bin/              the launchers: cypkg (sh) and cypkg.cmd
tests/            snapshot tests and a fixture registry
recipe/           the cvcpkg recipe (M5)
docs/ROADMAP.md   milestones and the libcvc and cvcpkg features each one needs
```

## Running from a checkout

`CYPKG_ARI` names the `ari` to run. Until #888 and #883 merge, that is an `ari`
built from libcvc master with both PRs merged in.

```bash
CYPKG_ARI=/path/to/ari bin/cypkg --q zlib
CYPKG_ARI=/path/to/ari bin/cypkg --tvision --package zstd
```

Document flags: `--q`, `--platform`, `--arch`, `--link`, `--offset`,
`--package`, `--pkg-offset` and `--page`. `bin/cypkg --help` lists them.

## Tests

`tests/snapshot.sh` starts a fixture registry
(`tests/registry/fixture_registry.py`, Python stdlib only). The fixture serves
193 real builds of 7 packages, captured from cvcpkg.org with
`tests/registry/capture.py`. The script renders each case with
`ari snapshot` and compares the frame with `tests/expected/`. Any warning from
the document fails the run.

```bash
ARI=/path/to/ari tests/snapshot.sh            # check
ARI=/path/to/ari tests/snapshot.sh --update   # rewrite the expected frames
ARI=/path/to/ari tests/snapshot.sh --show package_zlib
```

## License

MIT. See [LICENSE](LICENSE). The Ariadne hosts and libcvc are LGPL-2.1, and
are installed separately through cvcpkg.
