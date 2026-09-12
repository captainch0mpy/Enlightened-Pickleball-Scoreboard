# Pickleball Scoreboard for DaVinci Resolve

Score a pickleball game by clicking buttons — or hitting number keys — while
you watch the footage, instead of cutting in a new title every time the score
changes.

The scripts build a Fusion scoreboard on your timeline and then keyframe it
as you go. Each click drops a keyframe at the exact frame you're parked on,
so the board flips there and holds until the next one. A full game is a few
dozen keypresses.

It knows the rules: the serving team scores, a lost rally is a side out
(server 1 → server 2 on the same team, server 2 → server 1 on the other),
and the very first serve of a game counts as "server 2" so the starting team
only gets one service turn.

A usable set of scoreboard graphics is included, so you can be scoring a game
a couple of minutes after cloning — or swap in your own.

---

## What's in here

```
1_Setup Scoreboard.py           run once per game - builds the scoreboard
2_Scoreboard Control Panel.py   the scoring panel; the one you'll live in
3_Fix Scoreboard Images.py      relinks the graphics if you move them
LICENSE
images/
  1Game-Team1-1.png             the four background states
  1Game-Team1-2.png
  1Game-Team2-1.png
  1Game-Team2-2.png
```

## Requirements

DaVinci Resolve. Developed and tested on Windows; the script paths for macOS
and Linux are below but haven't been tested there.

---

## Install

**1.** Copy the three `.py` files into Resolve's `Scripts/Utility` folder so
they appear under **Workspace → Scripts**:

