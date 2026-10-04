# Launch

Canonical repo entry: `wscript launch.vbs` (or `wscript launch\run.vbs` — same thing).

- `launch.vbs` probes imports, then starts `pythonw launch_gui.py` with **no** `cmd` window.
- `launch_gui.py` tees stdout/stderr into `_launch_error.log` so pythonw crashes are not silent.

Desktop may still use `%LocalAppData%\SubtitleRipper\Launcher\SubtitleLauncher.exe` (outside this repo). That path can hide failures; prefer pointing the shortcut at:

`wscript.exe` + arguments: `"C:\Users\Home\OneDrive\Desktop\DS_Projects\YouTube_Translator\launch.vbs"`
