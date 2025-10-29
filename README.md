# Normalmap_generator_v3 — venv setup

This repository contains `main.py` (a Tkinter GUI app) and a Python virtual environment setup.

## What I created
- `.venv/` — virtual environment (created locally in the project)
- `requirements.txt` — runtime dependencies

## How to activate (PowerShell)
Open PowerShell in the project folder and run:

```powershell
# Allow script execution for this session (does not persist)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force

# Activate the venv
.\.venv\Scripts\Activate.ps1

# (optional) upgrade pip
python -m pip install --upgrade pip

# Run the app
python main.py
```

If you prefer CMD (no execution policy change needed), run:

```cmd
.\.venv\Scripts\activate.bat
python main.py
```

## Notes
- I installed the packages listed in `requirements.txt` into the `.venv` and ran a quick import test (customtkinter, cv2, numpy, Pillow, tkinterdnd2). The test printed `IMPORTS_OK` during setup.
- If you run into issues with `tkinter` on Windows, ensure your Python installation includes Tcl/Tk (the official Windows installer does this by default).

If you want, I can:
- Pin exact package versions to `requirements.txt`.
- Create a small script to launch the app with better diagnostics.
- Add a `.gitignore` entry for `.venv` if you plan to commit the repo.
