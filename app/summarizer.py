import json
import os
import shutil
import subprocess
import tempfile

import anthropic

from .models import Effort, ModelChoice, Segment, Summary, VideoInfo

# Model IDs for the API backend; the Claude Code CLI resolves the aliases itself.
API_MODELS: dict[str, str] = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}
BLOCK_SECONDS = 30
CLAUDE_CODE_TIMEOUT = 600  # seconds

SYSTEM_PROMPT = """You summarize YouTube videos from their transcripts.

Each transcript line starts with a [mm:ss] or [h:mm:ss] timestamp. Auto-generated captions
and speech-to-text can contain misheard words; infer the intended meaning from context.

Write a faithful summary of what the video actually says - do not add outside facts or opinions.
- tldr: two or three sentences covering the whole video.
- key_points: the most important takeaways, specific rather than generic (names, numbers,
  steps, conclusions). Usually 4-10 items depending on length and density.
- chapters: chronological sections that a viewer could jump to. Each start_seconds must be a
  timestamp that appears in the transcript, converted to seconds. Use roughly one chapter per
  few minutes of content; short videos may have only two or three."""


class SummaryError(Exception):
    pass


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def format_timestamp(seconds: float) -> str:
    s = int(seconds)
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def format_transcript(segments: list[Segment]) -> str:
    """Merge short caption segments into ~30s blocks, each prefixed with its start timestamp."""
    lines: list[str] = []
    block_start: float | None = None
    block_text: list[str] = []
    for seg in segments:
        if block_start is None:
            block_start = seg.start
        elif seg.start - block_start >= BLOCK_SECONDS:
            lines.append(f"[{format_timestamp(block_start)}] {' '.join(block_text)}")
            block_start, block_text = seg.start, []
        block_text.append(seg.text.replace("\n", " ").strip())
    if block_text:
        lines.append(f"[{format_timestamp(block_start)}] {' '.join(block_text)}")
    return "\n".join(lines)


def summarize(
    segments: list[Segment], video: VideoInfo, language: str, model: ModelChoice, effort: Effort
) -> tuple[Summary, str]:
    """Returns the summary and the exact model ID that wrote it."""
    if not segments:
        raise SummaryError("The transcript is empty - there is nothing to summarize.")

    language_instruction = (
        "Write the summary in the same language as the transcript."
        if language == "auto"
        else f"Write the summary in {language}, regardless of the transcript's language."
    )
    user_content = (
        f"Video title: {video.title}\n"
        + (f"Channel: {video.channel}\n" if video.channel else "")
        + f"\n<transcript>\n{format_transcript(segments)}\n</transcript>\n\n"
        + language_instruction
    )

    backend = os.getenv("SUMMARIZER_BACKEND", "claude-code")
    if backend == "claude-code":
        return _summarize_with_claude_code(user_content, model, effort)
    if backend == "api":
        return _summarize_with_api(user_content, model, effort)
    raise SummaryError(f"Unknown SUMMARIZER_BACKEND {backend!r}; use 'claude-code' or 'api'.")


def _summarize_with_claude_code(user_content: str, model: ModelChoice, effort: Effort) -> tuple[Summary, str]:
    """Run Claude Code headless (`claude -p`), which uses your Claude subscription's usage limits."""
    claude_bin = os.getenv("CLAUDE_BIN") or shutil.which("claude")
    if not claude_bin:
        raise SummaryError(
            "Claude Code CLI not found. Install it (https://claude.com/claude-code) "
            "or set CLAUDE_BIN to its path."
        )

    cmd = [
        claude_bin, "-p",
        "--output-format", "json",
        "--model", model,
        "--effort", effort,
        # Replace Claude Code's large default system prompt and turn off tools, settings
        # and MCP servers: this is a single text-in, JSON-out call.
        "--system-prompt", SYSTEM_PROMPT,
        "--tools", "",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--json-schema", json.dumps(Summary.model_json_schema()),
    ]
    # An API key in the environment (e.g. from .env) would make the CLI bill the API
    # instead of using the subscription login, so hide it from the subprocess.
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}

    try:
        with tempfile.TemporaryDirectory(prefix="summarizer-") as cwd:
            proc = subprocess.run(
                cmd, input=user_content, capture_output=True, text=True,
                timeout=CLAUDE_CODE_TIMEOUT, cwd=cwd, env=env,
            )
    except subprocess.TimeoutExpired as e:
        raise SummaryError("Claude Code took too long to respond. Try again.") from e

    try:
        output = json.loads(proc.stdout)
    except json.JSONDecodeError:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        raise SummaryError(
            f"Claude Code failed (exit {proc.returncode}): {detail[-1] if detail else 'no output'}. "
            "If you're not logged in, run `claude` in a terminal and log in with your Claude account."
        )

    if output.get("is_error") or output.get("subtype") != "success":
        raise SummaryError(f"Claude Code error: {output.get('result') or output.get('subtype')}")
    structured = output.get("structured_output")
    if structured is None:
        raise SummaryError("Claude Code returned no structured summary.")
    # modelUsage is keyed by the exact model IDs that ran, e.g. {"claude-opus-5-5": {...}}.
    model_id = next(iter(output.get("modelUsage") or {}), model)
    return Summary.model_validate(structured), model_id


def _summarize_with_api(user_content: str, model: ModelChoice, effort: Effort) -> tuple[Summary, str]:
    """Call the Anthropic API directly (pay-as-you-go, needs ANTHROPIC_API_KEY)."""
    # Server-side refusal fallback isn't available for Haiku.
    fallback = {} if model == "haiku" else {
        "betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default",
    }
    try:
        response = _get_client().beta.messages.create(
            model=API_MODELS[model],
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": Summary.model_json_schema()},
            },
            **fallback,
        )
    except TypeError as e:
        # The SDK raises TypeError at request time when no credentials are configured at all.
        if "authentication" not in str(e):
            raise
        raise SummaryError("No Anthropic API key found. Set ANTHROPIC_API_KEY in .env.") from e
    except anthropic.AuthenticationError as e:
        raise SummaryError("Anthropic API key is invalid. Check ANTHROPIC_API_KEY in .env.") from e
    except anthropic.RateLimitError as e:
        raise SummaryError("Rate limited by the Anthropic API. Wait a minute and try again.") from e
    except anthropic.APIStatusError as e:
        raise SummaryError(f"Anthropic API error ({e.status_code}): {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise SummaryError("Could not reach the Anthropic API. Check your internet connection.") from e

    if response.stop_reason == "refusal":
        raise SummaryError("Claude declined to summarize this video.")
    if response.stop_reason == "max_tokens":
        raise SummaryError("The summary was cut off before it finished. Try again.")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if text is None:
        raise SummaryError("Claude returned no summary text.")
    return Summary.model_validate(json.loads(text)), response.model
