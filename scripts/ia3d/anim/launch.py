"""Run one of the Blender scripts from plain Python (bake_perf.py, export_test.py): the right input
.blend, the temp folder on D:, a non-zero exit code when the script fails.

    run_blender(FACE3, script, ["bake", "--module", ...])     # blender -b face3 --python script -- args

The input .blend is only read: the scripts that write do it to an --out path of their own.
"""
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
WORK = os.path.join(REPO, "work", "ia3d")
FACE3 = os.path.join(WORK, "morfi_ia_face3.blend")      # rig + face + fixed wrists: where performances are baked
LOOK7 = os.path.join(WORK, "morfi_ia_look7.blend")      # the final look (materials): previews and the web export
BLENDER = os.environ.get("MORFI_BLENDER", "D:/tools/blender-4.5/blender.exe")
DEFAULT_TMP = "D:/tmp/morfi/blender_tmp"
SLOTS_DIR = "D:/tmp/morfi/blender_slots"                # machine-wide: several workers share one PC and one GPU
SLOTS = int(os.environ.get("MORFI_BLENDER_SLOTS", "4"))


def in_blender():
    try:
        import bpy  # noqa: F401
        return True
    except ImportError:
        return False


def tmp_env():
    """Environment for a child process: temp files on D: (never C:), no user site-packages."""
    env = dict(os.environ)
    tmp = env.get("TEMP", "")
    if not tmp.upper().startswith("D:"):
        tmp = DEFAULT_TMP.replace("/", "\\")
    os.makedirs(tmp, exist_ok=True)
    env.update(TEMP=tmp, TMP=tmp, PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    return env


def _alive(pid):
    """Is a process still running? (Windows: never os.kill, it would terminate it.)"""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    h = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ctypes.get_last_error() == 5            # access denied: it exists
    code = ctypes.c_ulong()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return bool(ok) and code.value == 259              # STILL_ACTIVE


def acquire_slot():
    """Wait for one of the SLOTS machine-wide Blender slots (a lock file holding this process' pid);
    a slot whose owner died is taken over. Returns the lock path (release_slot frees it)."""
    os.makedirs(SLOTS_DIR, exist_ok=True)
    waited = False
    while True:
        for i in range(SLOTS):
            path = os.path.join(SLOTS_DIR, f"slot{i}.lock")
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    with open(path, encoding="ascii") as fh:
                        pid = int(fh.read().strip() or 0)
                except (OSError, ValueError):
                    pid = 0                            # being written right now: busy
                if pid and not _alive(pid):
                    try:
                        os.remove(path)                # stale: its owner is gone
                    except OSError:
                        pass
                continue
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.close(fd)
            if waited:
                print("Blender slot free: starting", flush=True)
            return path
        if not waited:
            print(f"waiting for a free Blender slot (all {SLOTS} busy: other workers are baking/rendering)", flush=True)
            waited = True
        time.sleep(5)


def release_slot(path):
    try:
        os.remove(path)
    except OSError:
        pass


NOISE = re.compile(r"^(Fra:|Saved: |Time: |Blender \d|Blender quit|Read blend|\d\d:\d\d:\d\d \| (WARNING|INFO))")   # per-frame / glTF chatter


def run_blender(blend, script, args, quiet=True):
    """blender -b <blend> --python <script> -- <args>; returns the exit code. quiet drops Blender's
    per-frame render lines (a preview of 2 minutes prints thousands of them)."""
    if not os.path.exists(BLENDER):
        sys.exit(f"ERROR: Blender not found at {BLENDER} (set MORFI_BLENDER)")
    if not os.path.exists(blend):
        sys.exit(f"ERROR: input .blend not found: {blend}")
    cmd = [BLENDER, "-b", os.path.abspath(blend), "--python-exit-code", "1", "--python", os.path.abspath(script),
           "--", *[str(x) for x in args]]
    slot = acquire_slot()
    try:
        proc = subprocess.Popen(cmd, env=tmp_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", bufsize=1)
        for line in proc.stdout:
            if quiet and (NOISE.match(line) or not line.strip()):
                continue
            sys.stdout.write(line)
            sys.stdout.flush()
        return proc.wait()
    finally:
        release_slot(slot)


def run_node(script, args, cwd):
    node = os.environ.get("MORFI_NODE", "node")
    return subprocess.run([node, script, *[str(x) for x in args]], cwd=cwd, env=tmp_env()).returncode


def action_id(action):
    """Test_Opus -> opus; the web files and the audio are named by this id."""
    if not (action.startswith("Test_") and action[5:].isalnum()):
        sys.exit(f"ERROR: the action must be named Test_<Id> (Test_Opus, Test_Haiku2...), got {action!r}")
    return action[5:].lower()


def action_of(test_id):
    return "Test_" + test_id[:1].upper() + test_id[1:].lower()