- **Windows** — `%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Fusion\Scripts\Utility\`
- **macOS** — `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/`
- **Linux** — `/opt/resolve/Fusion/Scripts/Utility/`

Reopen the Workspace → Scripts menu (or restart Resolve) if they don't show
up straight away.

**2.** Put `images/` somewhere permanent — your project's media folder is a
good spot. Fusion stores an absolute path to each graphic, so if you point
Resolve at a clone of this repo and later move or delete it, every scoreboard
you've built goes offline. (Recoverable with `3_Fix Scoreboard Images`, but
easier to avoid.)

**3.** One-time per project: set **Playback → Render Cache → None** (it
defaults to *Smart*). Resolve caches a Fusion title's rendered frame, and
because the panel runs as its own script process rather than inside Resolve,
its keyframe writes aren't guaranteed to invalidate that cache — the picture
can look unchanged, or a click or two behind, even though the data is
correct. With the cache off you always see what you just clicked. It costs
nothing here; the scoreboard is a couple of PNGs and some text.

---

## Quick start

**1. Build the scoreboard.** On the Edit page, park the playhead where the
scoreboard should start and make sure the target video track is the one you
want. Then **Workspace → Scripts → 1_Setup Scoreboard**.

A dialog asks for your graphics folder — point it at wherever you put
`images/` — and your two team names. It tells you whether all four files were
found. Both settings are remembered, so every game after the first is one
click.

**2. Position it, once.** Trim the new clip to span the game, then
double-click it to open the Fusion page and drag the background, score
numbers and team names into place for your resolution. This is saved with the
clip, so it's a one-time job — copy/paste the clip for future games and skip
straight to step 3.

**3. Score the game.** **Workspace → Scripts → 2_Scoreboard Control Panel**.
Leave the panel open, move through your footage, and click **Point** when the
serving team wins a rally or **Next Server** when they lose it.

Every button reads the playhead fresh at the moment you click, so there's
nothing to refresh — just move and click.

---

## Keyboard shortcuts

Click the panel once so it has focus, then:

| Key | Action | Key | Action |
|---|---|---|---|
| `1` | Point | `2` | Next server |
| `3` | Team 1 +1 | `6` | Team 2 +1 |
| `4` | Previous clip | `5` | Next clip |
| `7` | Previous scored change | `8` | Next scored change |
| `9` | Clear the change at this frame | `Esc` | Close the panel |

Every one is printed on its button too.

**If you cut the dead air out between rallies** — so the game is a run of
separate clips, one per point — the whole workflow is `5` to reach the next
rally, then `1` or `2` to score it:

```
5 1   5 1   5 2   5 1  ...
```

> **Why digits and not letters.** Resolve claims any key it has a binding for
> before a script window ever sees it, even while that window is focused. All
> the intuitive choices are taken — `P` toggles the full screen viewer, `[`
> and `]` trim, `,` and `.` nudge, the arrows step frames — and none of them
> arrive. Digits and `Esc` aren't bound in Resolve, so they come through
> clean.
>
> Keys also only reach the panel while the *panel* is the focused window, so
> Resolve's J/K/L and space won't play footage until you click back on the
> timeline. Everything except playback can be driven from the panel.

---

## Moving around and fixing mistakes

**Prev / Next clip** jumps the playhead to the start of the previous or next
clip. Every video track is scanned, so it doesn't matter which one your
footage is on, and the scoreboard clip itself is skipped.

**Prev / Next change** walks the playhead through the points you've already
*scored* — every frame where the score or the server actually changes. The
label underneath reads `change 12 of 47` so you know where you are. This is
how you go back and correct something: step to it, then click Point / Next
Server / ±1 / Clear as normal.

**Clear the change at this frame** makes the current frame read exactly like
the frame before it. Use it for a mis-click, or when the board jumps to
something wrong and you just want that jump gone. There's otherwise no way to
remove a keyframe.

**Reset entire scoreboard to 0-0** wipes every keyframe on the whole clip —
not just the current frame — back to the starting state. Handy for reusing a
clip for a new game. Two-click confirm, since there's no undo.

The **+1 / −1** buttons under each team are there for manual corrections when
a score gets out of step.

---

## The graphics

The scoreboard is four PNGs, one per serving state, and the scripts show
exactly one at a time:

| File | Shown when |
|---|---|
| `1Game-Team1-1.png` | Team 1 serving, server 1 |
| `1Game-Team1-2.png` | Team 1 serving, server 2 |
| `1Game-Team2-1.png` | Team 2 serving, server 1 |
| `1Game-Team2-2.png` | Team 2 serving, server 2 |

The included set is 2079 × 494 with transparency: two coloured rows, Team 1
on top and Team 2 below, with empty boxes on the right for the scores. The
serving team's row carries the dots — one for server 1, two for server 2 —
and that's the *only* difference between the four files.

**The scores and team names aren't baked in.** They're Fusion text tools
drawn over the top, which is what lets the scripts change them. Leave those
areas empty in your artwork.

### Making your own

Any four images work, as long as they follow the same pattern. The quickest
route is to open one of the included PNGs in your editor of choice, restyle
it, and export the four server-dot combinations from it — they're flat
shapes, so there's not much to unpick. Things to keep:

- **The four filenames**, or update `image_files` in the settings file (see
  below) to match yours.
- **The same pixel dimensions across all four.** They're stacked on top of
  each other in Fusion, so a mismatch shows up as the board jumping when the
  server changes.
- **Transparency**, if you want the board to sit over footage rather than on
  a solid block.
- **Empty score and name areas**, per the note above.

> **Why the `-1` / `-2` naming matters.** Fusion reads a trailing number as an
> image sequence, so `1Game-Team1-1.png` and `1Game-Team1-2.png` get treated
> as one two-frame clip rather than two stills — which, left alone, makes
> every state draw the same picture. `1_Setup Scoreboard.py` handles it by
> trimming each loader to the single frame it needs, using the
> `SEQUENCE_FRAME` table at the top of the file. If you rename the files to
> something without trailing numbers, check that table.

---

## Settings

Your graphics folder and team names are stored in:

- **Windows** — `%APPDATA%\PickleballScoreboard\settings.json`
- **macOS / Linux** — `~/.config/PickleballScoreboard/settings.json`

```json
{
  "image_dir": "D:\\Pickleball\\Materials",
  "image_files": {
    "T1S1": "1Game-Team1-1.png",
    "T1S2": "1Game-Team1-2.png",
    "T2S1": "1Game-Team2-1.png",
    "T2S2": "1Game-Team2-2.png"
  },
  "team1": "TEAM 1",
  "team2": "TEAM 2"
}
```

Edit it by hand if you prefer, including renaming the four PNGs.

Moving your graphics folder only affects **new** scoreboards — clips you've
already built keep the path they were created with and will go offline. Run
**3_Fix Scoreboard Images** to repoint them at the folder in your current
settings. It only touches loaders whose files are actually missing.

---

## Troubleshooting

**The picture doesn't match what I clicked.** Render Cache — see install
step 3.

**The scoreboard is blank or shows a "media offline" box.** The graphics have
moved. Run `3_Fix Scoreboard Images`.

**"Couldn't find a PickleballScoreboard clip under the playhead."** The
playhead isn't over the scoreboard clip, or setup hasn't been run on this
timeline yet.

**"Couldn't read the playhead position."** The panel reads the Edit-page
playhead. Switch back to the Edit page from Fusion or Color.

**A keyboard shortcut does nothing.** Check the bottom line of the panel — it
shows the last key press it received. If that line doesn't change when you
press, Resolve intercepted the key before the panel saw it. Click the panel
first; keys go to whichever window has focus.

**Something threw an error.** Open **Workspace → Console** before running a
script; Python errors appear there with a line number.

---

## Found this useful?

It's free and always will be. If it saved you an evening of cutting titles
by hand, the thing that helps most is a follow — it's what keeps me making
tools and videos like this.

- **Instagram** — [@enlightenedpickleball](https://www.instagram.com/enlightenedpickleball/?hl=en)
- **YouTube** — [@EnlightenedPickleball](https://www.youtube.com/@EnlightenedPickleball)

Bug reports and pull requests are welcome too.

## License

[MIT](LICENSE) — do whatever you like with it, including using it
commercially, as long as the copyright notice comes along for the ride.

This covers everything in the repository: the scripts and the scoreboard
graphics. If you build something with it, a
credit to Enlightened Pickleball is required by the license, and a link back
is always appreciated.
