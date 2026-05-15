# Melon

`Melon` is a sandboxed Python prototype of the package-manager concept shown in the diagram.

## Current scope

- `melon-grow` fetches, verifies, and installs a prebuilt package from a configured repo.
- `melon-pack` packages already-built files into a `.tar.gz` from a simple `.pkg` recipe plus a `files/` directory.
- `melon repo set <url>` stores a remote repository base URL.
- `melon hydrate` pulls `index.json` from a configured remote repo or scans local repo archives.
- `melon sniff` searches the repo index.
- `melon plant` resolves dependencies, downloads package archives, verifies SHA256 checksums, and installs payload files into `.melon/root`.
- Install and remove operations are transactional: if extraction or a lifecycle hook fails, Melon restores files and package metadata.
- `melon squeeze` removes installed package files.
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

Each package entry in `index.json` should include a `sha256` checksum and may include `package_url`. Relative `package_url` values are resolved from the repository base URL.

## Builder workflow (publish prebuilt packages)

This is the intended model: the builder machine creates the `.tar.gz`, publishes it to the repo, and clients only download and install the already-built package.

1. Build package archives with `melon-grow` into your repo folder's `packages/`.
2. Generate/refresh `index.json` with `melon repo index --dir <repo-folder>`.
3. Publish the repo folder so it serves `index.json` and `packages/*.tar.gz` (any static file host works).

## Builder workflow (with buildspec)

Use `melon-build` when you want a PKGBUILD-like file that drives the build/install staging steps.

1. Write a buildspec like `examples/hello/hello.build.ini`.
2. Run `melon-build <spec> --out <repo>/packages` to create `packages/<name>-<version>.tar.gz`.
3. Run `melon repo index --dir <repo>` to regenerate `index.json`.
4. Publish the repo folder as static files.

Buildspec phases live under `[build]`:

- `configure =` (multi-line commands)
- `build =` (multi-line commands)
- `check =` (multi-line commands)
- `install =` (multi-line commands; must install into `$DESTDIR`)

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
