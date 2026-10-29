[app]
title = Spicy John
package.name = spicyjohn
package.domain = com.spicyjohn
source.dir = .
source.include_exts = py,png,jpg,ogg,wav,json,ttf
source.include_patterns = assets/*,assets/**/*
source.exclude_dirs = .github,bin,.buildozer,__pycache__
version = 1.1
icon.filename = %(source.dir)s/assets/images/icon.png

# pygame = python-for-android's own SDL2 pygame recipe (don't pin a version, the pinned 2.5.1 doesn't exist there)
requirements = python3,pygame,pyjnius
p4a.branch = v2023.09.16
orientation = landscape
fullscreen = 1

# network permissions are what make WiFi / hotspot multiplayer work
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WAKE_LOCK
android.wakelock = True
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
