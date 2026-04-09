# Backend Setup Guide (Windows)

## Prerequisites

- Python 3.11 or higher
- Windows environment with `winget` available

---

## Install Required Tools

### 1. uv (Python package manager)

```bash
winget install --id astral-sh.uv -e --source winget
```

### 2. FFmpeg

```bash
winget install --id Gyan.FFmpeg -e --source winget
```

### 3. Poppler

```bash
winget install --id oschwartz10612.poppler --source winget
```

---

## Project Setup

### 1. Verify tool installations

Run the following commands to confirm everything is installed correctly:

```bash
ffmpeg -version
pdftoppm -v
uv --version
```

If any command is not recognized, restart your terminal and try again. Make sure all tools are available in your system `PATH`.

### 2. Install project dependencies

```bash
uv sync --all-extras
```

### 3. Set up environment variables

Copy the `.env` files to the project `src/api` directory:
- `.env.example` -> `.env`
- `.env.aws.example` -> `.env.aws`

---

## Run the Backend

Navigate to the source directory:

```bash
cd src
```

Start the startup script:

```bash
uv run python startup.py
```

Start the API server:

```bash
uv run uvicorn api.main:app --reload --port 8001
```

---

## Notes

- `uvloop` is not supported on Windows and is automatically excluded via the platform marker in `pyproject.toml`.
- All installed tools must be accessible via your system `PATH`.
- If a command is not recognized after installation, restart your terminal and try again.
