# YouTube Video Summarizer

Summarize any YouTube video with one click. While you're watching a video in Chrome, click the toolbar button and a new tab opens with:

- a **TL;DR** of the whole video,
- the **key points**, and
- **timestamped chapters** that jump to that moment in the video.

Everything runs on your own computer, on **macOS or Windows**. Summaries are written by Claude through [Claude Code](https://claude.com/claude-code) using your existing **Claude Pro or Max subscription**, or by OpenAI's [Codex CLI](https://github.com/openai/codex) using your **ChatGPT plan**.

## Features

- **One-click Chrome button.** It starts the local server only when you need it. The server shuts itself down after 10 idle minutes.
- **Works without captions.** It uses YouTube's captions when they exist. When they don't, it downloads the audio and transcribes it on your machine with [Whisper](https://github.com/openai/whisper).
- **Any summary language.** Summarize an English video in Vietnamese, a Japanese video in English, and so on.
- **Claude Code or Codex.** It uses whichever one you have installed. If you have both, it uses Claude Code unless you choose otherwise (see [Configuration](#configuration)).
- **Your choice of model and effort.** Pick Opus, Sonnet or Haiku, and how hard the model should think, right on the page.
- **Cached results.** Opening the same video again is instant and uses none of your Claude usage.
- **Nothing extra to pay for.** It runs on the Claude or ChatGPT plan you already have.

## How it works

```
 Chrome extension button
   │  1. Chrome runs a small registered helper (Native Messaging)
   │  2. the helper starts the local server if it isn't running
   │  3. the extension opens http://localhost:8000/?url=<the video>
   ▼
 Local web server (FastAPI, Python)
   ├─ video info            yt-dlp
   ├─ transcript            YouTube captions (youtube-transcript-api)
   │                          └─ no captions? download the audio → Whisper, on your CPU
   ├─ summary               Claude Code CLI (claude -p) or Codex CLI (codex exec)
   └─ cache                 cache/<video>.<language>.<model>.<effort>.json
```

## Requirements

| Requirement | Notes |
| --- | --- |
| **macOS or Windows** | The Chrome button works on both. The web app on its own also runs on Linux (see [Without the Chrome button](#without-the-chrome-button)). |
| **Google Chrome** | Other Chromium browsers (Brave, Edge, Arc) register Native Messaging hosts in different places and aren't supported out of the box. |
| **[uv](https://docs.astral.sh/uv/)** | Python project manager. It installs the right Python version (3.12) for you. |
| **[Claude Code](https://claude.com/claude-code)** *or* **[Codex CLI](https://github.com/openai/codex)** | Claude Code logged in with a Claude Pro or Max subscription, or Codex logged in with a ChatGPT plan. Summaries count against that plan's usage limits. |

You don't need `ffmpeg`, a GPU, an API key, or an OpenAI account.

## Setup

### 1. Install the tools

Install uv (skip if you already have it):

```bash
# macOS
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then install **one** of these and log in once. The summarizer reuses that login:

- **Claude Code:** install [Claude Code](https://claude.com/claude-code), run `claude` in a terminal, and log in with your Claude account.
- **Codex:** install [Node.js](https://nodejs.org), run `npm install -g @openai/codex`, then run `codex login` and sign in with your ChatGPT account.

### 2. Get the code

```bash
git clone https://github.com/<your-username>/video-summarizer.git
cd video-summarizer
uv sync
```

`uv sync` creates a private Python environment in `.venv/` and installs every dependency at the exact versions in `uv.lock`.

### 3. Try it once by hand (optional, but a good check)

```bash
uv run uvicorn app.main:app
```

Open http://localhost:8000, paste a YouTube link, and click **Summarize**. If you get a summary, everything works. Stop the server with `Ctrl+C`.

### 4. Install the Chrome button

**a. Register the launcher with Chrome:**

```bash
uv run python launcher/install.py
```

This writes two small files outside the project. One tells Chrome which program the extension may run, and the other is that program, which starts the server:

| | macOS | Windows |
| --- | --- | --- |
| Chrome's entry | `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.videosummarizer.launcher.json` | `%LOCALAPPDATA%\VideoSummarizer\com.videosummarizer.launcher.json`, plus the registry key `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.videosummarizer.launcher` that points to it |
| The program | `~/Library/Application Support/VideoSummarizer/host.sh` | `%LOCALAPPDATA%\VideoSummarizer\host.bat` |

**b. Load the extension:**

1. Open `chrome://extensions` in Chrome.
2. Turn on **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select the `extension` folder inside this project.
4. Click the puzzle-piece icon in the toolbar and **pin** "Video Summarizer".

**c. Use it:** open any YouTube video and click the red button. The first click takes a few seconds while the server starts.

> On Windows, `install.py` must run in the same Windows user account you use Chrome with, because it registers the launcher for the current user only.
>
> If macOS asks whether Google Chrome may access a folder (for example, Documents), click **Allow**. The launcher needs to read the project folder.

## Usage

- **From a YouTube video:** click the button. The summary starts automatically in a new tab.
- **From any other page:** click the button to open the summarizer, then paste a link.
- **Language, model and effort:** choose them under the link box. Your choices are remembered, and the Chrome button uses them too.
- **Chapters:** click a timestamp to open the video at that moment.
- **Copy as Markdown:** copies the whole summary, which is handy for notes apps.

Supported links: `youtube.com/watch?v=…`, `youtu.be/…`, `youtube.com/shorts/…`, `youtube.com/live/…`, and embed links.

### Choosing a model and effort

| Model | Good for |
| --- | --- |
| **Opus** | The most thorough summaries. Worth it for long, dense or technical videos, but it uses more of your plan's limits. |
| **Sonnet** (default) | The best balance of quality, speed and usage. Handles most videos well. |
| **Haiku** | Quick summaries of short, simple videos. It may add details that aren't in the video, so don't rely on it for dense content. |

Each option uses the newest model of that family available to your Claude Code login. The result shows exactly which one wrote it, for example "Sonnet 5.5, high effort".

**With Codex** the model picker is hidden. Codex uses the default model from its own settings, or `CODEX_MODEL` if you set it (see [Configuration](#configuration)). Codex has no `max` effort, so that option is hidden too; `extra high` is its highest.

**Effort** sets how much Claude thinks before writing: `low`, `medium`, `high` (default), `extra high` or `max`. Higher effort can give better summaries of long or dense videos. It also takes longer and uses more of your plan's limits.

Results are cached separately for each model and effort. Switching settings creates a new summary instead of showing the old one.

## Configuration

The defaults need no configuration. To change a setting, create a `.env` file in the project folder:

```bash
# .env
WHISPER_MODEL=base
```

| Setting | Default | What it does |
| --- | --- | --- |
| `SUMMARIZER_BACKEND` | automatic | `claude-code` or `codex`. By default it uses Claude Code if the `claude` command is installed, otherwise Codex. |
| `CODEX_MODEL` | Codex's default | The model Codex uses, for example `gpt-5.5`. |
| `CLAUDE_BIN`, `CODEX_BIN` | found on `PATH` | Full path to the `claude` or `codex` command, if the summarizer can't find it. |
| `WHISPER_MODEL` | `small` | Speech-to-text model for videos without captions: `tiny`, `base`, `small`, `medium` or `large-v3`. Larger is more accurate but slower. The model downloads on first use (`small` is ~500 MB). |
| `IDLE_SHUTDOWN_MINUTES` | `0` (never) | Shuts the server down after this many idle minutes. A server you start by hand never stops by default. The Chrome launcher always sets it to 10; to change that, edit `IDLE_SHUTDOWN_MINUTES` in `launcher/native_host.py`. |

## Without the Chrome button

The web app works on its own on any OS:

```bash
uv run uvicorn app.main:app
```

Then open http://localhost:8000. You can also bookmark a link like `http://localhost:8000/?url=<video-url>` to start a summary directly.

## Uninstall

```bash
uv run python launcher/install.py --uninstall
```

Then remove the extension in `chrome://extensions` and delete the project folder. If you used Whisper, also delete its cached models in `~/.cache/huggingface/hub/models--Systran--faster-whisper-*` (on Windows, `%USERPROFILE%\.cache\huggingface\hub\...`).

## Development

```bash
uv run uvicorn app.main:app --reload   # restarts on code changes
uv run pytest                          # unit tests
```

After changing files in `extension/`, click the reload icon on the extension in `chrome://extensions`.

## Good to know

- **Personal use.** The summarizer runs Claude Code or Codex with your own subscription on your own machine. Don't host it as a service for other people.
- **Unofficial YouTube access.** `youtube-transcript-api` and `yt-dlp` are unofficial community tools, not YouTube products. They can break when YouTube changes, and downloading content may conflict with YouTube's Terms of Service. Use them responsibly.
- **Privacy.** Transcription runs locally. Only the transcript text is sent to Claude or OpenAI to be summarized.

## Built with

[FastAPI](https://fastapi.tiangolo.com/) · [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) · [yt-dlp](https://github.com/yt-dlp/yt-dlp) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [Claude](https://www.anthropic.com/claude) · [uv](https://docs.astral.sh/uv/)
