#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chronos – ΟΠΤΙΚΟΣ ΣΤΑΘΜΟΣ (MQTT client για PC τάξης)
----------------------------------------------------
Ακούει εντολές από το Home Assistant μέσω MQTT και δείχνει εικόνα/κείμενο σε
πλήρη οθόνη (για οπτικές ειδοποιήσεις, π.χ. εκκένωση).

Topics (όπου <room> = id αίθουσας):
  chronos/<room>/visual/show    payload: όνομα εικόνας (π.χ. evacuation.jpg)
  chronos/<room>/visual/text    payload: κείμενο (εμφανίζεται μεγάλο)
  chronos/<room>/visual/clear   payload: οτιδήποτε  -> μαύρη οθόνη
Δημοσιεύει (retain):
  chronos/<room>/visual/status  -> "online" / "offline" (LWT)

Χειρισμός: ESC για έξοδο/παράθυρο, F για εναλλαγή fullscreen.
Εξαρτήσεις: pip install paho-mqtt pyyaml pillow
(το tkinter συνοδεύει την Python· σε Linux ίσως: sudo apt install python3-tk)
"""
import os
import time
import queue
import threading
import tkinter as tk
import yaml
from PIL import Image, ImageTk
import paho.mqtt.client as mqtt

HERE = os.path.dirname(os.path.abspath(__file__))


def load_config():
    with open(os.path.join(HERE, "station_config.yaml"), "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("broker", {})
    cfg["broker"].setdefault("host", "127.0.0.1")
    cfg["broker"].setdefault("port", 1883)
    cfg.setdefault("room_id", "test")
    cfg.setdefault("images_dir", os.path.join(HERE, "images"))
    return cfg


CFG = load_config()
ROOM = CFG["room_id"]
IMAGES = CFG["images_dir"] if os.path.isabs(CFG["images_dir"]) else os.path.join(HERE, CFG["images_dir"])
BASE = f"chronos/{ROOM}/visual"
STATUS_TOPIC = f"{BASE}/status"

# Ουρά εντολών: το MQTT τρέχει σε νήμα, το tkinter στο κύριο νήμα.
CMD_Q = queue.Queue()


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ---------- GUI (tkinter) ----------
class VisualApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"Chronos Visual – {ROOM}")
        self.root.configure(bg="black")
        self.fullscreen = True
        self.root.attributes("-fullscreen", True)
        self.root.bind("<Escape>", lambda e: self.root.attributes("-fullscreen", False))
        self.root.bind("f", self.toggle_fs)
        self.label = tk.Label(self.root, bg="black")
        self.label.pack(expand=True, fill="both")
        self._imgref = None
        self.root.after(100, self.poll)

    def toggle_fs(self, *_):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)

    def screen_size(self):
        return self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def show_image(self, filename):
        path = os.path.join(IMAGES, filename.strip())
        if not os.path.exists(path):
            self.show_text(f"⚠️ Λείπει εικόνα:\n{filename}")
            return
        sw, sh = self.screen_size()
        img = Image.open(path)
        img.thumbnail((sw, sh))
        self._imgref = ImageTk.PhotoImage(img)
        self.label.configure(image=self._imgref, text="")
        log("🖼️ show:", filename)

    def show_text(self, text):
        self.label.configure(image="", text=text, fg="white", bg="black",
                             font=("DejaVu Sans", 64, "bold"), wraplength=self.screen_size()[0] - 80)
        self._imgref = None
        log("🅰️ text:", text[:40])

    def clear(self):
        self.label.configure(image="", text="", bg="black")
        self._imgref = None
        log("🧹 clear")

    def poll(self):
        try:
            while True:
                kind, payload = CMD_Q.get_nowait()
                if kind == "show":
                    self.show_image(payload)
                elif kind == "text":
                    self.show_text(payload)
                elif kind == "clear":
                    self.clear()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def run(self):
        self.root.mainloop()


# ---------- MQTT ----------
def make_client():
    cid = f"chronos_visual_{ROOM}"
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=cid)


def on_connect(client, userdata, flags, reason_code, properties=None, *args):
    log("Συνδέθηκε (rc=%s). Room=%s" % (reason_code, ROOM))
    client.subscribe(f"{BASE}/#")
    client.publish(STATUS_TOPIC, "online", qos=1, retain=True)


def on_message(client, userdata, msg):
    payload = msg.payload.decode("utf-8", "ignore").strip()
    topic = msg.topic
    log("⇣", topic, "=", payload[:40])
    if topic.endswith("/show"):
        CMD_Q.put(("show", payload))
    elif topic.endswith("/text"):
        CMD_Q.put(("text", payload))
    elif topic.endswith("/clear"):
        CMD_Q.put(("clear", payload))


def mqtt_thread():
    client = make_client()
    b = CFG["broker"]
    if b.get("username"):
        client.username_pw_set(b["username"], b.get("password", ""))
    client.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(b["host"], int(b["port"]), keepalive=30)
    client.loop_forever()


def main():
    threading.Thread(target=mqtt_thread, daemon=True).start()
    VisualApp().run()


if __name__ == "__main__":
    main()
