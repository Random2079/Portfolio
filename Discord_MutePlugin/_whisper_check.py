import sys, time, os
from pathlib import Path

print("=== 1. faster_whisper import ===")
try:
    import faster_whisper
    ver = getattr(faster_whisper, "__version__", None)
    if ver is None:
        try:
            from importlib.metadata import version
            ver = version("faster-whisper")
        except Exception as e:
            ver = f"(no __version__; metadata err: {e})"
    print(f"import ok; version={ver}")
except Exception as e:
    print(f"IMPORT FAIL: {type(e).__name__}: {e}")
    sys.exit(1)

print()
print("=== 2. ctranslate2 get_cuda_device_count ===")
try:
    import ctranslate2
    n = ctranslate2.get_cuda_device_count()
    print(f"ctranslate2.get_cuda_device_count() = {n}")
    ct_ver = getattr(ctranslate2, "__version__", None)
    if ct_ver is None:
        try:
            from importlib.metadata import version
            ct_ver = version("ctranslate2")
        except Exception:
            ct_ver = "?"
    print(f"ctranslate2 version={ct_ver}")
except Exception as e:
    print(f"FAIL: {type(e).__name__}: {e}")

print()
print("=== 3. cached whisper dirs ===")
home = Path(os.environ.get("USERPROFILE", Path.home()))
roots = [
    home / ".cache" / "huggingface",
    home / ".cache" / "huggingface" / "hub",
    home / ".cache" / "faster-whisper",
    home / "AppData" / "Local" / "huggingface",
    home / "AppData" / "Local" / "faster-whisper",
]
seen = set()
matches = []
for root in roots:
    if not root.exists():
        print(f"(missing root) {root}")
        continue
    print(f"(scan root) {root}")
    for p in root.rglob("*"):
        if p.is_dir() and "whisper" in p.name.lower():
            sp = str(p)
            if sp not in seen:
                seen.add(sp)
                matches.append(sp)

hub = home / ".cache" / "huggingface" / "hub"
if hub.exists():
    for p in hub.iterdir():
        if p.is_dir() and "whisper" in p.name.lower():
            sp = str(p)
            if sp not in seen:
                seen.add(sp)
                matches.append(sp)

if matches:
    for m in sorted(matches):
        print(m)
else:
    print("(no *whisper* dirs found under scanned roots)")

print()
print("=== 4. load + transcribe ===")
wav = Path(r"C:\Users\Home\OneDrive\Desktop\DS_Projects\Discord_MutePlugin\stt\logs\clips\ptt_20260825_191440_041287.wav")
print(f"wav exists={wav.exists()} path={wav}")
from faster_whisper import WhisperModel
prompt = "мьют, размьют, mute, unmute, замуть, размуть"
t0 = time.perf_counter()
model = WhisperModel("base", device="auto")
t_load = (time.perf_counter() - t0) * 1000
print(f'WhisperModel("base", device=auto) load_ms={t_load:.1f}')

if wav.exists():
    t1 = time.perf_counter()
    segments, info = model.transcribe(
        str(wav),
        language="ru",
        initial_prompt=prompt,
        vad_filter=False,
    )
    texts = []
    for seg in segments:
        texts.append(seg.text)
    text = "".join(texts).strip()
    t_tr = (time.perf_counter() - t1) * 1000
    print(f"transcribe_ms={t_tr:.1f}")
    print(f"language={getattr(info, 'language', None)} prob={getattr(info, 'language_probability', None)}")
    print(f"text={text!r}")
    print(f"text_plain={text}")
else:
    print("SKIP transcribe: wav missing")
