#!/usr/bin/env python
"""
2_Scoreboard Control Panel.py

Run from DaVinci Resolve's Edit page:  Workspace > Scripts > 2_Scoreboard Control Panel

Requires that "1_Setup Scoreboard.py" has already been run once on this
clip (or an earlier one you copy/pasted), so there's a Fusion comp named
"PickleballScoreboard" sitting on the timeline.

How to use it:
  - Scrub your main timeline to the frame where a rally ends.
  - Click "Point" if the serving team won the rally (their score goes up,
    same server keeps serving) or "Next Server" if they lost it - a side
    out (no score change; server 1 -> server 2 same team, server 2 ->
    server 1 other team).
  - The +1/-1 buttons under each team are there for manual corrections.
  - Each click drops a keyframe on the scoreboard at that exact frame, so
    it flips there and holds until the next click.
  - Move the playhead again, click again, repeat. Every button reads the
    playhead fresh at the moment you click it, so the panel never needs
    telling that you moved.
  - "Prev clip" / "Next clip" jump the playhead to the start of the
    previous/next clip on the timeline. If you cut the dead air out
    between rallies, that's one press per point.
  - "<< Prev change" / "Next change >>" walk the playhead through the
    points you've already SCORED - every frame where the score or the
    server actually changes. That's how you go back and fix a mistake:
    step to it, then Point / Next Server / +1 / -1 / Clear as normal. The
    label underneath says which change you're parked on.
  - "Clear the change at this frame" makes the current frame read exactly
    like the frame before it. Use it for a mis-click, or when you find a
    spot where the board jumps to something wrong and you want that jump
    gone. There is otherwise no way to remove a keyframe.
  - "Reset entire scoreboard to 0-0" wipes every keyframe on the WHOLE
    clip, everywhere on the timeline, back to 0-0 / Team 1 serving /
    server 2 (the real starting state of a pickleball game - the very
    first serve is always "server 2" so the starting team only gets one
    service turn). It's a two-click confirm since there's no undo.

KEYBOARD
--------
Click the panel once so it has focus, then:

    1   point to the serving team        2   next server (side out)
    3   TEAM 1 +1                        6   TEAM 2 +1
    4   previous clip                    5   next clip
    7   previous scored change           8   next scored change
    9   clear the change at this frame   Esc close the panel

The everyday loop is 5 to reach the next rally, then 1 or 2 to score it:

    5 1   5 1   5 2   5 1   ...

WHY DIGITS AND NOT LETTERS. Resolve claims any key it has its own binding
for before a script window sees it, even while that window is focused. The
obvious choices are all taken - P toggles the full screen viewer, [ and ]
trim, , and . nudge, the arrows step frames - and none of them ever arrive
here. Digits and Esc aren't bound in Resolve, so they come straight
through. Measured with "6_Key Test.py", not guessed at; run that script if
you want to find more free keys.

The letter and bracket shortcuts are still wired up as second names for
the same actions, on the off chance your keyboard layout or Resolve
settings leave one of them free - but don't rely on them.

Keys only reach the panel while the panel window is the focused one, so
Resolve's J/K/L and space won't play footage until you click back on the
timeline. Everything except playback can be driven from the panel.

Leave this window open while you work - it doesn't need to be closed and
reopened between clicks.

ONE-TIME SETUP: in Resolve, go to Playback > Render Cache and set it to
"None" (it defaults to "Smart"). DaVinci caches a Fusion title's rendered
frame, and because this panel runs as a separate script process rather
than inside Resolve itself, its keyframe writes don't reliably bust that
cache - the picture can look unchanged (or behind by a click or two) even
though the score/server data is correct. With Render Cache off, Resolve
always renders the frame fresh, so what you see always matches what you
just clicked. Confirmed live against this project's Fusion comp - this
setting was the actual fix, not anything about which frame the playhead
sits on.
"""

COMP_NAME = "PickleballScoreboard"

# Every input the scoreboard animates. Reset rebuilds exactly this set and
# the change-navigation scans exactly this set, so if you ever add another
# animated input to the scoreboard, add it here too.
#
# Blend_T1S2 starts at 1.0 (not 0.0) because the actual starting state of
# a real pickleball game is Team 1 serving, SERVER 2 - the very first
# serve of a game is always counted as "server 2" so the starting team
# only gets one service turn instead of two, per the standard doubles
# rule. Same starting state Setup builds.
ANIMATED_INPUTS = [
    ("Score1Text", "StyledText", "0"),
    ("Score2Text", "StyledText", "0"),
    ("Blend_T1S2", "Blend", 1.0),
    ("Blend_T2S1", "Blend", 0.0),
    ("Blend_T2S2", "Blend", 0.0),
]

# Pickleball side-out rules: the serving team keeps serving (and scoring)
# until it loses a rally. Losing as server 1 hands the serve to server 2 on
# the SAME team; losing as server 2 hands the serve to server 1 on the
# OTHER team. That's the exact chain "Next Server" walks below.
NEXT_STATE = {
    "T1S1": "T1S2",
    "T1S2": "T2S1",
    "T2S1": "T2S2",
    "T2S2": "T1S1",
}


def get_resolve():
    try:
        return resolve  # noqa: F821
    except NameError:
        import DaVinciResolveScript as dvr_script
        return dvr_script.scriptapp("Resolve")


def get_bmd():
    try:
        return bmd  # noqa: F821  (injected by Resolve)
    except NameError:
        import BlackmagicFusion
        return BlackmagicFusion


