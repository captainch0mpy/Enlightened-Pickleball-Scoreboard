#!/usr/bin/env python
"""
3_Fix Scoreboard Images.py

Run this ONCE on a scoreboard clip that was built before the image-sequence
fix, or on any clip whose images have gone offline because the materials
folder moved. Workspace > Scripts > 3_Fix Scoreboard Images

WHAT IT FIXES
-------------
1. The image-sequence trap. The four scoreboard PNGs are named "...-1.png"
   and "...-2.png". Fusion reads a trailing number as an IMAGE SEQUENCE, so
   pointing a Loader at 1Game-Team1-1.png does not load that single still -
   it loads a two-frame clip "1Game-Team1-#.png" built from the -1 and -2
   files. Loader_T1S1 and Loader_T1S2 therefore ended up holding the SAME
   clip, and which of the two frames you actually saw was decided by time
   rather than by which file was requested. Because HoldLastFrame pins a
   loader to the last frame of its clip, every state rendered the "-2"
   (two dot) image forever.

   That is what "next server only switches between server 2 and server 2"
   was: the team half worked, because Team1 and Team2 are separate
   sequences, but the server dots were stuck on two in every state.

   The repair trims each of the four loaders down to the single frame it is
   supposed to show - the "-1" file is frame 0 of the sequence, the "-2"
   file is frame 1 - and holds that frame across the whole comp.

2. Offline images. The materials folder is configurable now (you pick it in
   1_Setup Scoreboard, and it's remembered in a settings file). Existing
   scoreboard clips keep whatever path they were built with, so if you move
   that folder they go offline. Any loader whose file is missing gets
   repointed at the folder in your current settings. Loaders whose files
   are still where they should be are left completely alone.

Nothing else is touched. Your scores, servers and every keyframe you have
already placed are left exactly as they are.
"""

import json
import os

COMP_NAME = "PickleballScoreboard"

# "-1" file = frame 0 of the auto-detected sequence, "-2" file = frame 1.
SEQUENCE_FRAME = {"T1S1": 0, "T1S2": 1, "T2S1": 0, "T2S2": 1}

HOLD_FRAMES = 900000

# First-run defaults / fallbacks - the real values live in the settings file
# written by 1_Setup Scoreboard.py (see config_path below).
DEFAULT_IMAGE_DIR = r"D:\Pickleball\Materials"
DEFAULT_IMAGE_FILES = {
    "T1S1": "1Game-Team1-1.png",
    "T1S2": "1Game-Team1-2.png",
    "T2S1": "1Game-Team2-1.png",
    "T2S2": "1Game-Team2-2.png",
}


def config_path():
    base = (os.environ.get("APPDATA")
            or os.environ.get("XDG_CONFIG_HOME")
            or os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(base, "PickleballScoreboard", "settings.json")


def load_config():
    cfg = {"image_dir": DEFAULT_IMAGE_DIR, "image_files": dict(DEFAULT_IMAGE_FILES)}
    try:
        with open(config_path(), "r") as fh:
            saved = json.load(fh)
    except Exception:
        return cfg
    if isinstance(saved, dict):
        if saved.get("image_dir"):
            cfg["image_dir"] = str(saved["image_dir"])
        if isinstance(saved.get("image_files"), dict):
            for key in DEFAULT_IMAGE_FILES:
                if saved["image_files"].get(key):
                    cfg["image_files"][key] = str(saved["image_files"][key])
    return cfg


def get_resolve():
    try:
        return resolve  # noqa: F821
    except NameError:
        import DaVinciResolveScript as dvr_script
        return dvr_script.scriptapp("Resolve")


def read_clip_path(comp, tool):
    """Whatever file this Loader currently points at, as an OS path."""
    raw = None
    try:
        raw = tool.GetInput("Clip")
    except Exception:
        raw = None
    if isinstance(raw, dict):
        # Loader.Clip is an indexed input - the path sits under key 1.
        raw = raw.get(1) or raw.get("1") or next(iter(raw.values()), None)
        if isinstance(raw, dict):
            raw = raw.get("Filename") or next(iter(raw.values()), None)
    if not raw:
        return ""
    path = str(raw)
    try:
        path = comp.ReverseMapPath(path)
    except Exception:
        pass
    return path


def fix_comp(comp, cfg):
    trimmed, relinked = [], []
    for key, frame_in_clip in sorted(SEQUENCE_FRAME.items()):
        tool = comp.FindTool("Loader_" + key)
        if tool is None:
            print("  (no Loader_%s in this comp - skipping)" % key)
            continue

        # --- relink, if the file it points at isn't there any more -------
        current = read_clip_path(comp, tool)
        wanted_name = cfg["image_files"][key]
        wanted = os.path.join(cfg["image_dir"], wanted_name)
        if current and os.path.isfile(current):
            pass                                  # still online, leave it
        elif not os.path.isfile(wanted):
            print("  Loader_%s is offline (%s) and the replacement isn't "
                  "there either: %s" % (key, current or "no clip set", wanted))
        else:
            tool.Clip = comp.MapPath(wanted)
            print("  Loader_%s relinked: %s  ->  %s"
                  % (key, current or "(no clip set)", wanted))
            relinked.append(key)

        # --- trim to the single frame this state should show -------------
        before = None
        try:
            before = (tool.GetInput("ClipTimeStart"), tool.GetInput("ClipTimeEnd"))
        except Exception:
            pass

        tool.SetInput("ClipTimeStart", frame_in_clip)
        tool.SetInput("ClipTimeEnd", frame_in_clip)
        tool.SetInput("HoldFirstFrame", HOLD_FRAMES)
        tool.SetInput("HoldLastFrame", HOLD_FRAMES)

        after = None
        try:
            after = (tool.GetInput("ClipTimeStart"), tool.GetInput("ClipTimeEnd"))
        except Exception:
            pass

        print("  Loader_%s -> clip frame %d   (trim was %s, now %s)"
              % (key, frame_in_clip, before, after))
        trimmed.append(key)
    return trimmed, relinked


def main():
    resolve = get_resolve()
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        print("No project open.")
        return
    timeline = project.GetCurrentTimeline()
    if not timeline:
        print("No timeline open.")
        return

    cfg = load_config()
    print("Settings file: %s" % config_path())
    print("Materials folder: %s" % cfg["image_dir"])
    print("")

    # Scan every video track rather than relying on the playhead, so it
    # doesn't matter where you're parked when you run this.
    found_any = False
    relinked_any = False
    for track_idx in range(1, timeline.GetTrackCount("video") + 1):
        for item in (timeline.GetItemListInTrack("video", track_idx) or []):
            names = item.GetFusionCompNameList() or []
            if COMP_NAME not in names:
                continue
            found_any = True
            print("Fixing '%s' on video track %d (clip: %s)"
                  % (COMP_NAME, track_idx, item.GetName()))
            _trimmed, relinked = fix_comp(item.GetFusionCompByName(COMP_NAME), cfg)
            relinked_any = relinked_any or bool(relinked)

    if not found_any:
        print("Couldn't find a '%s' comp on any video track of this "
              "timeline. Open the timeline that has your scoreboard clip "
              "on it and run this again." % COMP_NAME)
        return

    print("")
    print("Done. Scrub a frame or two and the server dots should now match")
    print("the panel: 1 dot for server 1, 2 dots for server 2, on the")
    print("serving team's row.")
    if relinked_any:
        print("Some loaders were repointed at %s - if that's the wrong "
              "folder, set the right one in 1_Setup Scoreboard and run this "
              "again." % cfg["image_dir"])


if __name__ == "__main__":
    main()
