"""Reusable Tkinter pieces of the GUI: buttons, rounded panels, cards, banner, stats, tapes.

Owner: GUI & Video.
Everything is drawn flat (no gradient, no shadow) on tk.Canvas, because Canvas can draw
rounded corners and, unlike tk.Button on macOS, takes any background colour.
Widgets only draw what app.py passes in; none of them talks to the engine.
"""
import math
import tkinter as tk
from pathlib import Path

from model import CRIMINAL, INNOCENT

_AVATAR_DIR = Path(__file__).resolve().parent.parent / "assets" / "avatars"
_TAPE_TEXT = "KEEP OUT  •  CRIME SCENE  •  DO NOT CROSS  •  "


# ---------------------------------------------------------------- drawing helpers

def _round_rect(canvas, x1, y1, x2, y2, r, fill="", outline="", width=1, tags=(), dash=None):
    """Rounded rectangle with straight, crisp edges (Tk has no native one).

    Fill = 2 rectangles + 4 quarter discs; outline = 4 straight lines + 4 quarter arcs.
    (A smoothed polygon is shorter to write, but Tk draws its edges wavy.)
    """
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    d = 2 * r
    corners = ((x1, y1, 90), (x2 - d, y1, 0), (x1, y2 - d, 180), (x2 - d, y2 - d, 270))
    if fill:
        canvas.create_rectangle(x1 + r - 0.5, y1, x2 - r + 0.5, y2, fill=fill, outline="", tags=tags)
        canvas.create_rectangle(x1, y1 + r - 0.5, x2, y2 - r + 0.5, fill=fill, outline="", tags=tags)
        if r >= 1:
            for ax, ay, start in corners:
                canvas.create_arc(ax, ay, ax + d, ay + d, start=start, extent=90, style="pieslice",
                                  fill=fill, outline="", tags=tags)
    if outline and width:
        line = {"fill": outline, "width": width, "tags": tags}
        if dash:
            line["dash"] = dash
        canvas.create_line(x1 + r, y1, x2 - r, y1, **line)
        canvas.create_line(x1 + r, y2, x2 - r, y2, **line)
        canvas.create_line(x1, y1 + r, x1, y2 - r, **line)
        canvas.create_line(x2, y1 + r, x2, y2 - r, **line)
        if r >= 1:
            arc = {"outline": outline, "width": width, "style": "arc", "tags": tags}
            if dash:
                arc["dash"] = dash
            for ax, ay, start in corners:
                canvas.create_arc(ax, ay, ax + d, ay + d, start=start, extent=90, **arc)


