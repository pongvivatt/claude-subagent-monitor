# AUR packaging — `claude-agent-monitor-git`

Files for the AUR VCS package. The AUR hosts the `PKGBUILD` recipe (not the
code); it builds from the latest commit of the GitHub repo.

## Publish / update

1. Create the package page, then clone its AUR git repo:
   ```bash
   git clone ssh://aur@aur.archlinux.org/claude-agent-monitor-git.git
   ```
2. Copy `PKGBUILD` and `claude-agent-monitor-git.install` into it.
3. Build and test locally (also computes the real `pkgver`):
   ```bash
   makepkg -si
   ```
4. Regenerate `.SRCINFO` from the real checkout (do this whenever the PKGBUILD changes):
   ```bash
   makepkg --printsrcinfo > .SRCINFO
   ```
5. Commit `PKGBUILD`, `.SRCINFO`, `.install` and push.

## Notes

- `pkgver()` derives the version from git as `r<commit-count>.<short-sha>`; the
  `r0.0000000` placeholder in `PKGBUILD`/`.SRCINFO` is overwritten on build.
- GTK/PyGObject/librsvg are runtime `depends` (system libraries); the package
  itself is pure Python (`arch=any`).
- `provides`/`conflicts` reserve the base name `claude-agent-monitor` so a future
  tagged-stable package won't co-install with this `-git` one.
