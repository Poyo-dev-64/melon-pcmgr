# Melon

`Melon` is a small package manager for distributing and installing prebuilt packages.

## Current scope

- `melon plant` downloads, verifies SHA256, and installs a prebuilt package from a configured repo.
- `melon build` is a moderator wrapper: builds a package from a buildspec and regenerates `index.json`.
- `melon pack` packages already-built files into a `.tar.gz` from a simple `.pkg` recipe plus a `files/` directory.
- `melon repo set <url>` stores a remote repository base URL.
- `melon repo add <name> <url> --priority N` supports multiple repositories (higher priority wins).
- `melon hydrate` pulls `index.json` from a configured remote repo or scans local repo archives.
- `melon sniff` searches the repo index.
- `melon plant` resolves dependencies, downloads package archives, verifies SHA256 checksums, and installs payload files into the target root.
- Install and remove operations are transactional: if extraction or a lifecycle hook fails, Melon restores files and package metadata.
- `melon squeeze` removes installed package files.
- `melon rdepends <pkg>` shows reverse dependencies for an installed package.
- `melon preserve` and `melon thaw` manage held packages.
- `melon ripen` upgrades installed packages from the local repo.
- `melon rind`, `melon nutrition`, `melon wash`, and `melon status` expose local state.

## Local layout

Melon keeps everything inside the workspace:

- `.melon/repo/packages`: local package archives
- `.melon/repo/index.json`: generated repo index
- `.melon/repo/config.json`: remote repo settings
- `.melon/cache/packages`: downloaded package archives
- `.melon/db/installed/`: one JSON file per installed package
- `.melon/db/holds.json`: held packages
- `.melon/root`: sandboxed install root
- `.melon/logs`: command logs

## System layout (Linux distro mode)

When you run Melon with `--layout system --root /` (or `--root /mnt/lfs` during bootstrap), it behaves like a real root package manager:

- Installs into the target rootfs directly: `<root>/usr`, `<root>/etc`, `<root>/bin`, etc.
- Stores state under the target rootfs:
  - `<root>/var/lib/melon` (db + repo index)
  - `<root>/var/cache/melon` (downloaded package tarballs + transactions)
  - `<root>/var/log/melon` (logs)
  - `<root>/etc/melon/repo.json` (repo config)

Example (LFS-style chroot root):

```bash
melon --layout system --root /mnt/lfs repo set https://your-host/melon
melon --layout system --root /mnt/lfs hydrate
melon --layout system --root /mnt/lfs plant bash
```

On Linux, `--layout system` is the default. Use `--layout workspace` to keep everything under a local `.melon/` folder.

## Recipe format

Recipes are simple `key: value` files:

```text
name: hello
version: 1.0.0
desc: Example package
url: https://example.invalid/hello.tar.gz
deps:
config: ./configure --prefix=/usr
make: make -j4
install: make DESTDIR=/usr install
remove:
patch:
sha256:
```

Place package payload files in a sibling `files/` directory and optional lifecycle scripts in `scripts/`.

Supported hook names are `pre-install`, `post-install`, `pre-remove`, and `post-remove`.
Hooks may be shipped as `.py`, `.ps1`, `.cmd`, `.bat`, or `.sh` files.

During hook execution Melon exposes:

- `MELON_PACKAGE_NAME`
- `MELON_PACKAGE_VERSION`
- `MELON_INSTALL_ROOT`
- `MELON_STATE_DIR`

## Remote repositories

Remote repos are expected to expose:

- `index.json`: package metadata keyed by package name
- `packages/<name>-<version>.tar.gz`: package archives

`index.json` formats:

- v2 (current): `{ "format": 2, "packages": { "name": [ {meta}, {meta}, ... ] } }`
- v1 (legacy): `{ "name": {meta}, ... }` (still accepted during `hydrate`)

Each package entry should include a `sha256` checksum and may include `package_url`. Relative `package_url` values are resolved from the repository base URL.

Dependencies are strings like `zlib`, `zlib>=1.3`, or `openssl==3.0.0`.

Version format supports `epoch:version-release` (examples: `1:2.0.1-3`, `0:1.2.3`, `2.1.0-1`).

## GitHub Pages hosting (moderator git-push workflow)

Recommended layout is to publish from the repository root on `main`:

- `index.json`
- `index.html` (dynamic; loads `index.json`)
- `packages/*.tar.gz`

Moderator workflow:

1. Build a package into the Pages folder:
   - `melon build yourpkg.build.ini --repo .`
   - or `melon pack yourpkg.pkg --out packages`
2. Regenerate the index:
   - `melon repo index --dir .`
3. Ensure the HTML listing page exists (usually one-time):
   - `melon repo render --dir .`
4. `git add index.json packages index.html && git commit && git push`

Users can:

- Install via CLI: `melon repo set https://<user>.github.io/<repo> ; melon hydrate ; melon plant <pkg>`
- Or download tarballs directly by visiting the Pages site and clicking links.

## Builder workflow (publish prebuilt packages)

This is the intended model: the builder machine creates the `.tar.gz`, publishes it to the repo, and clients only download and install the already-built package.

1. Build package archives into your repo folder's `packages/` (via `melon build` or `melon pack`).
2. Generate/refresh `index.json` with `melon repo index --dir <repo-folder>`.
3. Publish the repo folder so it serves `index.json` and `packages/*.tar.gz` (any static file host works).

## Builder workflow (with buildspec)

Use `melon-build` when you want a PKGBUILD-like file that drives the build/install staging steps.

1. Write a buildspec like `examples/hello/hello.build.ini`.
2. Run `melon build <spec> --repo <repo>` to create `packages/<name>-<version>.tar.gz` and regenerate `index.json`.
3. Run `melon repo index --dir <repo>` to regenerate `index.json`.
4. Publish the repo folder as static files.

Buildspec phases live under `[build]`:

- `configure =` (multi-line commands)
- `build =` (multi-line commands)
- `check =` (multi-line commands)
- `install =` (multi-line commands; must install into `$DESTDIR`)

You can also use `melon repo index` and `melon repo render` as separate publishing steps.

Notes:

- Buildspec command lines should be POSIX-shell friendly for Linux distro usage (see `examples/hello/hello.build.ini`).

## Release Checklist

- Packages are reproducible on the builder machine (same inputs produce same tarball).
- `index.json` is regenerated after every package build (`melon repo index --dir <repo>`).
- Repo is served over HTTPS in production.
- Every package in `index.json` has a valid `sha256` and `package_url`.
- Clients run `melon hydrate` before installing so they get the latest index.

## Bootstrap prerequisites (LFS-friendly)

Melon is intentionally small and aims to be bootstrappable:

- Python 3 (stdlib only)
- `tar`/`gzip` support (Python `tarfile` handles this)
- `patch` executable if you use `[source] patches` in buildspecs
- A POSIX shell and toolchain for whatever you build (e.g. `sh`, `make`, `gcc`, `binutils`)

## Example flow

```bash
python -m melon.pack examples/hello/hello.pkg --out .melon/repo/packages
python -m melon.cli hydrate
python -m melon.cli sniff hello
python -m melon.cli plant hello
python -m melon.cli status
```

## Remote install flow

```bash
python -m melon.cli repo set file:///path/to/repo
python -m melon.cli hydrate
python -m melon.cli plant hello
```
