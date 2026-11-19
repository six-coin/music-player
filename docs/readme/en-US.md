# Music Player User Manual

A local music library manager plus two players: the manager imports, organizes and configures; the players only play. Windows desktop app, double-click to run.

[简体中文](zh-CN.md)

---

## 1. Installation

You need Windows 10 or 11 and [uv](https://docs.astral.sh/uv/). Everything else is installed into the project's `.venv` by `uv sync`.

```bat
setup.bat
```

Double-click `setup.bat`. It checks for uv, creates the virtual environment and installs dependencies. The window waits for a key press when it finishes.

| Component        | When you need it   | Notes                                                                 |
|------------------|--------------------|-----------------------------------------------------------------------|
| uv               | Always             | The only supported way to manage dependencies                         |
| WebView2 Runtime | Manager and player | Ships with Windows 11; Windows 10 usually has it via Edge             |
| VLC              | Simple Player only | Install the 64-bit build; the app finds it on its own                 |
| FFmpeg           | Optional           | Cleans audio on import and reads durations; playback works without it |

Moving to another machine: copy the program folder and run `setup.bat` there once. Copy `%PROGRAMDATA%\six-coin\music-player` to the same place and your library, playlists and audio come with you.

## 2. Starting

| Entry point   | What opens                            |
|---------------|---------------------------------------|
| `manager.bat` | Music Library Manager (window)        |
| `player.bat`  | Music Player (window, no VLC needed)  |
| `simple.bat`  | Simple Player (console, VLC required) |
| `setup.bat`   | Installs or updates the runtime       |

Each program allows a single instance. Double-clicking again while one is open shows "already running" and exits; no second window appears.

On the **first run**, whichever entry point you double-click opens the manager instead: pick the interface language (the Windows UI language by default, English when there is no matching locale; the whole dialog switches the moment you change it), then read the manual. If you started `player.bat` or `simple.bat`, one extra note explains that the manager is what just opened. Close it and start your original entry point again when you are done.

Closing the window quits. Next time the manager opens on the overview, and the player returns to the last playlist and position, paused.

## 3. The window

The manager has three columns: navigation on the left, a list in the middle, details on the right.

| Area        | Contents                                                                        |
|-------------|---------------------------------------------------------------------------------|
| Navigation  | Overview, Songs, Playlists, Tags, Artists, Pomodoro, with Settings at the bottom |
| List        | Items of the current section, with title, count and the New button above        |
| Detail      | Editor for the selected item; changes save as you type, there is no Save button |
| Preview bar | Rises from the bottom after Preview; pause, seek and change volume there        |

The overview has no list column, so its main area spans two columns: six number cards (songs, total time, size, playlists, artists, tag groups), then "Recently imported / Recently edited" next to "To review", then the quick actions.

## 4. Importing music

Only `.mp3` and `.m4a` are accepted. Anything else is rejected with a reason.

| Action                                   | Result                                           |
|------------------------------------------|--------------------------------------------------|
| Import music with one file selected      | Import starts immediately with a progress dialog |
| Import music with several files selected | The three-step bulk import wizard opens          |

The wizard:

| Step            | What you do                                                                      |
|-----------------|----------------------------------------------------------------------------------|
| 1 Check details | Edit each title and artist; artists are comma separated; remove a file if needed |
| 2 Choose tags   | Tick tags that apply to the whole batch; skippable                               |
| 3 Start import  | Review the summary, decide whether to clean audio, start                         |

Rules:

- "Title - Artist1, Artist2" in a filename is split automatically; unknown artists are created.
- Deduplication is by content: importing the same audio twice skips it, and the failure list says "same file as «Title» (identical MD5)". Cleaning strips tag differences, so two files that look different can still land on the same MD5.
- Audio is stored as `assets\music\{md5}.{ext}`; your original file is left alone.
- Cleaning (on by default) re-muxes with FFmpeg and drops metadata, so different tagged copies of one song are recognized as the same song. Without FFmpeg the import fails with a message; turn cleaning off in Settings.
- One failing file does not stop the batch; successes and failures are listed at the end.

## 5. Songs

The list sorts by title; switch to import date, duration or artist. Search matches titles, aliases, artists and tags at once.

| Action            | How                                                                |
|-------------------|--------------------------------------------------------------------|
| Select a song     | Click it; the detail area shows its information                    |
| Multi-select      | `Ctrl` click, `Shift` click, or the checkbox at the start of a row |
| Add tags in bulk  | Select several, then Add tags                                      |
| Add to a playlist | Select several, then Add to playlist (manual playlists only)       |
| Delete in bulk    | Select several, then Delete song                                   |

Detail cards:

| Card              | Contents                                                                                                                    |
|-------------------|-----------------------------------------------------------------------------------------------------------------------------|
| Basics            | Title, artists (searchable, move up/down to reorder), tags (grouped checkboxes)                                             |
| File              | MD5, path, size, duration, import date                                                                                      |
| Adaptive skipping | Total plays for this song, then its records, skip rate, full plays, auto skips and next probability in the default playlist |

"More" in the top right holds four actions:

| Action              | What it does                                                                                |
|---------------------|---------------------------------------------------------------------------------------------|
| Preview             | Plays in the preview bar at the bottom; does not touch a running player                     |
| Manage aliases      | Aliases are searchable but never shown in lists                                             |
| Replace source file | Swap the audio file while title, artists, tags, playlist membership and statistics stay put |
| Delete song         | Confirms first; the audio file goes to the Recycle Bin                                      |

A tag group can be Required or Single. Violations never block saving: the row gets an amber dot and the integrity check reports it.

## 6. Playlists

Two kinds, fixed at creation time and not switchable afterwards:

| Kind       | How songs get in                                |
|------------|-------------------------------------------------|
| Manual     | Hand-picked; drag to reorder                    |
| Rule-based | Collected by rules, recomputed as you edit them |

There is also a built-in Default playlist containing every song. It cannot be deleted or renamed, and it is what the Simple Player plays.

Each rule row reads "Include/Exclude · Target · Values":

| Target    | Values                                                                              |
|-----------|-------------------------------------------------------------------------------------|
| All songs | none                                                                                |
| Songs     | pick from the library                                                               |
| Playlists | pick another playlist (nesting allowed; a circular reference marks that row in red) |
| Tags      | pick tags; any match counts                                                         |
| Artists   | pick artists; any match counts                                                      |

Rules evaluate top to bottom: includes add, excludes subtract. An empty rule matches nothing.

Each row has a handle on the left; hold it and drag to change the order of the rules.

The playlist list can be reordered by dragging: grab a row, drop it where it belongs, and the order is written to `playlists.json` (the playlist column in the player follows the same order).

The Adaptive skipping card in the playlist detail configures that playlist; View statistics slides a drawer in from the right with records, skip rate, total plays, full plays, auto skips and next probability per song. Each row has a "Clear" button on the right, and it asks first — even the smallest record cannot be undone.

Deleting: the built-in playlist cannot be deleted. If other rule-based playlists reference this one, every referrer is listed (the box scrolls when there are many) and you must remove those references first.

## 7. Tags and artists

A tag group is a container for tags, with two switches:

| Switch   | Meaning                                             |
|----------|-----------------------------------------------------|
| Required | Every song needs at least one tag from this group   |
| Single   | Every song may have at most one tag from this group |

The tag group list can be reordered by dragging; inside a group, every tag has a handle to the left of its input — hold it and drag to change the order, and the order is saved when you drop.

Artists have a name and notes. The artist list is sorted by name and cannot be reordered by hand; the artist picker in song details uses the same order. Artists with no songs can be removed in one go.

Deleting a referenced artist or tag group lists the affected songs first; confirming removes the references along with it.

## 8. Adaptive skipping

Adaptive skipping filters out songs you keep skipping. It is configured **per playlist**: every playlist has its own switch and four parameters, and the same song's records in two playlists never mix.

| Parameter      | Default | Range    | Meaning                                 |
|----------------|---------|----------|-----------------------------------------|
| History window | 100     | 10–1000  | How many recent plays are kept per song |
| Minimum plays  | 10      | 0–window | Never skip below this many records      |
| Skip base      | 95%     | 1–99%    | Probability ceiling                     |
| Skip threshold | 30      | 5–300 s  | Switching away sooner counts as a skip  |

The rule, for song M in playlist P:

```
n = number of records
s = number of those marked as skipped
n <= minimum plays  → never skip
otherwise           → p = min(base, 0.99) × s / n; skip with probability p
```

What gets recorded:

| Situation                                                  | Record                                    |
|------------------------------------------------------------|-------------------------------------------|
| Skipped before the threshold (Next / `Ctrl+C`)             | `1`                                       |
| Skipped after the threshold                                | `0`, full plays +1                        |
| Played to the end                                          | `0`, full plays +1                        |
| Skipped automatically                                      | nothing; only the auto-skip counter grows |
| Previous, clicking the queue, switching playlist, quitting | nothing                                   |

Automatic skipping is **silent**: no toast, no flash, the player simply moves on and marks that row as played.

"Full plays" is how many times a song was played past the threshold without being switched away **in that playlist**. It is shown in the statistics drawer and never used for the decision.

"Total plays" is a separate ledger: **one file for the whole library**, not per playlist, and clearing adaptation never clears it. The only switch that turns it off is "General → Playback records → Record total play counts"; turning adaptation off for a playlist, or turning on debug mode, does not stop it. The criterion comes from whatever is playing at the time: inside a playlist it uses the skip threshold of that playlist, single-song loop uses the global one, and a natural end always counts.

While "Library manager → Maintenance · Debug mode" is on, neither player decides nor records anything — useful when troubleshooting.

## 9. Music Player

Three columns: playlists on the left, the current track in the middle, the queue on the right. All settings live in the manager; the player only reads them.

The middle column is a song card. Its top line shows the current playlist plus a badge saying whether that playlist has adaptation on ("Adaptive on" / "Adaptive off" — hover for an explanation, which also mentions when debug mode is suppressing it). Below it come the title, artist, progress, controls and volume. In a large window the card and its contents stay centred, so the empty space sits outside the card instead of between the lines.

| Behaviour                        | Detail                                                                                                                                                  |
|----------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------|
| Click a playlist                 | Loads it and starts from the first song                                                                                                                 |
| Click the current playlist again | Nothing happens; position and queue stay put                                                                                                            |
| Click a queue row                | Jumps there immediately, from 0; played rows can be clicked too                                                                                         |
| Previous / Next                  | Wraps according to the mode; playback never stops                                                                                                       |
| Three modes                      | Shuffle, list loop, repeat one — all endless                                                                                                            |
| Repeat one, other song           | "Pick one to loop" beside the title picks from the whole library; `Ctrl+L` opens the same dialog in any mode and switches to repeat one once you choose |

The queue always shows the **whole playlist**: played rows dimmed, the current one highlighted, upcoming ones normal. The next round is only generated after the last song ends, and Previous is disabled in a fresh round.

Closing the window quits. Reopening returns to the last playlist and position, paused. Volume, mode, window size and queue visibility are remembered.

## 10. Pomodoro

Pomodoros are configured in the manager and run in the player: not as a separate window, but as a full-screen layer inside the player window that returns you to the previous view when you exit.

The "Pomodoro" section of the manager has an overview plus five groups (pomodoros, duration modes, backgrounds, chimes, ambience). Groups collapse, reorder by dragging within a group, and the context menu is the same one as "More" in the detail header. On the right:

| Item                | Detail                                                                             |
|---------------------|------------------------------------------------------------------------------------|
| Description         | A note for yourself. Pomodoros, duration modes, backgrounds, chimes and ambience all have one |
| Duration mode       | A run of minutes: odd phases focus, even phases break; 1–99 phases, 1–180 min each |
| Background          | Image or video; scaling can stretch, fit width, fit height, contain or cover       |
| Focus / Break       | One playlist each. "None" means no music for that phase — there is no extra switch |
| Chime               | Plays at the end of prep, at every phase change and at the end of the round        |
| Ambience            | "None" means off; otherwise it runs for the whole round, independent of phases     |
| Font                | Font used by the timer layer                                                       |

The overview page also carries two cards:

| Item            | Detail                                                                                                              |
|-----------------|---------------------------------------------------------------------------------------------------------------------|
| Session history | One row per completed round: which pomodoro, when it started and ended, focus time, break time. Rows survive the pomodoro being deleted — the id itself is shown then |
| Preferences     | Prep time (0–300 s, 0 skips prep), fade down before the chime (0–30 s, 0 disables it), music level during the chime (0–50%), fade back after the chime (0–10 s), timer size (20%–500%). All of them apply to every pomodoro and are shared with the player |

The player lists pomodoros under the playlists; click one to see its details. Changes made there apply to this run only and never touch the saved configuration; "Reset to defaults" clears them.

After pressing Start:

1. A prep screen (120 seconds by default, skippable, centred countdown; 0 starts right away).
2. Prep ends and the window goes full screen: background, ambience and the focus playlist start together, with the phase and countdown in the bottom-left corner.
3. A chime marks every phase change; shortly before it the music fades down to the configured level and track changes are blocked, then it fades back up once the chime ends.
4. Hovering the top-right corner reveals a translucent panel: two volumes, pause, full screen, exit. `Ctrl+C` skips a track; `Esc` does nothing.
5. After the last phase comes the completion card: the background stays, ambience keeps playing, music follows the break settings, and the round is written to the session history.

"Keep going" in the exit dialog returns to the timer; "Exit" records the time already counted and leaves. A forced kill loses at most the last 10 seconds. Leaving early is not a completed round and is not recorded.

**Importing assets**: backgrounds accept common image and video formats, chimes accept mp3/ogg, ambience accepts mp3/ogg/mp4/m4a. Everything is transcoded on import — images to PNG, videos to H.264 MP4 without an audio track; audio can be trimmed, given a "seamless crossfade" (cut at the midpoint, reordered as B+A and crossfaded, which shortens the result by one fade), or simply stripped of metadata. The import dialog cannot be dismissed by clicking outside or pressing Esc; only Cancel closes it.

## 11. Simple Player

Double-click and the default playlist starts. No menu, no picker. Everything is configured in the manager; this program only reads.

The console draws a single box: title, artist, playlist with "N / M", play mode, the adaptive switch, and a key hint on the last line — the hint shows the keys you actually bound.

| Behaviour         | Detail                                                                              |
|-------------------|-------------------------------------------------------------------------------------|
| Play modes        | Shuffle or list loop, from the manager's Simple player page                         |
| Volume            | The program never sets it: VLC uses its own level, adjustable from the system mixer |
| Skip              | `Ctrl+C` by default: next song, no quit (configurable)                              |
| Quit              | `Ctrl+Q` by default (configurable); `Alt+F4` and the window's × always exit cleanly |
| Adaptive skipping | Uses the default playlist's configuration; the screen only shows on/off             |
| Language          | Follows the language chosen in the manager; read once at startup                    |

The console can only read a limited set of keys: `Ctrl+` one letter, Space, Enter, Tab, Esc and Backspace. The settings page refuses anything else, and a hand-edited file that asks for more falls back to the factory key with a line in the log.

Exit codes: `0` normal, `1` startup failure (no VLC, empty default playlist…), `2` fatal error while running.

## 12. Integrity check

Reachable from "To review" on the overview and from Settings · Library manager · Maintenance. The quick check does not read audio; the deep check recomputes every file's MD5, then verifies the bitrate with ffprobe, reports progress by bytes, and can be cancelled.

| Category          | What is checked                                                                                                                                | Auto-fix                               |
|-------------------|------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------|
| Missing files     | Record exists, file does not                                                                                                                   | No — re-import or replace the source   |
| Orphan files      | File exists, no record                                                                                                                         | Yes — sent to the Recycle Bin          |
| Content mismatch  | Deep check finds an MD5 that differs from the record                                                                                           | No                                     |
| Fake quality      | The bitrate declared in the file header is far above the effective bitrate (size ÷ duration), or a bitrate written in the title does not match | No — find another source               |
| Broken references | A song points at a missing artist or tag; a playlist points at a missing object                                                                | Yes — the stale references are dropped |
| Tag constraints   | A required group is empty, a single group has several tags                                                                                     | No — jumps to that song                |
| Stale statistics  | Statistics mention songs that are gone                                                                                                         | Yes — pruned against the library       |

Fixes run per category, or all fixable ones at once. They only delete data that no longer has an owner, so there is no second confirmation; orphan files go to the Recycle Bin and can be restored.

## 13. Keyboard shortcuts

They only apply while the window (or console) is in the foreground; no system-wide hooks.

What follows are the **factory bindings**. All three programs can be rebound on their own page in the manager's settings, under a "Shortcuts" card. System defaults such as `Ctrl+C` / `Ctrl+V` and the `Esc` / `Tab` behaviour inside dialogs are not part of that.

Music Player:

| Key                 | Action                               |
|---------------------|--------------------------------------|
| `Space`             | Play / pause                         |
| `←` / `→`           | Seek back / forward 5 seconds        |
| `Ctrl+←` / `Ctrl+→` | Previous / next                      |
| `↑` / `↓`           | Volume ±5%                           |
| `Ctrl+C`            | Skip the current song (same as Next) |
| `Ctrl+L`            | Open the loop picker                 |
| `Esc`               | Hide the queue                       |

Simple Player:

| Key      | Action                |
|----------|-----------------------|
| `Ctrl+C` | Skip the current song |
| `Ctrl+Q` | Quit                  |
| `Alt+F4` | Quit                  |

`Alt+F4` and `F4` stay hard-wired as the escape hatch, even after rebinding skip or quit.

Manager: `Ctrl+F` focuses the search box, `Ctrl+I` imports music, `Ctrl+,` opens settings. `Esc` closes a dialog, drawer or context menu and `Tab` cycles inside dialogs — those belong to the widgets and stay fixed. There is no `Ctrl+S` — every change is saved immediately.

## 14. Settings

Five pages; changes apply immediately and there is no Save button.

| Page            | Contents                                                                                                                                                                                                                                                   |
|-----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| General         | Theme (light / dark only, no follow-system option), language (sorted by language code), adaptive defaults (window, minimum plays, skip base, skip threshold), playback records (record total play counts), logs (level, automatic cleanup, retention days) |
| Library manager | Preview volume, import (default folder, clean audio on import, FFmpeg and ffprobe status), maintenance (integrity check, clean orphan files, clear adaptation stats, open data and log folders, debug mode), shortcuts                                     |
| Simple player   | Play mode, default playlist (read-only, with a link), shortcuts                                                                                                                                                                                            |
| Player          | Default volume, play mode, remember position, shortcuts                                                                                                                                                                                                    |
| About           | Data folder (an input box with "Change" and "Reset"), user manual, reset all settings, version                                                                                                                                                             |

The skip base is a percentage from 1 to 99: the real probability is base × the song's recent skip rate.

To rebind: click a key cap, it turns into "Press keys…", then press the new combination. Modifiers alone do not count; `Esc` cancels. Two actions on the same page cannot share a key — the toast names the one already holding it. "Reset" on a row restores just that row; "Reset this page" at the bottom of the card restores all of them. The console page only accepts `Ctrl+letter`, Space, Enter, Tab, Esc and Backspace, and explains why anything else is refused.

Switching the language takes effect immediately: labels, the window title and the sort dropdown change together. The Music Player and Simple Player read the language, the shortcuts and the log settings at startup, so restart them to follow a change.

"Reset all settings" also restores language and appearance; the library, playlists and statistics are untouched. A data folder change appends `music-player` automatically and applies after a restart, moving the old contents (audio included); existing files in the target are never overwritten.

## 15. Files and folders

The program folder holds code and the sample audio shipped with it; runtime files live in system folders.

```
Music Player\
├─ manager.bat / player.bat / simple.bat / setup.bat
├─ manager.pyw / player.pyw / simple.py      thin entry points
├─ app\                                      all code
│  ├─ core\                                  pure logic
│  ├─ system\                                OS integration
│  ├─ cli\                                   Simple Player UI
│  ├─ ui\manager\                            manager UI
│  ├─ ui\player\                             player UI
│  └─ locales\                               language packs
├─ assets\                                   sample audio shipped with the program
├─ docs\                                     documentation
└─ tests\                                    tests

%PROGRAMDATA%\six-coin\music-player\         data folder (configurable)
├─ settings.json                             settings
├─ library.json                              artists, tag groups, songs
├─ playlists.json                            playlists and the default one
├─ player.json                               window size, queue visibility
├─ pomodoro.json                             pomodoros, duration modes, asset registry, stats, preferences
├─ pomodoro-sessions.json                    one record per completed pomodoro round
├─ pomodoro\background\<uid>.png / .mp4        pomodoro backgrounds (transcoded on import)
├─ pomodoro\ring\<uid>.mp3 / .ogg              chimes
├─ pomodoro\environment\<uid>.mp3 / .ogg       ambience
├─ stats\<playlist id>.json                   adaptive statistics per playlist
├─ totals.json                               total play counts per song (one file for the library)
└─ music\<md5>.<ext>                          imported audio, file name is the MD5

%LOCALAPPDATA%\six-coin\music-player\
├─ logs\                                     one log file per start
├─ locks\                                    locks
└─ data-dir.txt                              data folder pointer

%TEMP%\six-coin\music-player\               intermediate cleaning and source-replacement output
```

Deleting `settings.json` restores every setting; deleting `library.json` wipes the library; deleting files from `music\` turns those songs into "File missing". To back up, copy the whole data folder.

Log files are named by start time and rotate at 5 MB. Only the last 30 days are kept by default: older files are deleted at startup, and the General page lets you turn the cleanup off or change the number of days. All three programs share one set of log settings. When troubleshooting, read the newest one first. The data folder always ends with the project code: picking `D://Data` gives `D://Data//music-player`.

## 16. Troubleshooting

**A bat file flashes a console and closes.** The runtime is not installed. Run `setup.bat`; if it says uv is missing, install uv first.

**"The manager is already running."** Only one instance is allowed. Find the open window in the taskbar, or end the leftover process in Task Manager.

**Import says the format is unsupported.** Only `.mp3` and `.m4a` are accepted; convert anything else first.

**Import says FFmpeg was not found.** Cleaning needs it. Install it, add it to `PATH`, then press "Check again" in Settings · Library manager · Import — or turn "Clean audio on import" off.

**The player opens but there is no sound.** Check whether the song is marked "File missing" — the file was moved or renamed. If it is there, check the system volume and the player's own volume.

**The theme changed but the player looks the same.** The player reads theme and language at startup; close and reopen it.

**Replacing a source says the file already belongs to another song.** The new file's content is identical to another song in the library. Deal with that song first.

**Can I get a deleted song back?** Yes — the audio file is in the Recycle Bin under its title. Restore it, then import it again.

**The interface switched to English.** The language setting under General is English; switch back to 简体中文 (中国).

## 17. Known limitations

- Windows only. The Recycle Bin, single-instance guard and console input all call Windows APIs directly.
- No cover art, lyrics or spectrum visualization.
- No hardware media keys and no global hotkeys; each program only handles keys inside its own window.
- No transcoding. Cleaning only re-muxes; it never changes encoding parameters.
- The player does not hot-reload: songs imported or playlists edited in the manager appear after a restart.
- Closing the player can lose up to 2 seconds of position (the close handler does not wait for the page, which would risk a deadlock).
- The Simple Player has no pause, no volume control and no progress bar, and cannot switch playlists.
- No multi-user, sync or cloud backup.
- Only Chinese and English are shipped; abnormal paths (crash dialogs, logs, integrity reports) stay Chinese.

## 18. Development

See [architecture.md](../architecture.md) for layering and the rules that must not break, and [configuration.md](../configuration.md) for data formats.

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

The UI has no build step: edit the HTML / CSS / JS under `app\ui\` and reopen the window. UI changes are not covered by automated tests; walk the visual checklist in `reference.md` by hand.
