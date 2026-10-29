# Spicy John - Android APK + Online Multiplayer

## 1. Make the APK (free, ~30 min, no Android Studio needed)
1. Create a free account on github.com, click **New repository** (name: `spicyjohn`, Private is fine).
2. Upload ALL the files of this folder to it (drag & drop, including the hidden `.github` folder -
   or use `git push`). `buildozer.spec` must be at the top level of the repo.
3. Open the **Actions** tab -> "Build Android APK" -> wait until it turns green
   (first build 25-40 min, later ones are faster).
4. Open the finished run -> **Artifacts** -> download `SpicyJohn-apk`, unzip, copy the `.apk` to your phone.
5. On the phone: open the APK, allow "install from unknown sources". Done.
If the build fails, open the red step, copy the last ~40 lines of the log and send them to me.

## 2. Play online with a friend (no internet needed)
Both players need the game (phone APK or PC) and must be on the SAME network:
* same WiFi / router (LAN), **or**
* one phone turns on its **Hotspot** and the other phone connects to it (works with no data/internet).

Player 1: **PLAY > MULTIPLAYER > ONLINE > HOST A GAME**  (shows "Your room is open")
Player 2: **PLAY > MULTIPLAYER > ONLINE > JOIN A GAME**  -> the room appears by itself, tap it.
If it doesn't appear (some routers block it): tap **TYPE IP** and enter the number shown on the host's screen.

In the lobby each player picks John or Jane. Player 2 taps READY, the host chooses CO-OP or VERSUS + the chapter and taps START.
Both devices run the same fight; only the button presses travel over the network, so it stays smooth on WiFi.
Menu button (top right) = leave the match. Back button on Android = same.

Bluetooth: not used. WiFi/hotspot is much faster and more reliable for a fighting game, and the hotspot
works exactly like Bluetooth (phone to phone, no router, no internet).

## 3. Touch controls
Left stick = move / up / down.  ATK = light, HEAVY, SPEC = special, JUMP (tap twice in the air for a double jump),
DASH, ULT.  Combos like DOWN + HEAVY or UP + ATK: hold the stick direction and tap the button.

## 4. PC
`python full_game.py`  (needs `pip install pygame`).  Online works on PC too (PC <-> PC, PC <-> phone on the same WiFi).
Keyboard in online mode: arrows/WASD, SPACE, Z/X/C, V or SHIFT, R.  `build_exe.bat` makes the Windows .exe.
