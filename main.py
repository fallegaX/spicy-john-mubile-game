# Entry point for the Android build.
# sdl2 bootstrap expects main.py; keep full_game as the real game.
import os, sys, traceback, time

def _logdir():
    # Prefer the app's writable home (internal storage); fall back to the script dir.
    for d in (os.path.expanduser("~"), os.path.dirname(os.path.abspath(__file__))):
        if d and os.path.isdir(d):
            try:
                p = os.path.join(d, "spicyjohn_crash.log")
                with open(p, "a") as f:
                    f.write("--- session %s ---\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
                return p
            except Exception:
                continue
    return None

LOG = _logdir()

def _log(msg):
    # goes to logcat automatically under the "python" tag
    print(msg, flush=True)
    if LOG:
        try:
            with open(LOG, "a") as f:
                f.write(msg + "\n")
        except Exception:
            pass

try:
    _log("spicyjohn: starting full_game...")
    from full_game import main
    main()
    _log("spicyjohn: main() returned normally")
except Exception:
    tb = traceback.format_exc()
    _log("spicyjohn CRASH:\n" + tb)
    sys.__stderr__.write(tb + "\n")
    sys.__stderr__.flush()
    # Keep the process alive so the user sees it crashed (not a silent exit)
    # and so "adb logcat" has time to capture the traceback.
    time.sleep(15)
