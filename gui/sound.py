"""Short sound effects, made with the Python standard library only.

Owner: GUI & Video.
Each effect is a few notes synthesised with math + wave into a temporary WAV file
(the first time it is needed), then played without blocking the window:
macOS `afplay`, Windows `winsound`, Linux `paplay` / `aplay`. If no player exists
the game is simply silent. Set GRIDUCTIVE_SOUND=0 to start muted.
"""
import array
import atexit
import math
import os
import shutil
import subprocess
import sys
import tempfile
import wave

_RATE = 22050

# effect -> notes; a note is (frequency Hz or None for silence, seconds, volume 0..1, shape)
_EFFECTS = {
    "select": [(1600, 0.035, 0.20, "sine")],
    "accept": [(660, 0.07, 0.28, "sine"), (990, 0.16, 0.28, "sine")],
    "flip": [(880, 0.06, 0.18, "sine")],
    "not_provable": [(494, 0.09, 0.24, "sine"), (392, 0.18, 0.24, "sine")],
    "contradicted": [(196, 0.11, 0.22, "square"), (None, 0.03, 0, "sine"), (165, 0.18, 0.22, "square")],
    "hint": [(1319, 0.05, 0.18, "sine"), (1760, 0.05, 0.18, "sine"), (2093, 0.14, 0.16, "sine")],
    "win": [(523, 0.10, 0.26, "bell"), (659, 0.10, 0.26, "bell"), (784, 0.10, 0.26, "bell"),
            (1047, 0.36, 0.26, "bell")],
}


def _samples(notes) -> array.array:
    """16-bit mono samples: each note has a 4 ms attack and an exponential fade-out."""
    out = array.array("h")
    for freq, seconds, volume, shape in notes:
        n = int(_RATE * seconds)
        for i in range(n):
            if freq is None:
                out.append(0)
                continue
            phase = 2 * math.pi * freq * i / _RATE
            if shape == "square":          # soft square: first odd harmonics only
                value = math.sin(phase) + math.sin(3 * phase) / 3 + math.sin(5 * phase) / 5
            elif shape == "bell":          # a little brighter than a plain sine
                value = math.sin(phase) + 0.3 * math.sin(2 * phase)
            else:
                value = math.sin(phase)
            attack = min(1.0, i / (0.004 * _RATE))
            fade = math.exp(-4.0 * i / n)
            out.append(int(32767 * volume * 0.8 * value * attack * fade))
    return out


def _player():
    """A function play(path) for this machine, or None if no player is available."""
    if sys.platform == "win32":
        try:
            import winsound
        except ImportError:
            return None
        return lambda path: winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    for command in (["afplay"], ["paplay"], ["aplay", "-q"]):
        if shutil.which(command[0]):
            return lambda path, command=command: subprocess.Popen(
                command + [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return None


class Sfx:
    """sfx.play("accept"). Never raises: a sound problem must not break the game."""

    def __init__(self, enabled=True):
        self.enabled = enabled and os.environ.get("GRIDUCTIVE_SOUND", "1") != "0"
        self._play = _player()
        self._dir = None
        self._files = {}
        self._running = []           # player processes, reaped so they do not pile up

    @property
    def available(self) -> bool:
        return self._play is not None

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled

    def play(self, name: str) -> None:
        if not self.enabled or self._play is None or name not in _EFFECTS:
            return
        try:
            process = self._play(self._file(name))
            self._running = [p for p in self._running if p.poll() is None]
            if process is not None:
                self._running.append(process)
        except (OSError, RuntimeError, ValueError):
            pass

    def _file(self, name: str) -> str:
        """Path of the WAV for `name`, written once per run into a temporary folder."""
        if name not in self._files:
            if self._dir is None:
                self._dir = tempfile.mkdtemp(prefix="griductive_sfx_")
                atexit.register(shutil.rmtree, self._dir, True)
            path = os.path.join(self._dir, f"{name}.wav")
            with wave.open(path, "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(_RATE)
                samples = _samples(_EFFECTS[name])
                if sys.byteorder == "big":      # WAV data is little-endian
                    samples.byteswap()
                out.writeframes(samples.tobytes())
            self._files[name] = path
        return self._files[name]
