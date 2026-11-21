# Making a release

Players only get what you publish. Your own changes and the Phoenix updates you pull reach them when you publish a new
version; their launcher then offers it (SYSTEM > Updates, a line on the Play page, and a question when it starts). Test builds (pre-releases)
only reach players who switched on "Get test builds".

## The easy way: the launcher
Commit and push your work (kit and server), rebuild the server if C++ changed (`Rebuild server.bat`), close the game,
then SYSTEM > Team > **Publish update...**. It shows the next version, release notes from your commit messages and anything
not ready yet, and after you confirm it:
1. builds `XI Forever Offline.exe` (`build_release.ps1`, in its own Python environment),
2. makes `dist\xi-forever-offline-server-<v>-win64.zip` (`package_server.py`) and `dist\kit\xi-forever-offline-<v>-win64.zip` (`package_kit.py`), each with a SHA256SUMS.txt,
3. tags both repos `<v>` and pushes the tags and the server's `release` branch,
4. creates both GitHub releases as drafts, uploads the files, then publishes them (using the GitHub sign-in Git keeps on this PC).

## By hand
```powershell
cd C:\FFXISOLO
.\build_release.ps1
python package_server.py v0.1.1
python package_kit.py v0.1.1
cd C:\ffxi-local\server
git tag -a v0.1.1 -m "XI: Forever Offline v0.1.1"
git push xiforever HEAD:refs/heads/release
git push xiforever v0.1.1
cd C:\FFXISOLO
git tag -a v0.1.1 -m "XI: Forever Offline v0.1.1"
git push origin v0.1.1
```
Then on GitHub: **Save draft first, upload the files, then Publish** (uploading on an unsaved form makes a separate draft).
Server release: the server zip + `dist\SHA256SUMS.txt`. Launcher release: `dist\kit\` zip + `dist\kit\SHA256SUMS.txt`.

## What players download
`xi-forever-offline-<v>-win64.zip`: unzip anywhere, run `XI Forever Offline.exe`. The first-run setup downloads the
server and everything else.

While the repos are private, players cannot download anything.

## Linux / Steam Deck files (automatic)
Nothing to do on the dev PC: pushing the version tag starts a GitHub workflow in each repo, and each one adds its Linux
files to the same release once the release is published (about 30-60 minutes after the Publish button, see the Actions
tab of each repo):
- kit repo, `.github/workflows/linux-release.yml`: builds the Linux launcher (`build_release.sh`), packs
  `xi-forever-offline-<v>-linux-x64.tar.gz` + `SHA256SUMS-linux.txt` (`package_kit.py --platform linux`), and for a full
  release also `XI-Forever-Offline-Linux.tar.gz` (the fixed one-click link
  `https://github.com/Hurami89/xi-forever-offline/releases/latest/download/XI-Forever-Offline-Linux.tar.gz`).
  It also checks MariaDB's Linux package on Arch Linux (SteamOS) with the launcher's setup code.
- server repo, `.github/workflows/xiforever-linux.yml`: builds the five server programs for Linux, packs
  `xi-forever-offline-server-<v>-linux-x64.tar.gz` + `SHA256SUMS-linux.txt` (`package_server.py --platform linux
  --bundle-libs`), runs it (database, five servers, map server ready) and checks for missing libraries on Arch Linux.
If a workflow fails, its Linux files are missing from that release: Linux players' update check then says the Linux
files aren't there yet, and Windows players are not affected. Run it again by hand: Actions > the workflow > Run workflow
(type the tag).
