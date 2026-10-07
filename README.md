# Issuarr

[![Build & Publish Docker Image](https://github.com/TRusselo/mylar3/actions/workflows/docker_ghcr.yml/badge.svg?branch=trusselo)](https://github.com/TRusselo/mylar3/actions/workflows/docker_ghcr.yml)

Issuarr is an automated comic book (cbr/cbz) manager and downloader. Keep a watchlist of series and Issuarr finds new and missing issues, downloads them (NZB, torrent or direct download), files and renames them, tags them with ComicInfo metadata and keeps your library in step with ComicVine.

## A spiritual successor to Mylar

Issuarr is built on Mylar's bones. Mylar was created by **evilhero**, rewritten for Python 3 as [mylar3/mylar3](https://github.com/mylar3/mylar3), and carried on by the community as [MylarComics/mylar3](https://github.com/MylarComics/mylar3). Both have now wound down: mylar3/mylar3 is no longer developed, and MylarComics/mylar3 is maintenance-only (no new features) while its team works on a separate project.

Issuarr picks up from there. It keeps everything Mylar3 does and adds the features below. It is an independent project, not affiliated with or endorsed by the Mylar3 or MylarComics teams, so please bring Issuarr questions here rather than to them.

> **Rename in progress.** The repository (`TRusselo/mylar3`), the Docker image (`ghcr.io/trusselo/mylar3`) and the app's own screens still say Mylar for now. Existing Mylar3 config folders and databases work as they are.

## Installation

### Docker (recommended)

```sh
docker run -d --name issuarr \
  -e PUID=1000 -e PGID=1000 -e TZ=Etc/UTC \
  -p 8090:8090 \
  -v /path/to/config:/config \
  -v /path/to/comics:/comics \
  -v /path/to/downloads:/downloads \
  ghcr.io/trusselo/mylar3:latest
```

The image is a drop-in replacement for [linuxserver/mylar3](https://hub.docker.com/r/linuxserver/mylar3): same s6 base, `PUID`/`PGID`/`UMASK`/`TZ`, `/config` with data in `/config/mylar`, and port 8090. To switch an existing Mylar3 container, change its image to `ghcr.io/trusselo/mylar3:latest` and keep your volumes.

### From source

```sh
git clone -b trusselo https://github.com/TRusselo/mylar3.git issuarr
cd issuarr
pip install -r requirements.txt
python3 Mylar.py
```

Then open http://localhost:8090. `unrar` must be installed to read cbr files.

## What Issuarr adds

### Direct downloads (GetComics)
- Download sources (GetComics' own server, Mega, Mediafire, Pixeldrain and others) are learned from GetComics posts and can be reordered or switched off. Pixeldrain API keys are supported.
- Cloudflare on GetComics is cleared through FlareSolverr, set up under Search providers > DDL.
- Mirrors can be handed to JDownloader 2. Jobs are tracked per package, with a fallback to the built-in downloader.
- Option to try GetComics' own server last for files over a size you choose (default 400 MB).
- Grabs a wanted issue from its own line in a multi-issue post instead of the whole post, and accepts packs titled "&lt;Series&gt; Complete".
- The download folder is set on the settings page. A warning appears if it is inside the folder monitor.
- Queue Management updates live with speed, progress and time left. The queue reloads after a restart without duplicates. Abort and Remove really stop a download and undo a pack's Snatched marks.
- An issue is marked Failed when every link fails. A new search runs when failed-download handling and auto-retry are on.

### Post-processing
- Unpacks zip and rar downloads from DDL, torrents, JDownloader and the folder monitor. Archives without enough comic pages are skipped, and there is an option to delete archives after extraction.
- Packs are matched against the whole watchlist. Issues nothing wants are moved to a review folder or deleted (your choice), keeping the monitored folder clear.
- A pack issue can upgrade a file you already own, but only under the normal duplicate rules.
- Dated weekly pack folders are matched to their series by release date.
- Optional: add the series for comics nothing on the watchlist wants, using ComicVine and the pack's release week.
- One post-processing job runs at a time, and searches wait while post-processing or auto-add is running.
- Reading-order numbers ("03 - …") and story-arc labels in filenames no longer confuse matching.

### Metadata tagging
- New tag mode, **fill** by default: writes every field ComicVine has but keeps any value already in ComicInfo.xml. **Skip** and **overwrite** modes are also available.

### WebP conversion (optional)
- Convert on import (off by default) for issues from a chosen year onward (default 2015). CBR files are repacked as CBZ first.
- Bulk converter under Manage > WebP conversion, with filters, a preview, confirmation prompts and an optional holding folder for the originals.
- Only converts what benefits. Pages that are unreadable, CMYK, low-quality JPEG, or would get bigger are left alone, and a file must shrink by at least 10%. Files are swapped atomically and journaled, and the stored file size is updated.
- Uses every CPU core and converts several files at once.

### Ledger (new page)
- Missing-issue ledger and collected-edition coverage: see which trades cover the issues you're missing, including trade volumes you don't own.
- Trade Management tab with actions for a trade, its missing singles or its duplicate singles. Duplicate singles are moved out with an undo list.
- Wanted counts, a status filter and keyboard selection.

### Library import and management
- Library Scan / Import status panel (Manage > Activity / Jobs and Settings > Information) with a live log tail, stop and resume controls and a header indicator. Mass imports resume after a restart, and concurrent scans are blocked.
- Activity / Jobs shows folder monitor and post-processing activity and lets you edit job intervals.
- ComicVine rate limits (HTTP 420) are waited out instead of being treated as "no results".
- Manage Comics loads one page at a time, so libraries with thousands of series don't crash the browser.
- Library sync never drops files the ComicVine reverse lookup couldn't resolve.

### Search
- Numbered annual series (for example "X-Men Annual 1992") are searched by issue number.

### API
- `setComicLocation` points a series at another existing folder and rescans it (see [API_REFERENCE](API_REFERENCE)).

### Interface
- Carbon theme with a solid header, page actions beside the title, underline tabs and sticky action bars.
- Annual groups are expanded by default.

### Fixes
- Discord test notification, `cmd=refreshComic`, the weekly pull-list week number, and annual counts when annual integration is off.

## Everything from Mylar3
- Runs on Windows, Linux, macOS, Raspberry Pi and more
- SABnzbd, NZBGet, various torrent clients and blackhole
- Multiple newznab indexers, a raw indexer and direct download
- Weekly pull-lists, up to 4 weeks ahead or several months back
- Monitoring and post-processing of TPBs and GNs
- Scans an existing library and downloads missing issues
- Failed download handling
- Configurable file and folder renaming
- Metatagging with a modified version of ComicTagger, during or after post-processing
- series.json generation for third-party apps
- Notifications on snatches and downloads
- Story arc tracking

## Support
- [Issues](https://github.com/TRusselo/mylar3/issues): bug reports and feature requests.
- Most of the [Mylar documentation](https://mylar.nerdfirehurricane.com/) still applies to the features Issuarr shares with Mylar3.

## Credits
Issuarr exists because of the people who built Mylar:
- **evilhero**, who created Mylar and wrote most of its code.
- Everyone who contributed to [mylar3/mylar3](https://github.com/mylar3/mylar3/graphs/contributors) and [MylarComics/mylar3](https://github.com/MylarComics/mylar3/graphs/contributors), by code, by helping others or by donating.
- [ComicTagger](https://github.com/comictagger/comictagger) (bundled in modified form), [ComicVine](https://comicvine.gamespot.com/) for series and issue data, and [linuxserver.io](https://www.linuxserver.io/) for the container base.

Thank you.

## License
GNU General Public License v3, the same as Mylar. See [LICENSE](LICENSE).
