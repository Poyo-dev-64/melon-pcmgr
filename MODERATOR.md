# Melon Moderator Map (GitHub Pages Repo)

This is the day-to-day guide for maintaining a Melon repository hosted on GitHub Pages.

## Mental Model

- A Melon repo is static files: `index.json` + `packages/*.tar.gz`.
- Clients do **not** compile. They only:
  - download `index.json`
  - download a `packages/<name>-<version>.tar.gz`
  - verify SHA256 against `index.json`
  - install payload files into the target root

If you break `index.json` or `sha256`, installs fail immediately (by design).

## Repo Layout (GitHub Pages)

Publish from the repository root on `main`:

- `index.json`
- `index.html` (dynamic; loads `index.json`)
- `packages/*.tar.gz`

## One-Time Setup (GitHub)

1. GitHub repo Settings → Pages.
2. Source: “Deploy from a branch”.
3. Branch: `main`, Folder: `/docs`.
4. Your base URL becomes: `https://<user>.github.io/<repo>/`

## Routine: Add or Update a Package

All commands below assume you are in the repo checkout.

### A) Build From Buildspec (recommended)

1. Build the tarball into the Pages folder:
   - `melon build path/to/pkg.build.ini --repo .`

Buildspec phases (`.build.ini`) are:

- `[build] configure`
- `[build] build`
- `[build] check`
- `[build] install` (must install into `$DESTDIR`)

### B) Pack Already-Built Files

1. Place artifacts under `files/` (already compiled).
2. Package them:
   - `melon pack path/to/pkg.pkg --out packages`

### Regenerate Repo Index (required)

After any tarball changes:

- `melon repo index --dir .`

This recomputes SHA256 for every tarball and writes `docs/index.json`.

### Ensure the Web Page Exists (usually one-time)

If you need to (re)generate the dynamic HTML:

- `melon repo render --dir .`

After this, the page updates automatically whenever `index.json` changes.

### Publish (git push)

1. `git add docs`
   - or `git add index.json index.html packages`
2. `git commit -m "repo: add/update <pkg> <ver>"`
3. `git push`

## Routine: Verify Before Pushing

- Open `docs/index.json` and verify:
  - each entry has `name`, `version`, `sha256`, `package_url`
- Sanity-check that the tarball exists:
  - `docs/packages/<name>-<version>.tar.gz`

Optional but recommended:

- Test install in a disposable root:
  - `melon --layout system --root /tmp/melonroot repo set https://<user>.github.io/<repo>`
  - `melon --layout system --root /tmp/melonroot hydrate`
  - `melon --layout system --root /tmp/melonroot plant <pkg>`

## Multiple Repositories (optional)

Clients can add more than one repo and set priorities:

- `melon repo add core https://example/core --priority 10`
- `melon repo add extra https://example/extra --priority 0`

When hydrating, higher priority repos override lower priority ones for the same package name.

## Emergency Rollback

GitHub Pages is deployed from git history, so rollback is:

- `git revert <bad-commit>` (preferred)
- or `git reset --hard <good-commit>; git push --force` (use only if you understand the consequences)

If you roll back a tarball, you must also roll back the matching `index.json`.

## Rules That Prevent Breaking Clients

- Never modify an existing tarball without regenerating `docs/index.json`.
- Never publish a tarball whose SHA256 does not match the index.
- Avoid “moving” packages: clients resolve `package_url` from `index.json`.
- Prefer version bumps over replacing a version in-place.

## What Hooks Mean

Packages may include `pre-install`, `post-install`, `pre-remove`, `post-remove` scripts.

- Melon runs hooks during install/remove.
- Melon rolls back package-managed files on failure.
- Hook side effects are not automatically rolled back.

Treat hooks as “privileged maintainer code”; use sparingly and review carefully.
