#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real Panorama Converter for Minecraft
Made by real_eldho

Requirements:
    python -m pip install pillow numpy

Run:
    python real_panorama_converter.py
"""

import json
import math
import os
import queue
import threading
import traceback
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

APP_NAME = "Real Panorama Converter"
APP_VERSION = "1.1.0"

# Exact release targets. Do not silently use a nearby version's metadata.
# Resource-pack format references:
# 1.8 = 1; 1.20/1.20.1 = 15; 1.21.11 = 75.0; 26.3 = 97.1.
MINECRAFT_TARGETS = {
    "Minecraft 26.3": {"kind": "modern", "min_format": [97, 1], "max_format": [97, 1]},
    "Minecraft 26.2": {"kind": "modern", "min_format": [88, 0], "max_format": [88, 0]},
    "Minecraft 26.1": {"kind": "modern", "min_format": [84, 0], "max_format": [84, 0]},
    "Minecraft 1.21": {"kind": "legacy", "pack_format": 34},
    "Minecraft 1.20": {"kind": "legacy", "pack_format": 15},
    "Minecraft 1.19": {"kind": "legacy", "pack_format": 9},
    "Minecraft 1.18": {"kind": "legacy", "pack_format": 8},
    "Minecraft 1.17": {"kind": "legacy", "pack_format": 7},
    "Minecraft 1.16": {"kind": "legacy", "pack_format": 5},
    "Minecraft 1.15": {"kind": "legacy", "pack_format": 5},
    "Minecraft 1.14": {"kind": "legacy", "pack_format": 4},
    "Minecraft 1.13": {"kind": "legacy", "pack_format": 4},
    "Minecraft 1.12": {"kind": "legacy", "pack_format": 3},
    "Minecraft 1.11": {"kind": "legacy", "pack_format": 3},
}

FACE_ORDER = [
    "panorama_0", "panorama_1", "panorama_2",
    "panorama_3", "panorama_4", "panorama_5",
]
FACE_LABELS = ["Front", "Right", "Back", "Left", "Top", "Bottom"]
FACE_VECTORS = {
    "panorama_0": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
    "panorama_1": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "panorama_2": ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
    "panorama_3": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "panorama_4": ((0, 1, 0), (1, 0, 0), (0, 0, -1)),
    "panorama_5": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
}
TEXTURE_DIR = Path("assets") / "minecraft" / "textures" / "gui" / "title" / "background"
ICON_SIZE = (128, 128)
MAX_FACE_SIZE = 4096


def generate_face(arr, face_key, size):
    """Project one square cubemap face from an RGB equirectangular image."""
    forward, right, up = [np.asarray(v, dtype=np.float64) for v in FACE_VECTORS[face_key]]
    h, w = arr.shape[:2]
    u_grid, v_grid = np.meshgrid(np.arange(size), np.arange(size))
    u = 2.0 * (u_grid + 0.5) / size - 1.0
    v = 1.0 - 2.0 * (v_grid + 0.5) / size

    dx = forward[0] + u * right[0] + v * up[0]
    dy = forward[1] + u * right[1] + v * up[1]
    dz = forward[2] + u * right[2] + v * up[2]
    norm = np.sqrt(dx * dx + dy * dy + dz * dz)
    dx, dy, dz = dx / norm, dy / norm, dz / norm

    latitude = np.arcsin(np.clip(dy, -1.0, 1.0))
    longitude = np.arctan2(dx, dz)
    x = (longitude + math.pi) / (2.0 * math.pi) * w
    y = (math.pi / 2.0 - latitude) / math.pi * h

    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]

    x0w, x1w = np.mod(x0, w), np.mod(x0 + 1, w)
    y0c, y1c = np.clip(y0, 0, h - 1), np.clip(y0 + 1, 0, h - 1)

    c00 = arr[y0c, x0w].astype(np.float64)
    c10 = arr[y0c, x1w].astype(np.float64)
    c01 = arr[y1c, x0w].astype(np.float64)
    c11 = arr[y1c, x1w].astype(np.float64)
    top = c00 * (1.0 - fx) + c10 * fx
    bottom = c01 * (1.0 - fx) + c11 * fx
    return np.clip(top * (1.0 - fy) + bottom * fy, 0, 255).astype(np.uint8)


def recenter(arr, center_x, center_y):
    h, w = arr.shape[:2]
    shifted = np.roll(arr, (w // 2) - int(round(center_x)), axis=1)
    if center_y is not None:
        shifted = np.roll(shifted, (h // 2) - int(round(center_y)), axis=0)
    return shifted


def make_default_icon():
    """Create a simple, valid 128x128 PNG when the user does not supply an icon."""
    image = Image.new("RGB", ICON_SIZE, (22, 27, 39))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((10, 10, 118, 118), radius=18, fill=(35, 48, 70), outline=(67, 190, 132), width=4)
    draw.ellipse((31, 31, 97, 97), fill=(67, 190, 132))
    draw.ellipse((42, 42, 86, 86), fill=(22, 27, 39))
    draw.line((64, 20, 64, 108), fill=(230, 244, 238), width=3)
    draw.line((20, 64, 108, 64), fill=(230, 244, 238), width=3)
    return image


def build_pack_metadata(version_name, pack_description):
    target = MINECRAFT_TARGETS[version_name]
    pack = {"description": pack_description}
    if target["kind"] == "legacy":
        pack["pack_format"] = target["pack_format"]
    else:
        pack["min_format"] = target["min_format"]
        pack["max_format"] = target["max_format"]
    return {"pack": pack}


class PanoramaConverterApp:
    BG = "#10141d"
    PANEL = "#192231"
    PANEL_ALT = "#202c3d"
    FG = "#edf2f7"
    MUTED = "#a6b3c5"
    ACCENT = "#42c98a"
    BORDER = "#2d3b4f"

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} · {APP_VERSION}")
        self.root.geometry("1050x700")
        self.root.minsize(900, 620)
        self.root.configure(bg=self.BG)

        self.image_path = None
        self.full_array = None
        self.preview_image = None
        self.preview_tk = None
        self.pack_icon_path = None
        self.icon_preview_tk = None
        self.center_x = None
        self.center_y = None
        self.canvas_box = None
        self.events = queue.Queue()
        self._light_theme = False
        self._palette_dark = {
            "BG": "#10141d", "PANEL": "#192231", "PANEL_ALT": "#202c3d",
            "FG": "#edf2f7", "MUTED": "#a6b3c5", "ACCENT": "#42c98a",
            "BORDER": "#2d3b4f", "CANVAS": "#080b10"
        }
        self._palette_light = {
            "BG": "#edf1f6", "PANEL": "#ffffff", "PANEL_ALT": "#e7edf4",
            "FG": "#172033", "MUTED": "#5c687a", "ACCENT": "#168653",
            "BORDER": "#cbd5e1", "CANVAS": "#dce4ee"
        }

        self.var_version = tk.StringVar(value="Minecraft 26.3")
        self.var_pack_name = tk.StringVar(value="My Panorama")
        self.var_pack_description = tk.StringVar(value="Custom Minecraft title screen panorama")
        self.var_resolution = tk.StringVar(value="1024")
        self.var_output = tk.StringVar(value="")
        self.var_input_info = tk.StringVar(value="No image selected")
        self.var_icon_info = tk.StringVar(value="Default icon will be created")
        self.var_status = tk.StringVar(value="Load a 360° equirectangular image to begin.")
        self.var_theme = tk.BooleanVar(value=True)

        self._build_ui()
        self.root.after(100, self._poll_events)

    def _label(self, parent, text, **kwargs):
        return tk.Label(parent, text=text, bg=self.PANEL, fg=self.FG,
                        font=("Segoe UI", 10), **kwargs)

    def _button(self, parent, text, command, primary=False):
        return tk.Button(
            parent, text=text, command=command, relief="flat", bd=0,
            bg=self.ACCENT if primary else self.PANEL_ALT,
            fg="#08130e" if primary else self.FG,
            activebackground="#35b77a" if primary else "#2b3b50",
            activeforeground="#ffffff", font=("Segoe UI", 10, "bold"),
            padx=12, pady=8, cursor="hand2"
        )

    def _section(self, parent, title):
        box = tk.Frame(parent, bg=self.PANEL, highlightbackground=self.BORDER, highlightthickness=1)
        tk.Label(box, text=title, bg=self.PANEL, fg=self.ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 7))
        return box

    def _build_ui(self):
        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=18, pady=(14, 10))
        tk.Label(header, text="REAL PANORAMA CONVERTER", bg=self.BG, fg=self.FG,
                 font=("Segoe UI", 17, "bold")).pack(side="left")
        tk.Label(header, text="Made by real_eldho", bg=self.BG, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(side="right", padx=(10, 0))
        self._button(header, "☼ Theme", self.toggle_theme).pack(side="right")

        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=18, pady=5)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=self.BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = tk.Frame(body, bg=self.BG)
        right.grid(row=0, column=1, sticky="nsew")

        image_box = self._section(left, "1 · 360° SOURCE IMAGE")
        image_box.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(image_box, bg="#080b10", highlightthickness=0, height=390)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.canvas.bind("<Configure>", lambda _e: self.draw_main())
        self.canvas.bind("<Button-1>", self.canvas_click)
        self.canvas.bind("<B1-Motion>", self.canvas_click)
        bottom = tk.Frame(image_box, bg=self.PANEL)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self._button(bottom, "Choose 360° Image", self.load_image, True).pack(side="left")
        tk.Label(bottom, textvariable=self.var_input_info, bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=10)
        tk.Label(image_box, text="Recommended: 4096 × 2048 px (2:1 equirectangular)",
                 bg=self.PANEL, fg=self.MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(0, 10))

        ver = self._section(right, "2 · MINECRAFT TARGET")
        ver.pack(fill="x", pady=(0, 9))
        self._label(ver, "Java Edition version").pack(anchor="w", padx=12)
        self.version_combo = ttk.Combobox(ver, textvariable=self.var_version,
            values=list(MINECRAFT_TARGETS.keys()), state="readonly")
        self.version_combo.pack(fill="x", padx=12, pady=(4, 10))
        self.version_combo.configure(font=("Segoe UI", 10))

        settings = self._section(right, "3 · RESOURCE PACK DETAILS")
        settings.pack(fill="x", pady=(0, 9))
        self._label(settings, "Pack name").pack(anchor="w", padx=12)
        tk.Entry(settings, textvariable=self.var_pack_name, bg=self.PANEL_ALT, fg=self.FG,
                 insertbackground=self.FG, relief="flat").pack(fill="x", padx=12, pady=(3, 8), ipady=6)
        self._label(settings, "Description").pack(anchor="w", padx=12)
        tk.Entry(settings, textvariable=self.var_pack_description, bg=self.PANEL_ALT, fg=self.FG,
                 insertbackground=self.FG, relief="flat").pack(fill="x", padx=12, pady=(3, 10), ipady=6)

        icon = self._section(right, "4 · RESOURCE PACK ICON")
        icon.pack(fill="x", pady=(0, 9))
        row = tk.Frame(icon, bg=self.PANEL)
        row.pack(fill="x", padx=12, pady=(0, 10))
        self.icon_preview = tk.Label(row, text="128×128", width=10, height=4,
                                     bg=self.PANEL_ALT, fg=self.MUTED)
        self.icon_preview.pack(side="left")
        icon_controls = tk.Frame(row, bg=self.PANEL)
        icon_controls.pack(side="left", fill="x", expand=True, padx=10)
        self._button(icon_controls, "Choose pack.png", self.choose_icon).pack(anchor="w")
        tk.Label(icon_controls, textvariable=self.var_icon_info, bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 8), wraplength=190, justify="left").pack(anchor="w", pady=(5, 0))

        size_row = tk.Frame(settings, bg=self.PANEL)
        size_row.pack(fill="x", padx=12, pady=(0, 10))
        self._label(size_row, "Panorama face size").pack(side="left")
        tk.Entry(size_row, textvariable=self.var_resolution, width=8, bg=self.PANEL_ALT, fg=self.FG,
                 insertbackground=self.FG, relief="flat").pack(side="left", padx=(10, 6), ipady=5)
        tk.Label(size_row, text="px square · 256–4096", bg=self.PANEL,
                 fg=self.MUTED, font=("Segoe UI", 8)).pack(side="left")

        actions = tk.Frame(right, bg=self.BG)
        actions.pack(fill="x", pady=(1, 0))
        self._button(actions, "Tutorial / Help", self.show_tutorial).pack(side="left")
        self.generate_button = self._button(actions, "Create Resource Pack", self.start_generation, True)
        self.generate_button.pack(side="right")

        footer = tk.Frame(self.root, bg=self.PANEL, height=38)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        self.progress = ttk.Progressbar(footer, maximum=6, mode="determinate")
        self.progress.pack(side="right", padx=12, pady=10, fill="x", expand=True)
        tk.Label(footer, textvariable=self.var_status, bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9), anchor="w").pack(side="left", padx=12)

        style = ttk.Style()
        try:
            style.theme_use("clam")
            style.configure("TCombobox", fieldbackground=self.PANEL_ALT, background=self.PANEL_ALT,
                            foreground=self.FG, arrowcolor=self.FG)
            style.configure("Horizontal.TProgressbar", troughcolor=self.PANEL_ALT,
                            background=self.ACCENT, bordercolor=self.PANEL)
        except tk.TclError:
            pass

    def toggle_theme(self):
        old = {key: getattr(self, key) for key in self._palette_dark}
        self._light_theme = not self._light_theme
        palette = self._palette_light if self._light_theme else self._palette_dark
        for key, value in palette.items():
            setattr(self, key, value)
        mapping = {old[key]: palette[key] for key in palette}
        mapping["#080b10"] = palette["CANVAS"]

        def recolor(widget):
            try:
                for option in ("bg", "background", "fg", "foreground",
                               "activebackground", "activeforeground",
                               "insertbackground", "highlightbackground"):
                    try:
                        current = widget.cget(option)
                        if current in mapping:
                            widget.configure(**{option: mapping[current]})
                    except (tk.TclError, TypeError):
                        pass
            except tk.TclError:
                pass
            for child in widget.winfo_children():
                recolor(child)

        self.root.configure(bg=self.BG)
        recolor(self.root)
        try:
            style = ttk.Style()
            style.configure("TCombobox", fieldbackground=self.PANEL_ALT,
                            background=self.PANEL_ALT, foreground=self.FG,
                            arrowcolor=self.FG)
            style.configure("Horizontal.TProgressbar", troughcolor=self.PANEL_ALT,
                            background=self.ACCENT, bordercolor=self.PANEL)
        except tk.TclError:
            pass
        self.draw_main()

    def load_image(self):
        path = filedialog.askopenfilename(
            title="Select a 360° equirectangular image",
            filetypes=[("Supported images", "*.jpg *.jpeg *.png *.webp *.tif *.tiff *.bmp"),
                       ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with Image.open(path) as source:
                image = source.convert("RGB")
            if image.width < 2 or image.height < 2:
                raise ValueError("The image dimensions are too small.")
            ratio = image.width / image.height
            if abs(ratio - 2.0) > 0.03:
                proceed = messagebox.askyesno(
                    "Image is not 2:1",
                    f"This image is {image.width}×{image.height} (ratio {ratio:.3f}:1).\n\n"
                    "A full 360° equirectangular panorama should be 2:1.\n"
                    "Continue anyway?"
                )
                if not proceed:
                    return
            self.image_path = path
            self.full_array = np.asarray(image, dtype=np.uint8)
            self.center_x = image.width / 2
            self.center_y = image.height / 2
            self.var_input_info.set(f"{image.width} × {image.height} px")
            max_preview_w = 1800
            if image.width > max_preview_w:
                new_h = max(1, round(image.height * max_preview_w / image.width))
                self.preview_image = image.resize((max_preview_w, new_h), Image.Resampling.LANCZOS)
            else:
                self.preview_image = image
            self.draw_main()
            self.var_status.set("Image loaded. Click the preview to adjust the panorama center.")
        except Exception as exc:
            messagebox.showerror("Could not load image", str(exc))

    def draw_main(self):
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        cw, ch = canvas.winfo_width(), canvas.winfo_height()
        if cw < 5 or ch < 5:
            return
        if self.preview_image is None:
            canvas.create_text(cw // 2, ch // 2, text="Your 360° panorama preview appears here",
                               fill=self.MUTED, font=("Segoe UI", 11))
            return
        iw, ih = self.preview_image.size
        scale = min((cw - 16) / iw, (ch - 16) / ih)
        dw, dh = max(1, int(iw * scale)), max(1, int(ih * scale))
        x0, y0 = (cw - dw) // 2, (ch - dh) // 2
        resized = self.preview_image.resize((dw, dh), Image.Resampling.LANCZOS)
        self.preview_tk = ImageTk.PhotoImage(resized)
        canvas.create_image(x0, y0, image=self.preview_tk, anchor="nw")
        self.canvas_box = (x0, y0, x0 + dw, y0 + dh)
        if self.center_x is not None:
            fx = self.center_x / self.full_array.shape[1]
            fy = self.center_y / self.full_array.shape[0]
            px, py = x0 + fx * dw, y0 + fy * dh
            canvas.create_line(px, y0, px, y0 + dh, fill="#ff5b5b", dash=(4, 4), width=2)
            canvas.create_line(x0, py, x0 + dw, py, fill="#ff5b5b", dash=(4, 4), width=2)
            canvas.create_oval(px - 5, py - 5, px + 5, py + 5, outline="#ff5b5b", width=2)

    def canvas_click(self, event):
        if self.full_array is None or self.canvas_box is None:
            return
        x0, y0, x1, y1 = self.canvas_box
        if not (x0 <= event.x <= x1 and y0 <= event.y <= y1):
            return
        fx = min(1.0, max(0.0, (event.x - x0) / (x1 - x0)))
        fy = min(1.0, max(0.0, (event.y - y0) / (y1 - y0)))
        self.center_x = fx * self.full_array.shape[1]
        self.center_y = fy * self.full_array.shape[0]
        self.draw_main()

    def choose_icon(self):
        path = filedialog.askopenfilename(
            title="Choose a resource pack icon",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            # Strict validation: no conversion or resizing of an invalid custom icon.
            with Image.open(path) as im:
                if im.format != "PNG":
                    raise ValueError("The icon file must be a real PNG image.")
                if im.size != ICON_SIZE:
                    raise ValueError(
                        f"The icon must be exactly 128×128 pixels. This file is {im.width}×{im.height}."
                    )
                im.verify()
            self.pack_icon_path = path
            with Image.open(path) as im:
                preview = im.convert("RGBA")
                preview.thumbnail((64, 64), Image.Resampling.LANCZOS)
            self.icon_preview_tk = ImageTk.PhotoImage(preview)
            self.icon_preview.configure(image=self.icon_preview_tk, text="")
            self.var_icon_info.set("Valid PNG · 128×128")
        except Exception as exc:
            messagebox.showerror("Invalid pack icon", str(exc))
            self.pack_icon_path = None
            self.var_icon_info.set("Default icon will be created")

    def choose_output(self):
        folder = filedialog.askdirectory(title="Choose where to save the resource pack")
        if folder:
            self.var_output.set(folder)

    def show_tutorial(self):
        win = tk.Toplevel(self.root)
        win.title("Real Panorama Converter — Tutorial")
        win.geometry("700x620")
        win.configure(bg=self.BG)
        win.transient(self.root)
        text = tk.Text(win, wrap="word", bg=self.PANEL, fg=self.FG, insertbackground=self.FG,
                       relief="flat", padx=18, pady=16, font=("Segoe UI", 10))
        text.pack(fill="both", expand=True, padx=12, pady=12)
        tutorial = """REAL PANORAMA CONVERTER — FULL TUTORIAL

