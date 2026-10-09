// Toolbar button: make sure the local server is running (via the native launcher),
// then open the summarizer page for the video in the current tab.

const HOST = "com.videosummarizer.launcher";
const DEFAULT_TITLE = "Summarize this video";
const VIDEO_URL = /^https:\/\/((www|m)\.)?(youtube\.com\/(watch\?|shorts\/|live\/)|youtu\.be\/)/;

chrome.action.onClicked.addListener(async (tab) => {
  await setBadge("…", "#6b6b66", "Starting the summarizer…");

  let reply;
  try {
    reply = await chrome.runtime.sendNativeMessage(HOST, { command: "start" });
  } catch (err) {
    return setBadge("!", "#b42318",
      `Can't run the launcher (${err.message}). Run: uv run python launcher/install.py`);
  }
  if (!reply?.ok) {
    return setBadge("!", "#b42318", reply?.error || "The launcher failed to start the server.");
  }

  await setBadge("", null, DEFAULT_TITLE);
  const page = new URL(reply.url);
  if (tab.url && VIDEO_URL.test(tab.url)) page.searchParams.set("url", tab.url);
  chrome.tabs.create({ url: page.href, index: tab.index + 1, openerTabId: tab.id });
});

async function setBadge(text, color, title) {
  await chrome.action.setBadgeText({ text });
  if (color) await chrome.action.setBadgeBackgroundColor({ color });
  await chrome.action.setTitle({ title });
}
