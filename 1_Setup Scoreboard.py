#!/usr/bin/env python
"""
1_Setup Scoreboard.py

Run this ONCE per game/video, from DaVinci Resolve's Edit page, with the
playhead where you want the scoreboard to start.

Workspace > Scripts > 1_Setup Scoreboard

What it does:
  - Opens a small setup dialog: where your four scoreboard PNGs live, and
    what the two teams are called. Both are remembered, so the next game
    you just click Build.
  - Inserts a blank Fusion Composition clip onto the timeline at the
    current playhead position (on whatever video track is currently
    the target track).
  - Builds the scoreboard inside it: 4 background states (your PNGs, one
    shown at a time depending on who's serving), a score number for each
    team, and a team-name text for each team.
  - Names the Fusion comp "PickleballScoreboard" so the control panel
    script (2_Scoreboard Control Panel.py) can find it later even if
    it's not on the topmost video track.

After running this:
  1. Trim/extend the new clip on the timeline so it spans however much
     of the video you want the scoreboard visible for (usually the
     whole game).
  2. Open the clip in the Fusion page (or its Edit-page Inspector) ONCE
     and drag the score numbers / team names / background into the
     position and size you want. This only needs doing once - after
     that, the layout is saved with the clip.
  3. From then on, use "2_Scoreboard Control Panel.py" to update scores
     and server as you scrub through your footage.

If something errors, copy the exact error text from Resolve's Console
(Workspace > Console) - that tells us exactly which line/API call to fix.
"""

import json
import os

COMP_NAME = "PickleballScoreboard"

# ---------------------------------------------------------------------------
# Settings. These are no longer hard-coded here - they're asked for in the
# setup dialog and remembered in a small JSON file:
#
#   Windows:  %APPDATA%\PickleballScoreboard\settings.json
#   else:     ~/.config/PickleballScoreboard/settings.json
#
# The values below are only the first-run defaults / fallbacks. You can edit
# that JSON by hand too if you'd rather; "image_files" lets you rename the
# four PNGs without touching this script.
# ---------------------------------------------------------------------------
DEFAULT_IMAGE_DIR = r"D:\Pickleball\Materials"

DEFAULT_IMAGE_FILES = {
    "T1S1": "1Game-Team1-1.png",  # Team 1 serving, server 1
    "T1S2": "1Game-Team1-2.png",  # Team 1 serving, server 2
    "T2S1": "1Game-Team2-1.png",  # Team 2 serving, server 1
    "T2S2": "1Game-Team2-2.png",  # Team 2 serving, server 2
}

DEFAULT_TEAM1 = "TEAM 1"
DEFAULT_TEAM2 = "TEAM 2"

# Which frame of the loaded clip each state needs.
#
# This matters because the four PNGs above are named "...-1.png" and
# "...-2.png", and Fusion reads a trailing number as an IMAGE SEQUENCE.
# So pointing a Loader at 1Game-Team1-1.png doesn't load that one still -
# it loads a 2-frame clip "1Game-Team1-#.png" made of the -1 and -2 files,
# and Loader_T1S1 and Loader_T1S2 end up holding the exact same clip.
# Which of the two you actually SEE is then decided by time, not by which
# file was asked for - and since HoldLastFrame pins it to the clip's LAST
# frame, every state rendered the "-2" (two dot) image forever.
#
# That's the "next server only switches between server 2 and server 2"
# behaviour: the team half worked (Team1 and Team2 are different
# sequences) while the server dots were stuck on two.
#
# The fix is to trim each Loader to the single frame it's supposed to
# show: the "-1" file is frame 0 of the sequence, the "-2" file frame 1.
SEQUENCE_FRAME = {"T1S1": 0, "T1S2": 1, "T2S1": 0, "T2S2": 1}

# How many frames of internal range to give the Fusion comp. Generous
# default (~4 hours at 60fps / ~8 hours at 30fps) so you don't hit "No
# frame available for Media Out1" on a long game. Raise it in Fusion page
# > Comp Settings > Global Start/End later if you ever need more.
DEFAULT_DURATION_FRAMES = 900000


# ---------------------------------------------------------------------------
# Saved settings
# ---------------------------------------------------------------------------