1. Prepare your 360° image
• Use a full 360° equirectangular panorama, not an ordinary perspective photo.
• The correct aspect ratio is 2:1 (width is twice the height).
• Recommended resolution: 4096 × 2048 px.
• Higher-resolution source images are fine, but very large files need more RAM.
• Supported source formats: JPG/JPEG, PNG, WEBP, TIF/TIFF and BMP.
• If the image is not 2:1, the app warns you. Results may be distorted or incomplete.

2. Choose the Minecraft version
• Select one of the exact target labels shown in the version list:
  Minecraft 26.3, 26.2, 26.1, 1.21, 1.20, 1.19, 1.18, 1.17,
  1.16, 1.15, 1.14, 1.13, 1.12 or 1.11.
• The app writes the pack metadata configured for that target.
• These are Java Edition targets. This app does not launch Minecraft or
  independently verify compatibility in-game. Some major-version labels
  cover multiple minor releases; verify the exact game release before publishing.

3. Resource pack icon (pack.png)
• Optional. If you do not select one, the app creates a default icon.
• A custom icon must be a PNG file exactly 128 × 128 pixels.
• Invalid format or dimensions are rejected; the app will not silently resize it.

4. Choose panorama face size
• Use a square size. 1024 × 1024 is a good starting point.
• All six generated panorama images use the same square dimensions.
• Larger images increase file size and memory use.