def _mix(c1: str, c2: str, t: float) -> str:
    """Blend two '#RRGGBB' colours: t = 0 -> c1, t = 1 -> c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def _wrap_text(text: str, font, width: int, max_lines: int | None = None) -> list[str]:
    """Split text into lines no wider than width pixels; '…' if cut at max_lines."""
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if font.measure(candidate) <= width or not line:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit_text(lines[-1] + " …", font, width)
    return lines


def _fit_text(text: str, font, width: int) -> str:
    """Cut text with '…' so it fits in width pixels."""
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + "…") > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _bind_wheel(canvas):
    """Scroll a Canvas with the mouse wheel while the pointer is over it.
    (tk.Text scrolls by itself; a Canvas needs this.)"""
    def on_wheel(event):
        if not canvas.winfo_exists():
            return
        if event.num == 4:
            step = -1
        elif event.num == 5:
            step = 1
        else:
            step = -1 if event.delta > 0 else 1
            if abs(event.delta) >= 120:
                step *= abs(event.delta) // 120
        canvas.yview_scroll(int(step), "units")

    def enter(_):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, on_wheel)

    def leave(_):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.unbind_all(seq)

    canvas.bind("<Enter>", enter, add="+")
    canvas.bind("<Leave>", leave, add="+")
    canvas.bind("<Destroy>", leave, add="+")     # a destroyed canvas never gets <Leave>


# ---------------------------------------------------------------- avatars

class AvatarCache:
    """Loads assets/avatars/<name>_<size>.png once and keeps the PhotoImage alive.

    Tkinter frees an image as soon as no Python variable refers to it (the picture
    turns blank), so every loaded image stays in self._images.
    """

    def __init__(self, root):
        self.root = root
        self._images = {}

    def get(self, name: str, size: int = 32):
        key = (name.lower(), size)
        if key not in self._images:
            path = _AVATAR_DIR / f"{name.lower()}_{size}.png"
            try:
                self._images[key] = tk.PhotoImage(master=self.root, file=str(path))
            except (tk.TclError, OSError):
                self._images[key] = None          # no file: caller draws a fallback circle
        return self._images[key]


def _draw_avatar(canvas, avatars, theme, fonts, name, x, y, size=32, tags=()):
    """Avatar picture, or a neutral circle with the first letter when there is no PNG."""
    image = avatars.get(name, size)
    if image is not None:
        canvas.create_image(x, y, image=image, anchor="nw", tags=tags)
        return
    canvas.create_oval(x, y, x + size, y + size, fill=theme["muted"], outline="", tags=tags)
    canvas.create_text(x + size / 2, y + size / 2, text=(name[:1] or "?").upper(),
                       fill=theme["on_accent"], font=fonts["body_bold"], tags=tags)


# ---------------------------------------------------------------- buttons

class FlatButton(tk.Canvas):
    """Rounded flat button. kind: primary | secondary | criminal | innocent."""

    def __init__(self, master, text, command, theme, fonts, kind="secondary", bg=None,
                 width=None, height=34):
        self.theme, self.fonts, self.kind = theme, fonts, kind
        self.text, self.command = text, command
        self.enabled, self.hover = True, False
        width = width or fonts["button"].measure(text) + 30
        super().__init__(master, width=width, height=height, bg=bg or theme["panel"],
                         highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._click)

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self._draw()

    def set_enabled(self, enabled: bool):
        if enabled != self.enabled:
            self.enabled = enabled
            self._draw()

    def _set_hover(self, value):
        self.hover = value
        self._draw()

    def _click(self, _event):
        if self.enabled and self.command:
            self.command()

    def _draw(self):
        t = self.theme
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:
            w, h = int(self["width"]), int(self["height"])
        fill, outline, fg = {
            "primary": (t["selected"], t["selected"], t["on_accent"]),
            "secondary": (t["panel"], t["border"], t["text"]),
            "criminal": (t["criminal"], t["criminal"], t["on_accent"]),
            "innocent": (t["innocent"], t["innocent"], t["on_accent"]),
        }[self.kind]
        if self.hover and self.enabled:
            if self.kind == "secondary":
                outline = t["muted"]
            else:
                fill = outline = _mix(fill, t["on_accent"], 0.12)
        if not self.enabled:
            bg = self["bg"]
            fill, outline, fg = _mix(fill, bg, 0.5), _mix(outline, bg, 0.5), _mix(fg, bg, 0.5)
        self.delete("all")
        _round_rect(self, 1, 1, w - 1, h - 1, 8, fill=fill, outline=outline, width=1)
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.fonts["button"])


# ---------------------------------------------------------------- panels

class RoundPanel(tk.Canvas):
    """Canvas with a rounded background; put child widgets in self.body (a Frame).

    fit=True: the panel is as tall as its content.
    fit=False: the content is stretched to the panel height (the panel gets its
    height from the grid / pack layout instead).
    The width comes from the layout, except when set_width() is called (board panel).
    """

    def __init__(self, master, theme, fill=None, outline=None, bg=None, radius=12, pad=16, fit=True):
        self.fill = fill or theme["panel"]
        self.outline = outline or theme["border"]
        self.radius, self.pad, self.fit = radius, pad, fit
        super().__init__(master, bg=bg or theme["canvas"], highlightthickness=0, bd=0,
                         width=2 * pad + 2, height=2 * pad + 2)
        self.body = tk.Frame(self, bg=self.fill)
        self._window = self.create_window(pad, pad, window=self.body, anchor="nw")
        self.bind("<Configure>", self._layout)
        if fit:
            self.body.bind("<Configure>", self._fit_height)

    def set_width(self, content_width: int):
        """Make the panel exactly wide enough for content_width pixels of content."""
        want = content_width + 2 * self.pad
        if int(float(self["width"])) != want:
            self.configure(width=want)

    def _layout(self, event):
        w, h = event.width, event.height
        self.delete("bg")
        _round_rect(self, 1, 1, w - 1, h - 1, self.radius, fill=self.fill, outline=self.outline,
                    width=1, tags="bg")
        self.tag_lower("bg")
        self.itemconfigure(self._window, width=max(1, w - 2 * self.pad))
        if not self.fit:
            self.itemconfigure(self._window, height=max(1, h - 2 * self.pad))

    def _fit_height(self, _event=None):
        want = self.body.winfo_reqheight() + 2 * self.pad
        if int(float(self["height"])) != want:
            self.configure(height=want)


class Banner(tk.Canvas):
    """Feedback box: kind ok | warn | error | info, bold coloured title, wrapped body."""

    def __init__(self, master, theme, fonts, bg):
        self.theme, self.fonts = theme, fonts
        self.kind, self.title, self.body = "info", "", ""
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, height=56, width=10)
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, kind, title, body):
        if (kind, title, body) != (self.kind, self.title, self.body):
            self.kind, self.title, self.body = kind, title, body
            self._draw()

    def _draw(self):
        t, f = self.theme, self.fonts
        w = self.winfo_width()
        if w <= 1:
            return
        colour, fill = {
            "ok": (t["innocent"], t["innocent_subtle"]),
            "warn": (t["warning"], t["warning_subtle"]),
            "error": (t["criminal"], t["criminal_subtle"]),
            "info": (t["muted"], t["canvas"]),
        }[self.kind]
        lines = _wrap_text(self.body, f["body"], w - 30)
        title_h, line_h = f["body_bold"].metrics("linespace"), f["body"].metrics("linespace")
        h = 10 + title_h + 2 + line_h * len(lines) + 10
        if int(float(self["height"])) != h:
            self.configure(height=h)
        self.delete("all")
        _round_rect(self, 1, 1, w - 1, h - 1, 8, fill=fill, outline=colour, width=1.5)
        self.create_text(15, 10, text=self.title, anchor="nw", fill=colour, font=f["body_bold"])
        self.create_text(15, 10 + title_h + 2, text="\n".join(lines), anchor="nw", fill=t["text"], font=f["body"])


class StatsGrid(tk.Canvas):
    """4 x 2 tiles: big number + small label."""

    COLS, TILE_H, GAP = 4, 46, 8

    def __init__(self, master, theme, fonts, bg, rows=2):
        self.theme, self.fonts, self.items = theme, fonts, []
        super().__init__(master, bg=bg, highlightthickness=0, bd=0, width=10,
                         height=rows * self.TILE_H + (rows - 1) * self.GAP)
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, items):
        """items = [(value text, label), ...] (8 of them)."""
        if items != self.items:
            self.items = items
            self._draw()

    def _draw(self):
        t, f = self.theme, self.fonts
        w = self.winfo_width()
        if w <= 1:
            return
        self.delete("all")
        tile_w = (w - (self.COLS - 1) * self.GAP) / self.COLS
        for i, (value, label) in enumerate(self.items):
            x = (i % self.COLS) * (tile_w + self.GAP)
            y = (i // self.COLS) * (self.TILE_H + self.GAP)
            _round_rect(self, x, y, x + tile_w, y + self.TILE_H, 8, fill=t["canvas"], outline="")
            self.create_text(x + 12, y + 17, text=_fit_text(value, f["stat_value"], tile_w - 20),
                             anchor="w", fill=t["text"], font=f["stat_value"])
            self.create_text(x + 12, y + 34, text=_fit_text(label, f["stat_label"], tile_w - 16),
                             anchor="w", fill=t["muted"], font=f["stat_label"])


class ClueList(tk.Frame):
    """Scrollable list of revealed clues: [cell tag] sentence. Click a row to highlight its clue."""

    def __init__(self, master, theme, fonts, on_click):
        self.theme, self.fonts, self.on_click = theme, fonts, on_click
        self.rows, self.selected = [], set()
        super().__init__(master, bg=theme["panel"])
        self.canvas = tk.Canvas(self, bg=theme["panel"], highlightthickness=0, bd=0, height=60, width=10)
        self.scroll = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw())
        _bind_wheel(self.canvas)

    def set(self, rows, selected):
        """rows = [(cell, sentence)], selected = cells whose row is highlighted."""
        if (rows, set(selected)) != (self.rows, self.selected):
            self.rows, self.selected = rows, set(selected)
            self._draw()

    def _draw(self):
        t, f = self.theme, self.fonts
        c = self.canvas
        w = c.winfo_width()
        if w <= 1:
            return
        c.delete("all")
        if not self.rows:
            c.create_text(4, 8, text="No clue revealed yet.", anchor="nw", fill=t["muted"], font=f["body"])
            self._set_region(w, 30)
            return
        y, gap, tag_w = 0, 8, 46
        line_h = f["body"].metrics("linespace")
        for cell, sentence in self.rows:
            lines = _wrap_text(sentence, f["body"], w - tag_w - 40)
            h = max(36, line_h * len(lines) + 16)
            sel = cell in self.selected
            tag = f"row:{cell}"
            _round_rect(c, 1, y + 1, w - 2, y + h - 1, 8,
                        fill=t["selected_subtle"] if sel else t["panel"],
                        outline=t["selected"] if sel else t["border"], width=2 if sel else 1, tags=tag)
            _round_rect(c, 14, y + h / 2 - 11, tag_w + 2, y + h / 2 + 11, 6,
                        fill=t["selected_subtle"], outline="", tags=tag)
            c.create_text(8 + tag_w / 2, y + h / 2, text=cell, fill=t["tag_text"], font=f["body_bold"], tags=tag)
            c.create_text(tag_w + 18, y + h / 2, text="\n".join(lines), anchor="w", fill=t["text"],
                          font=f["body"], tags=tag)
            c.tag_bind(tag, "<Button-1>", lambda e, cell=cell: self.on_click(cell))
            y += h + gap
        self._set_region(w, y - gap)

    def _set_region(self, w, content_h):
        self.canvas.configure(scrollregion=(0, 0, w, content_h))
        if content_h > self.canvas.winfo_height():
            if not self.scroll.winfo_ismapped():
                self.scroll.pack(side="right", fill="y")
        elif self.scroll.winfo_ismapped():
            self.scroll.pack_forget()


class Divider(tk.Canvas):
    """Draggable divider between the board column and the side column: a gap of the
    window colour with a thin line and a small grip in the middle."""

    WIDTH = 20

    def __init__(self, master, theme, on_drag):
        self.theme, self.on_drag, self.hover = theme, on_drag, False
        super().__init__(master, width=self.WIDTH, height=10, bg=theme["canvas"], highlightthickness=0, bd=0,
                         cursor="sb_h_double_arrow")
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<B1-Motion>", lambda e: self.on_drag(e.x_root))

    def _set_hover(self, value):
        self.hover = value
        self._draw()

    def _draw(self):
        t = self.theme
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        colour = t["muted"] if self.hover else t["border"]
        cx = w / 2
        self.create_line(cx, 0, cx, h, fill=_mix(colour, t["canvas"], 0.4), width=1)
        _round_rect(self, cx - 3, h / 2 - 24, cx + 3, h / 2 + 24, 3, fill=colour)


# ---------------------------------------------------------------- level menu

class LevelGrid(tk.Frame):
    """Scrollable grid of puzzle tiles, grouped by board size. Click a tile to play it.

    groups = [(title, [level, ...])], level = {"id", "file", "rows", "cols", "stars", "label"}.
    """

    TILE_W, TILE_H, GAP = 176, 108, 12

    def __init__(self, master, theme, fonts, groups, on_pick, current=None, solved=()):
        self.theme, self.fonts, self.groups, self.on_pick = theme, fonts, groups, on_pick
        self.current, self.solved = current, set(solved)
        super().__init__(master, bg=theme["panel"])
        self.canvas = tk.Canvas(self, bg=theme["panel"], highlightthickness=0, bd=0, width=10, height=10)
        self.scroll = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw())
        _bind_wheel(self.canvas)

    def _draw(self):
        t, f, c = self.theme, self.fonts, self.canvas
        w = c.winfo_width()
        if w <= 1:
            return
        c.delete("all")
        per_row = max(1, (w + self.GAP) // (self.TILE_W + self.GAP))
        y = 0
        for title, levels in self.groups:
            c.create_text(0, y + 10, text=title, anchor="w", fill=t["text"], font=f["panel_title"])
            c.create_text(f["panel_title"].measure(title) + 10, y + 11, anchor="w", fill=t["muted"], font=f["body"],
                          text=f"{len(levels)} case" + ("s" if len(levels) != 1 else ""))
            y += 30
            for i, level in enumerate(levels):
                x = (i % per_row) * (self.TILE_W + self.GAP)
                ty = y + (i // per_row) * (self.TILE_H + self.GAP)
                self._tile(level, x, ty)
            y += ((len(levels) + per_row - 1) // per_row) * (self.TILE_H + self.GAP) + 14
        content_h = max(0, y - 14)
        c.configure(scrollregion=(0, 0, w, content_h))
        if content_h > c.winfo_height():
            if not self.scroll.winfo_ismapped():
                self.scroll.pack(side="right", fill="y")
        elif self.scroll.winfo_ismapped():
            self.scroll.pack_forget()

    def _tile(self, level, x, y):
        t, f, c = self.theme, self.fonts, self.canvas
        tag = f"level:{level['file']}"
        playing = level["file"] == self.current
        outline, width = (t["selected"], 3) if playing else (t["facedown_border"], 1.5)
        x1, y1, x2, y2 = x + width / 2, y + width / 2, x + self.TILE_W - width / 2, y + self.TILE_H - width / 2
        _round_rect(c, x1, y1, x2, y2, 10, fill=t["facedown"], tags=tag)
        _round_rect(c, x1, y1, x2, y2, 10, outline=outline, width=width, tags=(tag, tag + ":outline"))

        # mini board: one small square per cell
        rows, cols = level["rows"], level["cols"]
        cell, gap = 7, 2
        gx = x + self.TILE_W - 12 - cols * cell - (cols - 1) * gap
        for r in range(rows):
            for col in range(cols):
                cx, cy = gx + col * (cell + gap), y + 12 + r * (cell + gap)
                c.create_rectangle(cx, cy, cx + cell, cy + cell, fill=t["panel"], outline=t["facedown_border"],
                                   tags=tag)

        c.create_text(x + 14, y + 22, text=level["id"], anchor="w", fill=t["text"], font=f["card_name"], tags=tag)
        c.create_text(x + 14, y + 42, text=f"{cols} × {rows}", anchor="w", fill=t["muted"], font=f["card_small"],
                      tags=tag)
        if level["stars"]:
            stars = "★" * level["stars"] + "☆" * (3 - level["stars"])
            c.create_text(x + 14, y + 66, text=stars, anchor="w", fill=t["highlight"], font=f["body_bold"], tags=tag)
            c.create_text(x + 14 + f["body_bold"].measure(stars) + 8, y + 66, text=level["label"], anchor="w",
                          fill=t["muted"], font=f["card_small"], tags=tag)
        else:
            c.create_text(x + 14, y + 66, text=level["label"], anchor="w", fill=t["muted"], font=f["card_small"],
                          tags=tag)

        badge = "PLAYING" if playing else ("✓ SOLVED" if level["file"] in self.solved else None)
        if badge:
            colour = t["selected"] if playing else t["innocent"]
            bw = f["badge"].measure(badge) + 18
            _round_rect(c, x + 14, y + self.TILE_H - 30, x + 14 + bw, y + self.TILE_H - 12, 9, fill=colour, tags=tag)
            c.create_text(x + 14 + bw / 2, y + self.TILE_H - 21, text=badge, fill=t["on_accent"], font=f["badge"],
                          tags=tag)

        c.tag_bind(tag, "<Button-1>", lambda e, file=level["file"]: self.on_pick(file))
        if not playing:      # hover: only recolour this tile's border (redrawing would flicker)
            c.tag_bind(tag, "<Enter>", lambda e: self._outline(tag, t["muted"]))
            c.tag_bind(tag, "<Leave>", lambda e: self._outline(tag, t["facedown_border"]))

    def _outline(self, tag, colour):
        for item in self.canvas.find_withtag(tag + ":outline"):
            option = "fill" if self.canvas.type(item) == "line" else "outline"
            self.canvas.itemconfigure(item, **{option: colour})


# ---------------------------------------------------------------- crime-scene tape

class Tape(tk.Canvas):
    """Horizontal KEEP OUT tape across the window (26 px)."""

    def __init__(self, master, theme, fonts, text=_TAPE_TEXT):
        self.theme, self.fonts, self.text = theme, fonts, text
        super().__init__(master, height=26, width=10, bg=theme["tape"], highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        t = self.theme
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        self.create_rectangle(0, 0, w, h, fill=t["tape"], outline="")
        self.create_rectangle(0, 0, w, 2, fill=t["tape_ink"], outline="")
        self.create_rectangle(0, h - 2, w, h, fill=t["tape_ink"], outline="")
        repeat = w // max(1, self.fonts["tape"].measure(self.text)) + 2
        self.create_text(12, h / 2, text=self.text * repeat, anchor="w", fill=t["tape_ink"],
                         font=self.fonts["tape"])


class CrossedTapes(tk.Canvas):
    """Decoration under the board: two tapes crossing at +7 and -6 degrees."""

    BAND = 26

    def __init__(self, master, theme, fonts):
        self.theme, self.fonts = theme, fonts
        super().__init__(master, bg=theme["canvas"], highlightthickness=0, bd=0, height=1, width=1)
        self.bind("<Configure>", lambda e: self._draw())

    def _draw(self):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("all")
        if w < 200 or h < 100:
            return                                   # not enough room: draw nothing
        length = w - 70
        self._band(w / 2, h / 2 - 12, length, 7)     # rising tape underneath
        self._band(w / 2, h / 2 + 14, length, -6)    # falling tape on top

    def _band(self, cx, cy, length, degrees):
        """One tape of `length` px centred at (cx, cy), turned `degrees` counter-clockwise."""
        t, font = self.theme, self.fonts["tape_big"]
        a = math.radians(degrees)
        cos_a, sin_a = math.cos(a), math.sin(a)
        half_l, half_b = length / 2, self.BAND / 2

        def turn(dx, dy):              # screen y grows downwards, so counter-clockwise = -a
            return cx + dx * cos_a + dy * sin_a, cy - dx * sin_a + dy * cos_a

        corners = [turn(-half_l, -half_b), turn(half_l, -half_b), turn(half_l, half_b), turn(-half_l, half_b)]
        self.create_polygon([p for xy in corners for p in xy], fill=t["tape"], outline="")
        for edge in (-half_b + 1, half_b - 1):
            self.create_line(*turn(-half_l, edge), *turn(half_l, edge), fill=t["tape_ink"], width=2)
        text = _TAPE_TEXT
        while font.measure(text) < length:
            text += _TAPE_TEXT
        text = _fit_text(text, font, length - 20).rstrip("…")
        self.create_text(*turn(-half_l + 10, 0), text=text, anchor="w", angle=degrees,
                         fill=t["tape_ink"], font=font)


# ---------------------------------------------------------------- board

class BoardView(tk.Canvas):
    """Grid of character cards with column letters, row numbers and the colour legend."""

    LABEL_W, HEADER_H, GAP, LEGEND_TOP = 30, 28, 8, 14
    EDGE = 3                                   # free pixels right of the last column, so its border is never clipped
    MIN_CARD, MAX_CARD = 96, 210

    def __init__(self, master, theme, fonts, avatars, on_click):
        self.theme, self.fonts, self.avatars, self.on_click = theme, fonts, avatars, on_click
        super().__init__(master, bg=theme["panel"], highlightthickness=0, bd=0, width=600, height=400)

    def draw_empty(self, message, detail):
        t, f = self.theme, self.fonts
        self.delete("all")
        self.configure(width=560, height=420)
        _round_rect(self, 2, 2, 558, 418, 12, fill=t["canvas"], outline=t["border"], dash=(6, 4))
        self.create_text(280, 190, text=message, fill=t["text"], font=f["panel_title"])
        self.create_text(280, 220, text=detail, fill=t["muted"], font=f["body"], width=480, justify="center")

    def natural_width(self, rows, cols):
        """Board width with cards at their normal width (140 px up to 4 columns, 116 px with 5)."""
        w = 140 if cols <= 4 else 116
        return self.LABEL_W + cols * w + (cols - 1) * self.GAP + self.EDGE

    def max_width(self, cols):
        """Board width with the biggest cards (the divider stops here, so the panel never ends early)."""
        return self.LABEL_W + cols * self.MAX_CARD + (cols - 1) * self.GAP + self.EDGE

    def min_width(self, cols):
        """Board width with the smallest cards (the divider must leave at least this)."""
        return self.LABEL_W + cols * self.MIN_CARD + (cols - 1) * self.GAP + self.EDGE

    def card_size(self, rows, cols, max_width, max_height):
        """(width, height) of a card. The width follows the space the divider leaves
        (normal width if unknown); the height is at most the width and shrinks so the
        board fits max_height."""
        if max_width is None:
            w = 140 if cols <= 4 else 116
        else:
            w = int((max_width - self.LABEL_W - self.EDGE - (cols - 1) * self.GAP) // cols)
        w = max(self.MIN_CARD, min(self.MAX_CARD, w))
        h = w
        while h > 92 and self._height(rows, cols, w, h) > max_height:
            h -= 2
        return w, h

    def _height(self, rows, cols, w, h):
        grid_w = self.LABEL_W + cols * w + (cols - 1) * self.GAP
        return self.HEADER_H + rows * h + (rows - 1) * self.GAP + self.LEGEND_TOP + self._legend(0, grid_w, False)

    def draw(self, cells, rows, cols, texts, verdicts, selected, highlighted, max_width=None, max_height=10_000):
        """cells: public_state["cells"]; texts: {cell: clue sentence} of face-up cards."""
        t, f = self.theme, self.fonts
        w, h = self.card_size(rows, cols, max_width, max_height)
        grid_h = rows * h + (rows - 1) * self.GAP
        width = self.LABEL_W + cols * w + (cols - 1) * self.GAP + self.EDGE
        self.delete("all")

        for c in range(cols):
            x = self.LABEL_W + c * (w + self.GAP) + w / 2
            self.create_text(x, self.HEADER_H / 2, text=chr(ord("A") + c), fill=t["muted"], font=f["axis"])
        for r in range(rows):
            y = self.HEADER_H + r * (h + self.GAP) + h / 2
            self.create_text(self.LABEL_W / 2 - 4, y, text=str(r + 1), fill=t["muted"], font=f["axis"])

        for i, info in enumerate(cells):
            r, c = divmod(i, cols)
            x = self.LABEL_W + c * (w + self.GAP)
            y = self.HEADER_H + r * (h + self.GAP)
            self._card(info, x, y, w, h, verdicts.get(info["cell"]), texts.get(info["cell"]),
                       info["cell"] == selected, info["cell"] in highlighted)

        legend_h = self._legend(self.HEADER_H + grid_h + self.LEGEND_TOP, width, True)
        self.configure(width=width, height=self.HEADER_H + grid_h + self.LEGEND_TOP + legend_h)

    def _card(self, info, x, y, w, h, verdict, clue_text, is_selected, is_highlighted):
        t, f = self.theme, self.fonts
        cell, tag, pad = info["cell"], f"card:{info['cell']}", 10
        if verdict == CRIMINAL:
            fill, border, bw = t["criminal_subtle"], t["criminal"], 2
        elif verdict == INNOCENT:
            fill, border, bw = t["innocent_subtle"], t["innocent"], 2
        else:
            fill, border, bw = t["facedown"], t["facedown_border"], 1
        if is_selected:                      # selected wins over highlighted
            border, bw = t["selected"], 3
        elif is_highlighted:
            border, bw = t["highlight"], 3
        inset = bw / 2
        _round_rect(self, x + inset, y + inset, x + w - inset, y + h - inset, 10,
                    fill=fill, outline=border, width=bw, tags=tag)

        # header: avatar, name, cell id
        _draw_avatar(self, self.avatars, t, f, info["name"], x + pad, y + pad, 32, tags=tag)
        coord_w = f["card_coord"].measure(cell)
        self.create_text(x + w - pad, y + pad + 16, text=cell, anchor="e", fill=t["muted"],
                         font=f["card_coord"], tags=tag)
        left, right = x + pad + 32 + 6, x + w - pad - coord_w - 6
        self.create_text((left + right) / 2, y + pad + 16,
                         text=_fit_text(info["name"], f["card_name"], right - left),
                         fill=t["text"], font=f["card_name"], tags=tag)

        # job line (left out on very small cards; the Verdict panel still shows it)
        if h >= 140:
            job_y, badge_top = y + pad + 44, y + pad + 54
        elif h >= 112:
            job_y, badge_top = y + pad + 41, y + pad + 49
        else:
            job_y, badge_top = None, y + pad + 38
        if job_y is not None:
            self.create_text(x + pad, job_y, text=_fit_text(info["job"], f["card_small"], w - 2 * pad),
                             anchor="w", fill=t["muted"], font=f["card_small"], tags=tag)

        # badge: CRIMINAL / INNOCENT pill, or "?" while face-down
        if verdict:
            badge_w = f["badge"].measure(verdict) + 18
            _round_rect(self, x + pad, badge_top, x + pad + badge_w, badge_top + 18, 9,
                        fill=t["criminal"] if verdict == CRIMINAL else t["innocent"], outline="", tags=tag)
            self.create_text(x + pad + badge_w / 2, badge_top + 9, text=verdict, fill=t["on_accent"],
                             font=f["badge"], tags=tag)
        else:
            _round_rect(self, x + pad, badge_top, x + pad + 22, badge_top + 18, 9,
                        fill=t["panel"], outline="", tags=tag)
            self.create_text(x + pad + 11, badge_top + 9, text="?", fill=t["muted"], font=f["badge"], tags=tag)

        # clue box: a lighter blend of the card colour
        box_top, box_bottom = badge_top + 18 + 6, y + h - pad
        box_fill = _mix(fill, t["panel"], 0.5 if verdict is None else 0.8)
        _round_rect(self, x + pad, box_top, x + w - pad, box_bottom, 6, fill=box_fill, outline="", tags=tag)
        line_h = f["clue"].metrics("linespace")
        max_lines = max(1, int((box_bottom - box_top - 8) // line_h))
        if clue_text is None:
            self.create_text(x + pad + 8, box_top + 5, text="Clue hidden", anchor="nw", fill=t["muted"],
                             font=f["clue"], tags=tag)
        else:
            lines = _wrap_text(clue_text, f["clue"], w - 2 * pad - 16, max_lines)
            self.create_text(x + pad + 8, box_top + 5, text="\n".join(lines), anchor="nw", fill=t["text"],
                             font=f["clue"], tags=tag)
        self.tag_bind(tag, "<Button-1>", lambda e, cell=cell: self.on_click(cell))

    def _legend(self, top, width, draw):
        """Colour legend in one or more lines (wraps to `width`); returns its height."""
        t, f = self.theme, self.fonts
        items = [("Criminal", t["criminal"], ""), ("Innocent", t["innocent"], ""),
                 ("Face-down", t["facedown_border"], t["facedown"]),
                 ("Referenced by selected clue", t["highlight"], ""), ("Selected cell", t["selected"], "")]
        x, y, line_h = 0, top, 22
        for label, colour, fill in items:
            item_w = 22 + f["legend"].measure(label) + 18
            if x > 0 and x + item_w - 18 > width:
                x, y = 0, y + line_h
            if draw:
                _round_rect(self, x + 1, y + 1, x + 15, y + 15, 3, fill=fill or t["panel"],
                            outline=colour, width=2)
                self.create_text(x + 22, y + 8, text=label, anchor="w", fill=t["muted"], font=f["legend"])
            x += item_w
        return y - top + line_h