# ---------------------------------------------------------------------------
# Timecode
# ---------------------------------------------------------------------------

def is_drop_frame(timeline, fps):
    """Is this timeline using drop-frame timecode?

    Ask Resolve first; fall back to "any NTSC-ish fractional frame rate is
    probably drop-frame", which is the usual default for 29.97/59.94.
    """
    for key in ("timelineDropFrameTimecode", "timelineDropFrameTimeCode"):
        try:
            v = timeline.GetSetting(key)
        except Exception:
            v = None
        if v not in (None, ""):
            return str(v).strip().lower() in ("1", "true", "yes", "on")
    return abs(fps - round(fps)) > 0.001


def timecode_to_frame(tc, fps, drop_frame=False):
    """Convert an "HH:MM:SS:FF" / "HH:MM:SS;FF" timecode to a frame count.

    Drop-frame timecode keeps clock time honest at 29.97/59.94 by SKIPPING
    label numbers: the first 2 (at 30) or 4 (at 60) frame numbers of every
    minute are never used, except on minutes divisible by 10. So the frame
    count for a given timecode is NOT seconds * fps - it's seconds *
    NOMINAL fps (30, 60) minus all the labels that were skipped along the
    way.

    The naive round(seconds * fps) + frames version this replaced was wrong
    by a growing amount - at 01:02:40;04 on this 59.94 timeline it produced
    225378 where the true frame is 225380, so the panel read and wrote
    keyframes two frames away from the frame Resolve was actually showing.
    """
    h, m, s, f = [int(p) for p in tc.replace(";", ":").split(":")]
    nominal = int(round(fps))
    total = (((h * 60) + m) * 60 + s) * nominal + f
    if drop_frame:
        # 2 dropped labels per minute at 30fps, 4 at 60fps, etc.
        dropped_per_minute = int(round(nominal / 15.0))
        total_minutes = h * 60 + m
        total -= dropped_per_minute * (total_minutes - total_minutes // 10)
    return total


def frame_to_timecode(frame, fps, drop_frame=False, sep=None):
    """The exact inverse of timecode_to_frame - a frame count back to a
    timecode label. Needed by the change-navigation buttons, which know
    which FRAME they want to jump to but can only move Resolve's playhead
    by handing it a timecode string.
    """
    frame = int(frame)
    nominal = int(round(fps))
    if drop_frame:
        dropped = int(round(nominal / 15.0))
        frames_per_10_min = nominal * 600 - dropped * 9
        frames_per_min = nominal * 60 - dropped
        tens, rest = divmod(frame, frames_per_10_min)
        frame += dropped * 9 * tens
        if rest > dropped:
            frame += dropped * ((rest - dropped) // frames_per_min)
    if sep is None:
        sep = ";" if drop_frame else ":"
    f = frame % nominal
    total_seconds = frame // nominal
    return "%02d:%02d:%02d%s%02d" % (
        total_seconds // 3600,
        (total_seconds // 60) % 60,
        total_seconds % 60,
        sep,
        f,
    )


# ---------------------------------------------------------------------------
# Finding the scoreboard
# ---------------------------------------------------------------------------

def locate_scoreboard(resolve):
    """Returns (ctx, error_message). error_message is None on success.

    ctx carries everything a button needs: the comp, the comp-LOCAL frame
    the playhead maps to, and enough of the timeline/clip geometry to turn
    a comp-local frame back into a playhead position.

    What this deliberately does NOT do is assign comp.CurrentTime.
    Assigning it also drags Resolve's own Edit-page playhead, and the
    playhead lands one frame EARLIER than it started - so the panel walked
    the user's playhead backwards on every single action, including a
    plain read. Confirmed live: four clicks moved the playhead 92451 ->
    92450 -> 92449 -> 92448 with nobody touching the timeline.

    That creep is what produced the "first click does nothing, second click
    skips" bug. Each click writes the new state at frame t plus a keyframe
    holding the OLD value at t-1 (the hard-cut trick). The drift then parks
    the playhead on that t-1 frame, so the NEXT click reads the old value
    back, concludes nothing has changed yet, and rewrites the same
    transition.

    comp.CurrentTime was only ever being set so the code had somewhere to
    read the frame number back from - but we compute that number here
    anyway, so we can just carry it around and never touch the comp's clock.
    """
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return None, "No project open."
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return None, "No timeline open."

    try:
        fps = float(timeline.GetSetting("timelineFrameRate"))
    except Exception:
        fps = 30.0
    df = is_drop_frame(timeline, fps)

    # Resolve only reports a playhead timecode while the Edit (or Cut)
    # page is up - ask for it from the Fusion/Color page and it hands back
    # None, which used to blow up with a raw traceback in the console.
    try:
        tc = timeline.GetCurrentTimecode()
    except Exception:
        tc = None
    if not tc:
        return None, (
            "Couldn't read the playhead position. Switch back to the Edit "
            "page (this panel reads the Edit-page playhead) and try again."
        )
    frame = timecode_to_frame(tc, fps, df)

    def build(item):
        if not item:
            return None
        if COMP_NAME not in (item.GetFusionCompNameList() or []):
            return None
        comp = item.GetFusionCompByName(COMP_NAME)
        if comp is None:
            return None
        start = item.GetStart()
        left = item.GetLeftOffset()
        return {
            "timeline": timeline, "item": item, "comp": comp,
            "fps": fps, "df": df, "tc": tc,
            "frame": frame, "t": frame - start + left,
            "start": start, "end": item.GetEnd(), "left": left,
        }

    # Fast path: the scoreboard is the current (topmost) item under the playhead.
    ctx = build(timeline.GetCurrentVideoItem())
    if ctx is not None:
        return ctx, None

    # Fallback: scan every video track for a clip under the playhead that
    # contains the scoreboard comp (covers it not being the top track).
    for track_idx in range(1, timeline.GetTrackCount("video") + 1):
        for it in (timeline.GetItemListInTrack("video", track_idx) or []):
            if it.GetStart() <= frame <= it.GetEnd():
                ctx = build(it)
                if ctx is not None:
                    return ctx, None

    return None, (
        "Couldn't find a '%s' clip under the playhead on any video track. "
        "Move the playhead over the scoreboard clip, or run "
        "'1_Setup Scoreboard.py' first if you haven't yet." % COMP_NAME
    )


def seek(ctx, timeline_frame):
    """Move Resolve's playhead to a timeline frame. True if it landed.

    Don't trust SetCurrentTimecode's return value, and don't string-compare
    the timecode back either: on a drop-frame timeline Resolve hands back
    "HH:MM:SS:FF" with colons while wanting the ";" form on the way in, so
    the strings legitimately differ even on success. Compare FRAMES.
    """
    timeline, fps, df = ctx["timeline"], ctx["fps"], ctx["df"]
    for sep in ((";", ":") if df else (":",)):
        tc = frame_to_timecode(timeline_frame, fps, df, sep)
        try:
            timeline.SetCurrentTimecode(tc)
            landed = timeline.GetCurrentTimecode()
        except Exception:
            continue
        if landed and timecode_to_frame(landed, fps, df) == timeline_frame:
            return True
    return False


# ---------------------------------------------------------------------------
# Reading and writing keyframes
# ---------------------------------------------------------------------------

def get_spline(comp, tool, input_name):
    """The BezierSpline driving tool[input_name], or None."""
    try:
        out = tool[input_name].GetConnectedOutput()
        if out:
            spline = out.GetTool()
            if spline:
                return spline
    except Exception:
        pass
    # Fusion auto-names an unnamed modifier "<ParentTool><InputName>".
    try:
        return comp.FindTool(tool.Name + input_name)
    except Exception:
        return None


def key_times(comp, tool, input_name):
    """Sorted integer frames that this input has keyframes on."""
    spline = get_spline(comp, tool, input_name)
    if spline is None:
        return []
    try:
        raw = spline.GetKeyFrames() or {}
    except Exception:
        return []
    out = []
    for raw_time in raw.keys():
        try:
            out.append(int(round(float(raw_time))))
        except (TypeError, ValueError):
            continue
    out.sort()
    return out


def hold_until_next_change(comp, tool, input_name, t, value):
    """Guard the stretch AFTER frame t.

    Fusion interpolates smoothly between keyframes. Writing the old value
    at t-1 makes the change itself a hard cut, but says nothing about the
    run from t to the NEXT keyframe further along. If that one holds a
    different value, Fusion ramps across the whole gap - which over a few
    thousand frames reads as the dots slowly fading from one team to the
    other on their own. So re-stamp our value one frame before the next
    key, and the change lands exactly where the next click put it.
    """
    later = [k for k in key_times(comp, tool, input_name) if k > t]
    if not later:
        return
    nxt = later[0]
    if nxt - t > 1:
        tool.SetInput(input_name, value, nxt - 1)


def read_state(comp, t):
    state = "T1S1"
    for key in ("T1S2", "T2S1", "T2S2"):
        tool = comp.FindTool("Blend_" + key)
        if tool is not None:
            try:
                if float(tool.Blend[t]) > 0.5:
                    state = key
            except Exception:
                pass
    score1 = comp.FindTool("Score1Text").StyledText[t]
    score2 = comp.FindTool("Score2Text").StyledText[t]
    return {"t": t, "state": state, "score1": score1, "score2": score2}


def read_team_names(comp, t):
    names = []
    for tool_name, fallback in (("TeamName1Text", "TEAM 1"), ("TeamName2Text", "TEAM 2")):
        value = None
        tool = comp.FindTool(tool_name)
        if tool is not None:
            try:
                value = tool.StyledText[t]
            except Exception:
                value = None
        names.append(str(value).strip() if value else fallback)
    return names


def write_score(comp, which, value, t):
    # tool.Input[time] = value does NOT create a real per-time keyframe on
    # its own - it just overwrites the single static value everywhere, no
    # matter what time index you give it. Confirmed by hand in Fusion's
    # scripting console: a keyframe only sticks once the input has an
    # explicit BezierSpline modifier attached (which "1_Setup
    # Scoreboard.py" does for every input this panel touches) AND you write
    # through SetInput(name, value, time) rather than the bracket
    # shorthand. Text can't be interpolated, so it already steps - no hold
    # keyframes needed on this one.
    tool = comp.FindTool("Score1Text" if which == 1 else "Score2Text")
    tool.SetInput("StyledText", str(value), t)


def write_serving_state(comp, state, t):
    # Same SetInput requirement as write_score. On top of that, Blend is
    # numeric and Fusion's default spline interpolates smoothly - fine for
    # a fade, wrong for a scoreboard dot that should snap. So when a value
    # is actually changing, drop a keyframe holding the OLD value one frame
    # earlier, which forces a hard cut.
    #
    # Read that old value at t-1, NOT at t. Reading at t looks right until
    # you click twice on the same frame: the second time round the value at
    # t is already the new one, so writing it at t-1 overwrites what was
    # true before the change and everything back to the previous key turns
    # into a ramp.
    for key in ("T1S2", "T2S1", "T2S2"):
        tool = comp.FindTool("Blend_" + key)
        if tool is None:
            continue
        new_value = 1.0 if key == state else 0.0
        before = None
        if t > 0:
            try:
                before = 1.0 if float(tool.Blend[t - 1]) > 0.5 else 0.0
            except Exception:
                before = None
        if before is not None and abs(before - new_value) > 0.001:
            tool.SetInput("Blend", before, t - 1)
        tool.SetInput("Blend", new_value, t)
        hold_until_next_change(comp, tool, "Blend", t, new_value)


def clear_change(comp, t):
    """Make frame t read exactly like frame t-1. Returns an error or None."""
    if t <= 0:
        return "There's no frame before this one to copy from."
    for tool_name, input_name, _initial in ANIMATED_INPUTS:
        tool = comp.FindTool(tool_name)
        if tool is None:
            continue
        try:
            before = tool[input_name][t - 1]
        except Exception:
            continue
        if input_name == "Blend":
            try:
                value = 1.0 if float(before) > 0.5 else 0.0
            except (TypeError, ValueError):
                continue
        else:
            value = str(before)
        tool.SetInput(input_name, value, t)
        if input_name == "Blend":
            hold_until_next_change(comp, tool, input_name, t, value)
    return None


def reset_scoreboard(comp, t=None):
    # Wipes every keyframe on the whole clip, not just at the current
    # frame: deletes every BezierSpline modifier in this comp (that's every
    # animated input the scoreboard uses - nothing else in this comp should
    # have one) and reattaches a fresh spline holding the clean starting
    # value.
    tool_list = comp.GetToolList(False) or {}
    for tool in list(tool_list.values()):
        if tool.ID == "BezierSpline":
            try:
                tool.Delete()
            except Exception:
                pass

    # Attaching a fresh BezierSpline to an input that currently holds a
    # value makes Fusion SEED the new spline with a keyframe at the comp's
    # own current time carrying that old value. Writing the clean value at
    # frame 0 alone therefore wiped the whole clip EXCEPT that one seeded
    # frame - the "reset left the old score sitting at the playhead" bug.
    #
    # An earlier fix tried to guess where the seed landed (frame 0, the
    # user's frame, and comp.CurrentTime) and that guess was itself wrong:
    # comp.CurrentTime was stale, so the reset planted a clean-state island
    # in the middle of a scored game. Don't guess. Attach the spline, write
    # the clean value, then read the keys that ACTUALLY exist back out and
    # stamp the clean value on every one of them.
    for tool_name, input_name, initial_value in ANIMATED_INPUTS:
        tool = comp.FindTool(tool_name)
        if tool is None:
            continue
        spline = comp.AddTool("BezierSpline")
        setattr(tool, input_name, spline)
        tool.SetInput(input_name, initial_value, 0)
        try:
            frame = int(t)
        except (TypeError, ValueError):
            frame = None
        if frame is not None:
            tool.SetInput(input_name, initial_value, frame)
        for existing in key_times(comp, tool, input_name):
            tool.SetInput(input_name, initial_value, existing)


# ---------------------------------------------------------------------------
# Where the score/server actually changes
# ---------------------------------------------------------------------------

def keyframe_value(entry):
    """Pull the numeric value out of a GetKeyFrames() entry."""
    if isinstance(entry, dict):
        for key in (1, 1.0, "1", 0, 0.0, "0"):
            if key in entry:
                try:
                    return float(entry[key])
                except (TypeError, ValueError):
                    pass
        for value in entry.values():
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None
    try:
        return float(entry)
    except (TypeError, ValueError):
        return None


def sample_inputs(comp):
    """{(tool, input): [(frame, value), ...]} for every animated input.

    Read once, in bulk, so the change list can be worked out arithmetically
    instead of asking Fusion for the state at thousands of frames.
    """
    data = {}
    for tool_name, input_name, _initial in ANIMATED_INPUTS:
        tool = comp.FindTool(tool_name)
        if tool is None:
            continue
        spline = get_spline(comp, tool, input_name)
        if spline is None:
            continue
        try:
            raw = spline.GetKeyFrames() or {}
        except Exception:
            continue
        points = []
        for raw_time, entry in raw.items():
            try:
                frame = int(round(float(raw_time)))
            except (TypeError, ValueError):
                continue
            if input_name == "Blend":
                value = keyframe_value(entry)
                if value is None:
                    try:
                        value = float(tool[input_name][frame])
                    except Exception:
                        continue
                points.append((frame, 1.0 if value > 0.5 else 0.0))
            else:
                # Text keyframe entries don't carry the string in a layout
                # we can read - ask the tool for the value at that frame.
                try:
                    value = tool[input_name][frame]
                except Exception:
                    value = None
                points.append((frame, "" if value is None else str(value)))
        points.sort()
        data[(tool_name, input_name)] = points
    return data


def value_at(points, frame, default):
    """Step lookup: the value of the last keyframe at or before `frame`.

    Every animated input here is stepped by design (text can't interpolate,
    and the Blends are hard-cut and hold-guarded), so a step lookup is an
    honest reading of what the board shows.
    """
    value = default
    for key_frame, key_value in points:
        if key_frame <= frame:
            value = key_value
        else:
            break
    return value


def signature(data, frame):
    state = "T1S1"
    for key in ("T1S2", "T2S1", "T2S2"):
        points = data.get(("Blend_" + key, "Blend"))
        if points is None:
            continue
        default = 1.0 if key == "T1S2" else 0.0
        if value_at(points, frame, default) > 0.5:
            state = key
    return (
        state,
        value_at(data.get(("Score1Text", "StyledText"), []), frame, "0"),
        value_at(data.get(("Score2Text", "StyledText"), []), frame, "0"),
    )


def clip_starts(ctx):
    """TIMELINE frames where a clip begins, under the scoreboard's span.

    The workflow this exists for: the dead air between rallies gets cut
    out, so the finished game is a run of separate clips, one per point.
    Jumping edit to edit is therefore jumping point to point.

    Every video track is scanned, because the footage isn't necessarily on
    V1 - but the scoreboard clip itself is skipped, since its own start
    isn't a point boundary and it usually spans the whole game anyway.
    Results are clipped to the scoreboard's span: past that the panel has
    no comp to write to.

    Note these are TIMELINE frames, not comp-local ones - they're compared
    against ctx["frame"] and handed straight to seek(), no offset maths.
    """
    timeline = ctx["timeline"]
    points = set()
    for track_idx in range(1, timeline.GetTrackCount("video") + 1):
        for item in (timeline.GetItemListInTrack("video", track_idx) or []):
            try:
                if COMP_NAME in (item.GetFusionCompNameList() or []):
                    continue
            except Exception:
                pass
            try:
                points.add(int(item.GetStart()))
            except (TypeError, ValueError):
                continue
    return sorted(f for f in points if ctx["start"] <= f <= ctx["end"])


def change_frames(ctx):
    """Comp-local frames where the score or server visibly changes.

    Only keyframe times can possibly be change points, so those are the
    only candidates worth testing - and most of them aren't real changes:
    the hard-cut hold at t-1 and the hold-until-next-change guard both
    plant keyframes that deliberately carry the SAME value as the frame
    before them. Comparing the full board state at f against f-1 filters
    those out, so the buttons only ever land on something you'd actually
    see happen.
    """
    data = sample_inputs(ctx["comp"])
    candidates = sorted(set(f for points in data.values() for f, _v in points))
    low = ctx["left"]
    high = ctx["left"] + (ctx["end"] - ctx["start"])
    out = []
    for frame in candidates:
        if frame < low or frame > high:
            continue          # keyframe sits outside the trimmed clip
        if signature(data, frame) != signature(data, frame - 1):
            out.append(frame)
    return out


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

# Qt key codes, as Fusion's KeyPress event reports them.
KEY_ESCAPE = 0x01000000
KEY_LEFT, KEY_UP, KEY_RIGHT, KEY_DOWN = 0x01000012, 0x01000013, 0x01000014, 0x01000015


def event_field(ev, *names):
    """Read a field off a Fusion event, whichever way it's exposed.

    Fusion hands events over as a dict-like object in Python, but which
    keys exist has shifted between versions - so try subscripting, then
    attributes, and give up quietly rather than throwing inside a key
    handler (an exception there kills the event loop, not just the press).
    """
    for name in names:
        try:
            value = ev[name]
        except Exception:
            value = None
        if value is None:
            value = getattr(ev, name, None)
        if value is not None:
            return value
    return None


def shift_held(ev):
    mods = event_field(ev, "Modifiers", "modifiers")
    if mods is None:
        return False
    if isinstance(mods, dict):
        return bool(mods.get("Shift") or mods.get("SHIFT") or mods.get("shift"))
    if isinstance(mods, (list, tuple, set)):
        return any(str(m).lower().startswith("shift") for m in mods)
    return "shift" in str(mods).lower()


# ---------------------------------------------------------------------------

def main():
    resolve = get_resolve()
    fusion = resolve.Fusion()
    ui = fusion.UIManager
    disp = get_bmd().UIDispatcher(ui)

    win = disp.AddWindow(
        {
            "ID": "ScoreboardPanel",
            "WindowTitle": "Pickleball Scoreboard",
            # Wide enough that the longest button caption fits without the
            # right-hand side being clipped on open. The window is still
            # freely resizable.
            # Height is deliberately set BELOW what the rows add up to.
            # Qt won't shrink a window under its layout's minimum, so this
            # snaps to exactly the height the controls need - no guessing at
            # a number, and no leftover for the bottom VGap to absorb. Drag
            # it taller and the extra goes to the bottom edge.
            "Geometry": [100, 100, 480, 300],
            # Ask Fusion to deliver key presses to this window. Only fires
            # while the window is focused - see the KEYBOARD section of the
            # docstring. There are deliberately no text fields left in this
            # panel, so nothing swallows a typed character.
            #
            # "Close" MUST be listed here. Declaring an Events table
            # REPLACES the window's default event set rather than adding to
            # it, so asking for KeyPress alone silently stopped the title
            # bar's X from firing win.On.ScoreboardPanel.Close - the window
            # vanished but RunLoop() never exited and the script stayed
            # running with no error printed anywhere.
            "Events": {"Close": True, "KeyPress": True},
        },
        ui.VGroup(
            # KeyPress is declared BOTH here and on the window. Which of the
            # two actually receives the press differs between builds: the
            # window only sees it if no child widget consumed it first, and
            # buttons hold focus after a click. Declaring it on the root
            # group as well gives the press a second chance to be caught.
            {"ID": "PanelRoot", "Spacing": 8, "Events": {"KeyPress": True}},
            [
                # Every row below is Weight 0 so it takes exactly the height
                # it needs; one stretch spacer further down soaks up
                # whatever's left over. Without that, spare window height
                # got shared out among the rows that still had weight and
                # the status line floated in the middle of a tall empty gap.
                ui.Label({"ID": "StatusLabel", "Text": "Loading...",
                          "WordWrap": True, "Weight": 0}),
                ui.HGroup(
                    {"Spacing": 12, "Weight": 0},
                    [
                        ui.VGroup(
                            {"Weight": 1},
                            [
                                ui.Label({"ID": "Team1Header", "Text": "TEAM 1",
                                          "Alignment": {"AlignHCenter": True}}),
                                ui.Label({"ID": "Score1Label", "Text": "0",
                                          "Alignment": {"AlignHCenter": True},
                                          "Font": ui.Font({"PixelSize": 28})}),
                                ui.HGroup([
                                    ui.Button({"ID": "T1Minus", "Text": "-1"}),
                                    ui.Button({"ID": "T1Plus", "Text": "+1   (3)"}),
                                ]),
                            ],
                        ),
                        ui.VGroup(
                            {"Weight": 1},
                            [
                                ui.Label({"ID": "Team2Header", "Text": "TEAM 2",
                                          "Alignment": {"AlignHCenter": True}}),
                                ui.Label({"ID": "Score2Label", "Text": "0",
                                          "Alignment": {"AlignHCenter": True},
                                          "Font": ui.Font({"PixelSize": 28})}),
                                ui.HGroup([
                                    ui.Button({"ID": "T2Minus", "Text": "-1"}),
                                    ui.Button({"ID": "T2Plus", "Text": "+1   (6)"}),
                                ]),
                            ],
                        ),
                    ],
                ),
                ui.VGroup(
                    {"Spacing": 4, "Weight": 0},
                    [
                        ui.Label({"ID": "ServingLabel", "Text": "Serving: -", "Weight": 0,
                                  "Alignment": {"AlignHCenter": True}}),
                        ui.HGroup(
                            {"Spacing": 12},
                            [
                                ui.Button({"ID": "PointBtn", "Text": "Point   (1)"}),
                                ui.Button({"ID": "NextServerBtn", "Text": "Next Server   (2)"}),
                            ],
                        ),
                    ],
                ),
                ui.VGroup(
                    {"Spacing": 4, "Weight": 0},
                    [
                        ui.Label({"Text": "Move the playhead:", "Weight": 0}),
                        ui.HGroup(
                            {"Spacing": 12},
                            [
                                ui.Button({"ID": "PrevClipBtn", "Text": "4   |<<  Prev clip"}),
                                ui.Button({"ID": "NextClipBtn", "Text": "Next clip  >>|   5"}),
                            ],
                        ),
                        ui.HGroup(
                            {"Spacing": 12},
                            [
                                ui.Button({"ID": "PrevChangeBtn", "Text": "7   <<  Prev change"}),
                                ui.Button({"ID": "NextChangeBtn", "Text": "Next change  >>   8"}),
                            ],
                        ),
                        ui.Label({"ID": "ChangeLabel", "Text": " ", "Weight": 0,
                                  "Alignment": {"AlignHCenter": True}}),
                        ui.Button({"ID": "ClearBtn",
                                   "Text": "Clear the change at this frame   (9)"}),
                    ],
                ),
                ui.VGroup(
                    {"Spacing": 4, "Weight": 0},
                    [
                        ui.Button({"ID": "ResetBtn", "Text": "Reset entire scoreboard to 0-0"}),
                        # Deliberately NOT WordWrap, and one Label per line.
                        # A wrapping label reports the height of a single
                        # line to the layout and then draws several, so the
                        # last row of the window ends up clipped top and
                        # bottom and overlapping the button above it. Short
                        # fixed lines measure honestly.
                        ui.Label({"ID": "KeysLine1", "Weight": 0,
                                  "Text": "Shortcuts are digits: Resolve keeps P [ ] , . and the arrows."}),
                        ui.Label({"ID": "KeysLine2", "Weight": 0,
                                  "Text": "Click the panel first - keys go to whichever window has focus."}),
                        ui.HGroup(
                            {"Weight": 0},
                            [
                                # Pushes the button to the right edge. Same
                                # reason as the VGap below - a Label used as
                                # a spacer drags its own minimum size along.
                                ui.HGap(0, 1),
                                # A second way out, so a window whose title
                                # bar X isn't firing can never trap you.
                                ui.Button({"ID": "CloseBtn", "Text": "Close  (Esc)",
                                           "Weight": 0}),
                            ],
                        ),
                    ],
                ),
                # Zero-height stretch, last in the window on purpose.
                #
                # It has to be a VGap, not an empty Label. A Label's minimum
                # height is one line of text whether or not it has any, so
                # using one as a spacer wedges ~18px of blank space in
                # permanently - that was the stubborn gap under the Close
                # button. VGap(0, 1) has a minimum of 0 and only takes space
                # when there's genuinely spare height to take, so at the
                # default size it collapses to nothing.
                ui.VGap(0, 1),
            ],
        ),
    )

    itm = win.GetItems()
    reset_armed = [False]  # list so the nested functions below can mutate it

    def show_error(msg):
        itm["StatusLabel"].Text = "Error: " + msg

    def disarm_reset():
        if reset_armed[0]:
            reset_armed[0] = False
            itm["ResetBtn"].Text = "Reset entire scoreboard to 0-0"

    def update_labels(ctx, note=None):
        # Reads the scoreboard at the frame the CALLER already worked out,
        # and paints the UI from it. It never recomputes the frame itself,
        # so a click's write and the redisplay right after it are
        # guaranteed to be talking about the same frame.
        comp, t = ctx["comp"], ctx["t"]
        try:
            st = read_state(comp, t)
        except Exception as e:
            show_error("Reading scoreboard state failed: %r" % (e,))
            return

        itm["StatusLabel"].Text = (note + "  " if note else "") + \
            "At %s (comp frame %s)" % (ctx["tc"], st["t"])
        itm["Score1Label"].Text = str(st["score1"])
        itm["Score2Label"].Text = str(st["score2"])

        try:
            name1, name2 = read_team_names(comp, t)
            itm["Team1Header"].Text = name1
            itm["Team2Header"].Text = name2
        except Exception:
            name1, name2 = "TEAM 1", "TEAM 2"

        team = 1 if st["state"] in ("T1S1", "T1S2") else 2
        server = 1 if st["state"] in ("T1S1", "T2S1") else 2
        itm["ServingLabel"].Text = "Serving: %s - Server %d" % (
            name1 if team == 1 else name2, server)

    def show_change_position(ctx, frames=None):
        try:
            if frames is None:
                frames = change_frames(ctx)
        except Exception:
            itm["ChangeLabel"].Text = " "
            return
        if not frames:
            itm["ChangeLabel"].Text = "no scored changes on this clip yet"
            return
        t = ctx["t"]
        if t in frames:
            itm["ChangeLabel"].Text = "change %d of %d" % (frames.index(t) + 1, len(frames))
        else:
            after = len([f for f in frames if f < t])
            itm["ChangeLabel"].Text = "between change %d and %d of %d" % (
                after, min(after + 1, len(frames)), len(frames))

    def refresh(note=None):
        """Re-locate the playhead and repaint. Returns ctx or None."""
        ctx, err = locate_scoreboard(resolve)
        if err:
            show_error(err)
            itm["ChangeLabel"].Text = " "
            return None
        update_labels(ctx, note)
        show_change_position(ctx)
        return ctx

    def act(work, failure):
        """Locate, run `work(ctx)`, repaint. `work` returns an error or None."""
        disarm_reset()
        ctx, err = locate_scoreboard(resolve)
        if err:
            show_error(err)
            return
        try:
            problem = work(ctx)
        except Exception as e:
            show_error("%s: %r" % (failure, e))
            return
        if problem:
            itm["StatusLabel"].Text = problem
            return
        refresh()

    def bump_score(which, delta):
        def work(ctx):
            st = read_state(ctx["comp"], ctx["t"])
            current = int(st["score1"] if which == 1 else st["score2"])
            write_score(ctx["comp"], which, max(0, current + delta), ctx["t"])
        act(work, "Updating score failed")

    def add_point(ev=None):
        # The serving team just won the rally: their score goes up, the
        # serve itself doesn't change hands.
        def work(ctx):
            st = read_state(ctx["comp"], ctx["t"])
            team = 1 if st["state"] in ("T1S1", "T1S2") else 2
            current = int(st["score1"] if team == 1 else st["score2"])
            write_score(ctx["comp"], team, current + 1, ctx["t"])
        act(work, "Adding point failed")

    def next_server(ev=None):
        # The serving team just lost the rally (side out): no score change,
        # just walk the state machine (server 1 -> server 2 same team;
        # server 2 -> server 1 other team).
        def work(ctx):
            st = read_state(ctx["comp"], ctx["t"])
            write_serving_state(ctx["comp"], NEXT_STATE[st["state"]], ctx["t"])
        act(work, "Switching server failed")

    def do_clear(ev=None):
        act(lambda ctx: clear_change(ctx["comp"], ctx["t"]),
            "Clearing this frame failed")

    def nudge(frames=0, seconds=0):
        """Step the playhead, clamped to the scoreboard clip."""
        disarm_reset()
        ctx, err = locate_scoreboard(resolve)
        if err:
            show_error(err)
            return
        delta = frames + seconds * int(round(ctx["fps"]))
        target = ctx["frame"] + delta
        clamped = max(ctx["start"], min(ctx["end"], target))
        if clamped == ctx["frame"]:
            itm["StatusLabel"].Text = "That's the %s of the scoreboard clip." % (
                "end" if delta > 0 else "start")
            return
        if not seek(ctx, clamped):
            show_error("Couldn't move the playhead to frame %s." % clamped)
            return
        refresh("Stepped past the end of the clip." if clamped != target else None)

    def go_to_clip(direction):
        disarm_reset()
        ctx, err = locate_scoreboard(resolve)
        if err:
            show_error(err)
            return
        try:
            points = clip_starts(ctx)
        except Exception as e:
            show_error("Couldn't read the timeline's clips: %r" % (e,))
            return
        if not points:
            itm["StatusLabel"].Text = (
                "No other clips under the scoreboard - is the footage on a "
                "track this timeline actually has?")
            return

        if direction > 0:
            later = [f for f in points if f > ctx["frame"]]
            target = later[0] if later else None
            edge = "Already on the last clip under the scoreboard."
        else:
            # Mid-clip, this lands on the start of the clip you're in -
            # same as Resolve's own up-arrow.
            earlier = [f for f in points if f < ctx["frame"]]
            target = earlier[-1] if earlier else None
            edge = "Already at the first clip under the scoreboard."
        if target is None:
            itm["StatusLabel"].Text = edge
            return

        if not seek(ctx, target):
            show_error("Couldn't move the playhead to frame %s. Make sure the "
                       "Edit page is up and the timeline isn't locked." % target)
            return
        refresh("Clip %d of %d." % (points.index(target) + 1, len(points)))

    def go_to_change(direction):
        disarm_reset()
        ctx, err = locate_scoreboard(resolve)
        if err:
            show_error(err)
            return
        try:
            frames = change_frames(ctx)
        except Exception as e:
            show_error("Couldn't work out where the changes are: %r" % (e,))
            return
        if not frames:
            itm["StatusLabel"].Text = (
                "Nothing scored on this clip yet - no changes to step through.")
            show_change_position(ctx, frames)
            return

        if direction > 0:
            later = [f for f in frames if f > ctx["t"]]
            target = later[0] if later else None
            edge = "You're at the last change on this clip."
        else:
            earlier = [f for f in frames if f < ctx["t"]]
            target = earlier[-1] if earlier else None
            edge = "You're at the first change on this clip."
        if target is None:
            itm["StatusLabel"].Text = edge
            show_change_position(ctx, frames)
            return

        if not seek(ctx, target - ctx["left"] + ctx["start"]):
            show_error("Couldn't move the playhead to comp frame %s. Make sure "
                       "the Edit page is up and the timeline isn't locked."
                       % target)
            return
        refresh("Change %d of %d." % (frames.index(target) + 1, len(frames)))

    def do_reset(ev=None):
        if not reset_armed[0]:
            reset_armed[0] = True
            itm["ResetBtn"].Text = "Click again to confirm - wipes the clip"
            return
        disarm_reset()
        act(lambda ctx: reset_scoreboard(ctx["comp"], ctx["t"]), "Reset failed")

    def on_key(ev):
        # Never let an exception escape a key handler - it takes the whole
        # event loop down with it, not just this press.
        try:
            text = str(event_field(ev, "Text", "text") or "")
            try:
                code = int(event_field(ev, "Key", "key") or 0)
            except (TypeError, ValueError):
                code = 0

            # Proof of life. If this line never changes, no key event is
            # reaching the panel at all and the problem is event delivery,
            # not the key map - run "6_Key Test.py" and send the console
            # output. If it DOES change but nothing happens, the event is
            # arriving with fields we're not reading correctly.
            try:
                itm["KeysLine2"].Text = "last key seen:  text=%r  code=%s" % (text, code)
            except Exception:
                pass
            # Shift+, and Shift+. arrive either as "<" / ">" or as "," / "."
            # with a shift modifier set, depending on the build.
            shift = shift_held(ev) or text in ("<", ">")

            if code == KEY_ESCAPE:
                disp.ExitLoop()
                return

            # The digits are the shortcuts that actually work - Resolve
            # doesn't bind them, so they reach this window intact. Checked
            # first and returned from immediately.
            digit = {
                "1": add_point,
                "2": next_server,
                "3": lambda: bump_score(1, +1),
                "4": lambda: go_to_clip(-1),
                "5": lambda: go_to_clip(+1),
                "6": lambda: bump_score(2, +1),
                "7": lambda: go_to_change(-1),
                "8": lambda: go_to_change(+1),
                "9": do_clear,
            }.get(text)
            if digit is not None:
                digit()
                return

            # Everything below is a second name for one of the actions
            # above, kept only because it costs nothing. Resolve swallows
            # most of these before they get here.
            if code in (KEY_LEFT, KEY_RIGHT) or text in (",", ".", "<", ">"):
                back = code == KEY_LEFT or text in (",", "<")
                step = -1 if back else 1
                if shift:
                    nudge(seconds=step)
                else:
                    nudge(frames=step)
                return
            if code == KEY_UP or text == "[":
                go_to_clip(-1)
                return
            if code == KEY_DOWN or text == "]":
                go_to_clip(+1)
                return
            if text == ";":
                go_to_change(-1)
                return
            if text == "'":
                go_to_change(+1)
                return

            letter = text.lower()
            if letter == "p":
                add_point()
            elif letter == "s":
                next_server()
            elif letter == "c":
                do_clear()
            elif letter == "q":
                bump_score(1, -1)
            elif letter == "w":
                bump_score(2, -1)
        except Exception as e:
            try:
                show_error("Key handler: %r" % (e,))
            except Exception:
                pass

    win.On.ScoreboardPanel.Close = lambda ev: disp.ExitLoop()
    win.On.ScoreboardPanel.KeyPress = on_key
    try:
        win.On.PanelRoot.KeyPress = on_key
    except Exception:
        pass
    win.On.CloseBtn.Clicked = lambda ev: disp.ExitLoop()
    win.On.PrevClipBtn.Clicked = lambda ev: go_to_clip(-1)
    win.On.NextClipBtn.Clicked = lambda ev: go_to_clip(+1)
    win.On.T1Plus.Clicked = lambda ev: bump_score(1, +1)
    win.On.T1Minus.Clicked = lambda ev: bump_score(1, -1)
    win.On.T2Plus.Clicked = lambda ev: bump_score(2, +1)
    win.On.T2Minus.Clicked = lambda ev: bump_score(2, -1)
    win.On.PointBtn.Clicked = add_point
    win.On.NextServerBtn.Clicked = next_server
    win.On.PrevChangeBtn.Clicked = lambda ev: go_to_change(-1)
    win.On.NextChangeBtn.Clicked = lambda ev: go_to_change(+1)
    win.On.ClearBtn.Clicked = do_clear
    win.On.ResetBtn.Clicked = do_reset

    win.Show()
    try:
        win.RecalcLayout()
    except Exception:
        pass
    refresh()
    disp.RunLoop()
    win.Hide()


if __name__ == "__main__":
    main()