5. Generate and install
• Click “Create Resource Pack” and choose the destination folder in the dialog.
• The app creates a complete resource pack folder and a ZIP archive.
• In Minecraft Java Edition, open Options → Resource Packs → Open Pack Folder.
• Copy the generated ZIP into that folder (or copy the generated pack folder there).
• Return to Minecraft and enable the pack. If it does not appear, check that the ZIP has
  pack.mcmeta at its root and that you selected the same Minecraft version in this app.

IMPORTANT
This tool creates the panorama textures and version metadata. It does not launch Minecraft
or automatically test the pack inside the game. Always select the matching game version.
"""
        text.insert("1.0", tutorial)
        text.configure(state="disabled")

    def _validate(self):
        if self.full_array is None:
            raise ValueError("Load a 360° panorama image first.")
        version = self.var_version.get()
        if version not in MINECRAFT_TARGETS:
            raise ValueError("Select one of the supported Minecraft versions.")
        pack_name = self.var_pack_name.get().strip()
        if not pack_name:
            raise ValueError("Enter a resource pack name.")
        description = self.var_pack_description.get().strip() or pack_name
        try:
            size = int(self.var_resolution.get().strip())
        except ValueError:
            raise ValueError("Panorama face size must be a whole number.")
        if not 256 <= size <= MAX_FACE_SIZE:
            raise ValueError(f"Panorama face size must be between 256 and {MAX_FACE_SIZE}.")
        if len(pack_name) > 80 or len(description) > 200:
            raise ValueError("Pack name must be 80 characters or fewer and description 200 or fewer.")
        return version, pack_name, description, size

    def start_generation(self):
        try:
            version, pack_name, description, size = self._validate()
        except Exception as exc:
            messagebox.showerror("Check your settings", str(exc))
            return
        selected_folder = filedialog.askdirectory(
            title="Choose where to save the generated resource pack",
            initialdir=str(Path.home() / "Documents")
        )
        if not selected_folder:
            return
        base = Path(selected_folder)
        safe_name = "".join(c for c in pack_name if c.isalnum() or c in " _-").strip() or "Minecraft Panorama"
        output_dir = base / safe_name
        if output_dir.exists():
            if not messagebox.askyesno("Folder already exists",
                f"{output_dir} already exists.\n\nFiles with matching names may be replaced. Continue?"):
                return
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            messagebox.showerror("Output error", str(exc))
            return

        source_array = self.full_array.copy()
        cx, cy = self.center_x, self.center_y
        icon_path = self.pack_icon_path
        self.generate_button.configure(state="disabled")
        self.progress.configure(value=0)
        self.var_status.set("Generating the six panorama faces…")
        thread = threading.Thread(
            target=self._worker,
            args=(source_array, cx, cy, size, version, pack_name, description, output_dir, icon_path),
            daemon=True
        )
        thread.start()

    def _worker(self, source_array, cx, cy, size, version, pack_name, description, output_dir, icon_path):
        try:
            shifted = recenter(source_array, cx, cy)
            texture_dir = output_dir / TEXTURE_DIR
            texture_dir.mkdir(parents=True, exist_ok=True)
            for index, face in enumerate(FACE_ORDER, start=1):
                pixels = generate_face(shifted, face, size)
                Image.fromarray(pixels, mode="RGB").save(texture_dir / f"{face}.png", format="PNG")
                self.events.put(("progress", index, f"Generated {face}.png ({index}/6)"))

            metadata = build_pack_metadata(version, description)
            (output_dir / "pack.mcmeta").write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            if icon_path:
                # Re-check the selected icon immediately before copying.
                with Image.open(icon_path) as icon:
                    if icon.format != "PNG" or icon.size != ICON_SIZE:
                        raise ValueError("The selected pack icon is no longer a valid 128×128 PNG.")
                    icon.verify()
                with Image.open(icon_path) as icon:
                    icon.save(output_dir / "pack.png", format="PNG")
            else:
                make_default_icon().save(output_dir / "pack.png", format="PNG")

            zip_path = output_dir.parent / f"{output_dir.name}.zip"
            temp_zip = zip_path.with_suffix(".zip.tmp")
            with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                for file_path in sorted(output_dir.rglob("*")):
                    if file_path.is_file():
                        archive.write(file_path, file_path.relative_to(output_dir).as_posix())
            os.replace(temp_zip, zip_path)

            # Structural validation before reporting success.
            with zipfile.ZipFile(zip_path, "r") as archive:
                names = set(archive.namelist())
                required = {"pack.mcmeta", "pack.png"} | {
                    (TEXTURE_DIR / f"{face}.png").as_posix() for face in FACE_ORDER
                }
                missing = required - names
                if missing:
                    raise RuntimeError("Pack validation failed. Missing: " + ", ".join(sorted(missing)))
                parsed = json.loads(archive.read("pack.mcmeta").decode("utf-8"))
                if parsed != metadata:
                    raise RuntimeError("Pack metadata validation failed.")
            self.events.put(("done", str(output_dir), str(zip_path)))
        except Exception as exc:
            self.events.put(("error", str(exc), traceback.format_exc()))

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, value, status = event
                    self.progress.configure(value=value)
                    self.var_status.set(status)
                elif event[0] == "done":
                    _, folder, zip_path = event
                    self.generate_button.configure(state="normal")
                    self.var_status.set("Resource pack created and validated.")
                    messagebox.showinfo(
                        "Finished",
                        "Your Minecraft resource pack is ready!\n\n"
                        f"Pack folder:\n{folder}\n\nZIP archive:\n{zip_path}\n\n"
                        "The ZIP was checked for all required files and valid metadata."
                    )
                elif event[0] == "error":
                    _, message, details = event
                    self.generate_button.configure(state="normal")
                    self.var_status.set("Generation failed. No success was reported.")
                    print(details)
                    messagebox.showerror("Generation failed", message)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)


def main():
    root = tk.Tk()
    PanoramaConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
