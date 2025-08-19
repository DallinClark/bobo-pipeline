import nuke
import os
import re
import glob
from datetime import datetime


def get_latest_exr_sequence(render_root):
    """
    Scan render_root for MM-DD-YYYY_V_### folders and, inside the newest one,
    discover all .exr files, extract their frame numbers & padding, and return:
      (pattern, first_frame, last_frame)
    where pattern is something like '/…/images/%04d.exr'
    """
    if not os.path.isdir(render_root):
        nuke.message(f"[Auto Read] Render folder does not exist:\n  {render_root}")
        return None, None, None

    # find latest date/version subfolder
    folder_pattern = re.compile(r"^(\d{2}-\d{2}-\d{2})_V_(\d{3})$")
    candidates = []
    for name in os.listdir(render_root):
        path = os.path.join(render_root, name)
        m = folder_pattern.match(name)
        if m and os.path.isdir(path):
            date_obj = datetime.strptime(m.group(1), "%m-%d-%y").date()
            version = int(m.group(2))
            candidates.append((date_obj, version, path))
    if not candidates:
        nuke.message("[Auto Read] No valid render subfolders found.")
        return None, None, None

    # pick newest, then check for images_dn/images
    _, _, newest = sorted(candidates, key=lambda x: (x[0], x[1]))[-1]
    for sub in ("images_dn", "images"):
        subdir = os.path.join(newest, sub)
        if os.path.isdir(subdir):
            newest = subdir
            break

    # glob all .exr files
    files = glob.glob(os.path.join(newest, "*.exr"))
    if not files:
        nuke.message(f"[Auto Read] No .exr files found in:\n  {newest}")
        return None, None, None

    # extract frame numbers and detect padding
    nums, pad = [], 0
    for f in files:
        fname = os.path.basename(f)
        m = re.match(r"^(.*?)(\d+)\.exr$", fname)
        if not m:
            continue
        nums.append(int(m.group(2)))
        pad = max(pad, len(m.group(2)))

    if not nums:
        nuke.message(f"[Auto Read] Couldn't parse frame numbers in:\n  {newest}")
        return None, None, None

    first_frame = min(nums)
    last_frame = max(nums)
    pattern = os.path.join(newest, "%%0%dd.exr" % pad)

    return pattern, first_frame, last_frame


def make_read_node(render_subdir="render", node_name="EXR_read"):
    """
    Create a Read node pointing at the full sequence (from first_frame to last_frame).
    """
    script_path = nuke.root()["name"].value()
    if not script_path or script_path == "Root":
        nuke.message("Open your shot before using Auto Read.")
        return None

    shot_dir = os.path.dirname(os.path.dirname(script_path))
    render_dir = os.path.join(shot_dir, render_subdir)

    seq_pattern, first, last = get_latest_exr_sequence(render_dir)
    if not seq_pattern:
        return None
    for n in nuke.allNodes("Read"):
        if n.name() == node_name:
            nuke.delete(n)
    read = nuke.nodes.Read(name=node_name, file=seq_pattern, on_error="black")
    # set both the sequence's native range and the playback range
    read["origfirst"].setValue(first)
    read["origlast"].setValue(last)
    read["first"].setValue(first)
    read["last"].setValue(last)

    nuke.root()["first_frame"].setValue(first)
    nuke.root()["last_frame"].setValue(last)

    return read


def auto_read_latest_fx_exr():
    read_node = make_read_node("FX/render", node_name="Bobo_FX_read")
    if not read_node:
        return
    try:
        viewer = nuke.activeViewer().node()
        nuke.zoom(1, [viewer["xpos"].value(), viewer["ypos"].value()])
    except Exception as e:
        nuke.tprint(f"[Auto Read] Viewer zoom error: {e}")


def auto_read_latest_exr():
    """
    Callback: build the Read node and zoom the Viewer.
    """
    read_node = make_read_node()
    if not read_node:
        return
    try:
        viewer = nuke.activeViewer().node()
        nuke.zoom(1, [viewer["xpos"].value(), viewer["ypos"].value()])
    except Exception as e:
        nuke.tprint(f"[Auto Read] Viewer zoom error: {e}")


def main():
    """
    Register the menu command and run it immediately.
    """
    nuke.menu("Nuke").addCommand(
        "Custom/Auto Read Latest EXR", auto_read_latest_exr, "ctrl+shift+r"
    )
    # immediately invoke to surface any errors at load time
    auto_read_latest_exr()


# auto-register on module load
try:
    main()
    nuke.tprint("[Auto Read] Module loaded and command registered.")
except Exception as e:
    nuke.tprint(f"[Auto Read] Failed to initialize: {e}")