def config_path():
    base = (os.environ.get("APPDATA")
            or os.environ.get("XDG_CONFIG_HOME")
            or os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(base, "PickleballScoreboard", "settings.json")


def load_config():
    cfg = {
        "image_dir": DEFAULT_IMAGE_DIR,
        "image_files": dict(DEFAULT_IMAGE_FILES),
        "team1": DEFAULT_TEAM1,
        "team2": DEFAULT_TEAM2,
    }
    try:
        with open(config_path(), "r") as fh:
            saved = json.load(fh)
    except Exception:
        return cfg
    if isinstance(saved, dict):
        for key in ("image_dir", "team1", "team2"):
            if saved.get(key):
                cfg[key] = str(saved[key])
        if isinstance(saved.get("image_files"), dict):
            for key in DEFAULT_IMAGE_FILES:
                if saved["image_files"].get(key):
                    cfg["image_files"][key] = str(saved["image_files"][key])
    return cfg


def save_config(cfg):
    """Returns None on success, or an error string."""
    path = config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception as e:
        return "%r" % (e,)
    return None


def image_paths(cfg):
    return dict(
        (key, os.path.join(cfg["image_dir"], cfg["image_files"][key]))
        for key in DEFAULT_IMAGE_FILES
    )


def missing_images(cfg):
    return sorted(
        name for key, name in cfg["image_files"].items()
        if not os.path.isfile(os.path.join(cfg["image_dir"], name))
    )


# ---------------------------------------------------------------------------

def get_resolve():
    try:
        return resolve  # noqa: F821  (already injected by Resolve when run via Workspace > Scripts)
    except NameError:
        import DaVinciResolveScript as dvr_script
        return dvr_script.scriptapp("Resolve")


def get_bmd():
    try:
        return bmd  # noqa: F821  (injected by Resolve)
    except NameError:
        import BlackmagicFusion
        return BlackmagicFusion


def ask_settings(fusion, cfg):
    """Setup dialog. Returns an updated config dict, or None if cancelled."""
    ui = fusion.UIManager
    disp = get_bmd().UIDispatcher(ui)
    answer = {"ok": False}

    win = disp.AddWindow(
        {
            "ID": "ScoreboardSetup",
            "WindowTitle": "Set up Pickleball Scoreboard",
            "Geometry": [200, 200, 620, 300],
        },
        ui.VGroup(
            {"Spacing": 8},
            [
                ui.Label({"Text": "Folder holding the four scoreboard PNGs:"}),
                ui.HGroup(
                    {"Spacing": 8, "Weight": 0},
                    [
                        ui.LineEdit({"ID": "ImageDir", "Text": cfg["image_dir"], "Weight": 1}),
                        ui.Button({"ID": "BrowseBtn", "Text": "Browse...", "Weight": 0}),
                    ],
                ),
                ui.Label({"ID": "FoundLabel", "Text": "", "WordWrap": True}),
                ui.HGroup(
                    {"Spacing": 12, "Weight": 0},
                    [
                        ui.VGroup({"Weight": 1}, [
                            ui.Label({"Text": "Team 1 name:"}),
                            ui.LineEdit({"ID": "Team1", "Text": cfg["team1"]}),
                        ]),
                        ui.VGroup({"Weight": 1}, [
                            ui.Label({"Text": "Team 2 name:"}),
                            ui.LineEdit({"ID": "Team2", "Text": cfg["team2"]}),
                        ]),
                    ],
                ),
                ui.Label({"Text": " ", "Weight": 1}),
                ui.HGroup(
                    {"Spacing": 12, "Weight": 0},
                    [
                        ui.Button({"ID": "CancelBtn", "Text": "Cancel"}),
                        ui.Button({"ID": "BuildBtn", "Text": "Build scoreboard"}),
                    ],
                ),
            ],
        ),
    )
    itm = win.GetItems()

    def check(ev=None):
        cfg["image_dir"] = itm["ImageDir"].Text.strip()
        gone = missing_images(cfg)
        if not cfg["image_dir"]:
            itm["FoundLabel"].Text = "Pick the folder that holds your scoreboard PNGs."
        elif not gone:
            itm["FoundLabel"].Text = "All four images found."
        else:
            itm["FoundLabel"].Text = (
                "Not found in that folder: %s  (you can still build - the "
                "loaders will just come up empty until the files are there)"
                % ", ".join(gone)
            )

    def browse(ev=None):
        try:
            picked = fusion.RequestDir(itm["ImageDir"].Text.strip() or DEFAULT_IMAGE_DIR)
        except Exception:
            picked = None
        if picked:
            itm["ImageDir"].Text = str(picked).rstrip("/\\")
        check()

    def build(ev=None):
        answer["ok"] = True
        disp.ExitLoop()

    win.On.ScoreboardSetup.Close = lambda ev: disp.ExitLoop()
    win.On.CancelBtn.Clicked = lambda ev: disp.ExitLoop()
    win.On.BuildBtn.Clicked = build
    win.On.BrowseBtn.Clicked = browse
    win.On.ImageDir.TextChanged = check

    check()
    win.Show()
    disp.RunLoop()

    cfg["image_dir"] = itm["ImageDir"].Text.strip()
    cfg["team1"] = itm["Team1"].Text.strip() or DEFAULT_TEAM1
    cfg["team2"] = itm["Team2"].Text.strip() or DEFAULT_TEAM2
    win.Hide()

    return cfg if answer["ok"] else None


def main():
    resolve = get_resolve()
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        print("No project open.")
        return

    timeline = project.GetCurrentTimeline()
    if not timeline:
        print("No timeline open. Open/create a timeline first.")
        return

    cfg = ask_settings(resolve.Fusion(), load_config())
    if cfg is None:
        print("Cancelled - nothing was added to the timeline.")
        return

    err = save_config(cfg)
    if err:
        print("(Couldn't save your settings for next time: %s)" % err)
    else:
        print("Settings saved to %s" % config_path())

    paths = image_paths(cfg)
    print("Using images from: %s" % cfg["image_dir"])
    gone = missing_images(cfg)
    if gone:
        print("WARNING: these files aren't in that folder yet: %s" % ", ".join(gone))

    print("Inserting blank Fusion composition at the playhead...")
    tl_item = timeline.InsertFusionCompositionIntoTimeline()
    if not tl_item:
        print("Could not insert a Fusion composition. Make sure the Edit "
              "page is active, a video track is targeted/selected, and "
              "the playhead is over the timeline (not past the end).")
        return

    comp = tl_item.GetFusionCompByIndex(1)
    if not comp:
        print("Inserted the clip but couldn't get its Fusion composition.")
        return

    # InsertFusionCompositionIntoTimeline() creates a comp with a tiny
    # internal frame range (a couple of frames) - even after you stretch
    # the clip on the timeline, Fusion has no frames defined past that,
    # hence "No frame available for Media Out1". Widen it generously here;
    # if you ever need more than this, Fusion page > Comp Settings has
    # Global Start/End fields you can raise by hand.
    comp.SetAttrs({
        "COMPN_GlobalStart": 0,
        "COMPN_GlobalEnd": DEFAULT_DURATION_FRAMES,
        "COMPN_RenderStart": 0,
        "COMPN_RenderEnd": DEFAULT_DURATION_FRAMES,
    })

    comp.Lock()
    try:
        build_scoreboard(comp, paths, cfg["team1"], cfg["team2"])
    finally:
        comp.Unlock()

    tool_list = comp.GetToolList(False) or {}
    # GetToolList() is keyed by integer index, not name - pull .Name off
    # each tool object rather than using the dict keys directly.
    tool_names = sorted(t.Name for t in tool_list.values())
    print("Tools now in this comp (%d): %s" % (len(tool_names), tool_names))
    expected = {"Score1Text", "Score2Text", "TeamName1Text", "TeamName2Text", "MediaOut1"}
    missing = expected - set(tool_names)
    if missing:
        print("WARNING: these expected tools are missing: %s" % sorted(missing))
        print("Clip name for reference: %s" % tl_item.GetName())

    # Rename the comp so the control panel can find it reliably later,
    # regardless of which video track it ends up on.
    names = tl_item.GetFusionCompNameList()
    print("Fusion comp name(s) on this clip: %s" % names)
    if names:
        tl_item.RenameFusionCompByName(names[0], COMP_NAME)

    print("Scoreboard built. Now:")
    print("  1) Trim the new clip on the timeline to span the game.")
    print("  2) Open it in Fusion (or the Edit inspector) once to position")
    print("     the background / score numbers / team names.")
    print("  3) Use '2_Scoreboard Control Panel.py' from then on.")


def build_scoreboard(comp, paths, team1, team2):
    # Fusion's node-graph coordinates are small (roughly 1 unit ~= 1 node
    # width), but 1.0 apart still overlaps in some builds - use a bit more
    # spacing, and zigzag the row so consecutive nodes never share a row.
    x = -10.0
    row = 0

    def add(tool_id, name):
        nonlocal x, row
        y = 0.0 if row % 2 == 0 else -1.6
        t = comp.AddTool(tool_id, x, y)
        if t is None:
            raise RuntimeError(
                "comp.AddTool(%r) returned None - that tool ID isn't "
                "recognized by this Fusion/Resolve version." % tool_id
            )
        t.SetAttrs({"TOOLS_Name": name})
        x += 1.8
        row += 1
        return t

    def animate(t, input_name, t0, initial_value):
        # Fusion inputs are NOT keyframable by just assigning a value at a
        # time (tool.Input[time] = value silently just overwrites the
        # single static value everywhere, no matter what time you give
        # it) - an explicit BezierSpline modifier has to be attached to
        # the input FIRST. Only once that's connected does
        # tool.SetInput(name, value, time) actually create real,
        # independent keyframes. This was confirmed by hand in Fusion's
        # own scripting console against this exact project.
        spline = comp.AddTool("BezierSpline")
        setattr(t, input_name, spline)
        t.SetInput(input_name, initial_value, t0)
        return t

    # ---- 4 background states (loaders) ------------------------------
    # A Loader only considers its first frame valid by default and
    # errors ("No frame available") on every frame after that unless you
    # tell it to keep holding that still image - HoldLastFrame does that.
    loaders = {}
    for key, path in paths.items():
        ld = add("Loader", "Loader_" + key)
        ld.Clip = comp.MapPath(path)
        # Trim the (auto-detected) sequence down to the ONE frame this
        # state is meant to show - see the SEQUENCE_FRAME note at the top.
        # Without this, all four loaders sit on the same "-#" clip and
        # every state renders the two-dot image.
        frame_in_clip = SEQUENCE_FRAME[key]
        ld.ClipTimeStart = frame_in_clip
        ld.ClipTimeEnd = frame_in_clip
        # Now that the clip is a single frame, hold it in both directions
        # so it covers the whole comp no matter where the clip sits.
        ld.HoldFirstFrame = DEFAULT_DURATION_FRAMES
        ld.HoldLastFrame = DEFAULT_DURATION_FRAMES
        loaders[key] = ld

    # ---- merge chain that shows exactly one background state at a time
    # T1S1 is the base of the chain (no Merge of its own), but the actual
    # starting STATE of a real pickleball game is Team 1 serving, server
    # 2 - the very first serve of a game is always counted as "server 2"
    # so the starting team only gets one service turn instead of two, per
    # the standard doubles rule. So Blend_T1S2 starts at 1.0 (showing
    # through over the T1S1 base) and the rest start at 0.0.
    order = ["T1S1", "T1S2", "T2S1", "T2S2"]
    initial_blend = {"T1S2": 1.0, "T2S1": 0.0, "T2S2": 0.0}
    prev = loaders[order[0]]
    merges = {}
    t0 = comp.CurrentTime
    for key in order[1:]:
        m = add("Merge", "Blend_" + key)
        m.Background = prev
        m.Foreground = loaders[key]
        animate(m, "Blend", t0, initial_blend[key])
        merges[key] = m
        prev = m
    background_out = prev

    # ---- score text, one per team ------------------------------------
    score1 = add("TextPlus", "Score1Text")
    animate(score1, "StyledText", t0, "0")
    score1.Center = {1: 0.90, 2: 0.755}
    score1.Size = 0.06

    score2 = add("TextPlus", "Score2Text")
    animate(score2, "StyledText", t0, "0")
    score2.Center = {1: 0.90, 2: 0.245}
    score2.Size = 0.06

    # ---- team name text, one per team (static - set from the dialog) --
    name1 = add("TextPlus", "TeamName1Text")
    name1.StyledText[t0] = team1
    name1.Center = {1: 0.45, 2: 0.755}
    name1.Size = 0.05

    name2 = add("TextPlus", "TeamName2Text")
    name2.StyledText[t0] = team2
    name2.Center = {1: 0.45, 2: 0.245}
    name2.Size = 0.05

    # ---- composite everything together --------------------------------
    m1 = add("Merge", "Merge_Score1")
    m1.Background = background_out
    m1.Foreground = score1

    m2 = add("Merge", "Merge_Score2")
    m2.Background = m1
    m2.Foreground = score2

    m3 = add("Merge", "Merge_Name1")
    m3.Background = m2
    m3.Foreground = name1

    m4 = add("Merge", "Merge_Name2")
    m4.Background = m3
    m4.Foreground = name2

    # ---- connect to whatever output node the inserted comp already has
    media_out = comp.FindTool("MediaOut1")
    if media_out is None:
        for t in comp.GetToolList(False).values():
            if t.ID in ("Saver", "MediaOut"):
                media_out = t
                break
    if media_out is None:
        media_out = add("MediaOut", "MediaOut1")

    media_out.Input = m4


if __name__ == "__main__":
    main()
