#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chronos – ΗΧΗΤΙΚΟΣ ΣΤΑΘΜΟΣ (MQTT client για PC τάξης)
-----------------------------------------------------
Ακούει εντολές από το Home Assistant μέσω MQTT και παίζει αρχεία ήχου.

Topics (όπου <room> = το id της αίθουσας, π.χ. a_gymnasiou):
  chronos/<room>/audio/play    payload: όνομα αρχείου (π.χ. bell_break.mp3)  -> one-shot
  chronos/<room>/audio/music   payload: όνομα αρχείου  -> αναπαραγωγή σε επανάληψη (loop)
  chronos/<room>/audio/stop    payload: οτιδήποτε      -> διακοπή
  chronos/<room>/audio/volume  payload: 0-100          -> ένταση

Δημοσιεύει (retain):
  chronos/<room>/audio/status  -> "online" / "offline" (LWT)

Ρυθμίσεις: station_config.yaml (δίπλα σε αυτό το αρχείο).
Εξαρτήσεις: pip install paho-mqtt pyyaml pygame
"""
import os
import sys
import time
import yaml
import pygame
import paho.mqtt.client as mqtt

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config():
    path = os.path.join(HERE, "station_config.yaml")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("broker", {})
    cfg["broker"].setdefault("host", "127.0.0.1")
    cfg["broker"].setdefault("port", 1883)
    cfg.setdefault("room_id", "test")
    cfg.setdefault("media_dir", os.path.join(HERE, "sounds"))
    return cfg


CFG = load_config()
ROOM = CFG["room_id"]
SOUNDS = CFG["media_dir"] if os.path.isabs(CFG["media_dir"]) else os.path.join(HERE, CFG["media_dir"])
BASE = f"chronos/{ROOM}/audio"
STATUS_TOPIC = f"{BASE}/status"


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ---------- Ήχος (pygame mixer) ----------
pygame.mixer.init()
log("Mixer OK:", pygame.mixer.get_init())


def resolve(filename):
    """Βρες το αρχείο μέσα στον φάκελο ήχων."""
    p = os.path.join(SOUNDS, filename.strip())
    return p if os.path.exists(p) else None


def play_oneshot(filename):
    p = resolve(filename)
    if not p:
        log("⚠️ Δεν βρέθηκε αρχείο:", filename, "στο", SOUNDS)
        return
    try:
        snd = pygame.mixer.Sound(p)
        snd.play()
        log("🔔 play:", filename)
    except Exception as e:
        log("Σφάλμα play:", e)


def play_music(filename):
    p = resolve(filename)
    if not p:
        log("⚠️ Δεν βρέθηκε αρχείο:", filename, "στο", SOUNDS)
        return
    try:
        pygame.mixer.music.load(p)
        pygame.mixer.music.play(loops=-1)  # επανάληψη
        log("🎵 music (loop):", filename)
    except Exception as e:
        log("Σφάλμα music:", e)


def stop_all():
    pygame.mixer.music.stop()
    pygame.mixer.stop()
    log("⏹️ stop")


def set_volume(payload):
    try:
        v = max(0, min(100, int(float(payload)))) / 100.0
        pygame.mixer.music.set_volume(v)
        log("🔊 volume:", int(v * 100))
    except Exception as e:
        log("Σφάλμα volume:", e)


# ---------- MQTT ----------
def make_client():
    cid = f"chronos_audio_{ROOM}"
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)  # paho 2.x
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=cid)  # paho 1.x


def on_connect(client, userdata, flags, reason_code, properties=None, *args):
    log("Συνδέθηκε στον broker (rc=%s). Room=%s" % (reason_code, ROOM))
    client.subscribe(f"{BASE}/#")
    client.publish(STATUS_TOPIC, "online", qos=1, retain=True)


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", "ignore").strip()
    topic = msg.topic
    log("⇣", topic, "=", payload)
    if topic.endswith("/play"):
        play_oneshot(payload)
    elif topic.endswith("/music"):
        play_music(payload)
    elif topic.endswith("/stop"):
        stop_all()
    elif topic.endswith("/volume"):
        set_volume(payload)
    # το /status το αγνοούμε (το γράφουμε εμείς)


def main():
    client = make_client()
    b = CFG["broker"]
    if b.get("username"):
        client.username_pw_set(b["username"], b.get("password", ""))
    client.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)
    client.on_connect = on_connect
    client.on_message = on_message
    log("Σύνδεση σε %s:%s …" % (b["host"], b["port"]))
    client.connect(b["host"], int(b["port"]), keepalive=30)
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        log("Τερματισμός…")
        client.publish(STATUS_TOPIC, "offline", qos=1, retain=True)
        time.sleep(0.3)
        client.disconnect()


if __name__ == "__main__":
    main()
