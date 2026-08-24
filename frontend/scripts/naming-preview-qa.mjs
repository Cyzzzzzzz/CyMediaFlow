import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const targets = await fetch("http://127.0.0.1:9224/json").then((response) => response.json());
const target = targets.find((entry) => entry.type === "page");
if (!target) throw new Error("No Edge page target is available on port 9224.");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let id = 0;
const pending = new Map();
const errors = [];
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const task = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) task.reject(new Error(`${task.method}: ${message.error.message}`));
    else task.resolve(message.result);
  }
  if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails.text);
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
    errors.push(message.params.args.map((argument) => argument.value ?? argument.description).join(" "));
  }
});

function command(method, params = {}) {
  const commandId = ++id;
  socket.send(JSON.stringify({ id: commandId, method, params }));
  return new Promise((resolve, reject) => pending.set(commandId, { resolve, reject, method }));
}

async function evaluate(expression) {
  let result;
  try {
    result = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  } catch (error) {
    throw new Error(`${error.message}; expression=${expression}`);
  }
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function waitFor(expression, timeout = 20000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 160));
  }
  throw new Error(`Timed out waiting for ${expression}`);
}

async function setViewport(width, height) {
  await command("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
}

async function navigate(posterIndex = 4) {
  await command("Page.navigate", { url: "http://127.0.0.1:5173/" });
  await waitFor("document.readyState === 'complete' && document.querySelectorAll('.poster-card').length === 5");
  await evaluate(`document.querySelectorAll('.poster-card')[${posterIndex}]?.click()`);
  await waitFor("!!document.querySelector('.scrape-drawer')");
  await new Promise((resolve) => setTimeout(resolve, 350));
}

async function findNfoGenerationCandidate() {
  const posterCount = await evaluate("document.querySelectorAll('.poster-card').length");
  for (let posterIndex = 0; posterIndex < posterCount; posterIndex += 1) {
    await navigate(posterIndex);
    await evaluate("document.querySelectorAll('.accordion-trigger')[1]?.click()");
    await waitFor("document.querySelectorAll('.accordion')[1]?.classList.contains('open')");
    await new Promise((resolve) => setTimeout(resolve, 800));
    if (await evaluate("!!document.querySelector('.nfo-generation-card .preview-refresh')")) return posterIndex;
  }
  return null;
}

async function capture(name) {
  const result = await command("Page.captureScreenshot", { format: "png", fromSurface: true });
  const directory = path.resolve(".data/design-qa");
  await mkdir(directory, { recursive: true });
  await writeFile(path.join(directory, name), Buffer.from(result.data, "base64"));
}

await command("Page.enable");
await command("Runtime.enable");
await setViewport(1751, 898);
await navigate(0);
errors.length = 0;
await evaluate("document.querySelectorAll('.accordion-trigger')[1]?.click()");
await waitFor("document.querySelectorAll('.episode-card').length === 12 && [...document.querySelectorAll('.scrape-info-panel img')].every((image) => image.complete && image.naturalWidth > 0)");
await waitFor("!![...document.querySelectorAll('.metadata-scrape-action button')].find((button) => button.textContent.includes('刮削元数据') && !button.disabled)");
await evaluate("[...document.querySelectorAll('.metadata-scrape-action button')].find((button) => button.textContent.includes('刮削元数据'))?.click()");
await waitFor("document.querySelector('.metadata-scrape-status.success')?.textContent.includes('已重新获取')");
const scrapeInfo = await evaluate(`({
  title: document.querySelector('.scrape-series-main h3')?.textContent,
  seasons: document.querySelectorAll('.scrape-season-card').length,
  episodes: document.querySelectorAll('.episode-card').length,
  seriesPosters: document.querySelectorAll('.series-artwork img').length,
  seasonPosters: document.querySelectorAll('.season-artwork img').length,
  episodePosters: document.querySelectorAll('.episode-artwork img').length,
  seasonPosterSource: document.querySelector('.season-summary small')?.textContent,
  metadataButton: document.querySelector('.metadata-scrape-action button')?.textContent,
  metadataStatus: document.querySelector('.metadata-scrape-status.success')?.textContent,
  overflow: document.documentElement.scrollWidth > innerWidth,
})`);
await capture("scrape-info-01.png");

const nfoGenerationCandidate = await findNfoGenerationCandidate();
let nfoGeneration;
if (nfoGenerationCandidate === null) {
  nfoGeneration = { skipped: "All current samples already have local NFO files." };
} else {
  await evaluate("document.querySelector('.nfo-generation-card .preview-refresh')?.click()");
  await waitFor("!!document.querySelector('.nfo-generation-confirm')");
  nfoGeneration = await evaluate(`({
    posterIndex: ${nfoGenerationCandidate},
    title: document.querySelector('.nfo-generation-card strong')?.textContent,
    confirmation: document.querySelector('.nfo-generation-confirm span')?.textContent,
    confirmButton: document.querySelector('.nfo-generation-confirm .primary-button')?.textContent,
    overflow: document.documentElement.scrollWidth > innerWidth,
  })`);
  await capture("nfo-generation-confirm-01.png");
}

await navigate(4);
await evaluate("document.querySelectorAll('.accordion-trigger')[3]?.click()");
await waitFor("!!document.querySelector('.nfo-preview') && document.querySelectorAll('.rename-diff').length === 73");
await evaluate("document.querySelector('.preview-refresh')?.click()");
await waitFor("!document.querySelector('.preview-refresh')?.disabled");
const desktop = await evaluate(`({
  rows: document.querySelectorAll('.rename-diff').length,
  folders: document.querySelectorAll('.rename-folder').length,
  selected: document.querySelectorAll('.diff-select input:checked').length,
  skipped: document.querySelectorAll('.diff-select input:not(:checked)').length,
  summary: document.querySelector('.preview-counts')?.textContent,
  open: document.querySelector('.accordion.open .accordion-heading strong')?.textContent,
  overflow: document.documentElement.scrollWidth > innerWidth,
  drawerScrollHeight: document.querySelector('.drawer-scroll')?.scrollHeight,
})`);
await capture("nfo-preview-01.png");

await evaluate("document.querySelector('.folder-toggle')?.click()");
await waitFor("document.querySelectorAll('.rename-folder.collapsed').length === 1 && document.querySelectorAll('.rename-diff').length < 73");
const collapseInteraction = await evaluate(`({
  collapsedFolders: document.querySelectorAll('.rename-folder.collapsed').length,
  visibleRows: document.querySelectorAll('.rename-diff').length,
  selectedSummary: document.querySelector('.preview-counts .rename')?.textContent,
  expanded: document.querySelector('.folder-toggle')?.getAttribute('aria-expanded'),
})`);
await capture("nfo-preview-01-collapsed.png");
await evaluate("document.querySelector('.folder-toggle')?.click()");
await waitFor("document.querySelectorAll('.rename-diff').length === 73");

const selectionBaseline = await evaluate(`(() => {
  const folder = document.querySelector('.folder-select').closest('.rename-folder');
  const inputs = [...folder.querySelectorAll('.diff-select input:not(:disabled)')];
  return { selectable: inputs.length, checked: inputs.filter((input) => input.checked).length };
})()`);
await evaluate("document.querySelector('.folder-select').closest('.rename-folder').querySelector('.diff-select input:not(:disabled)')?.click()");
await waitFor(`(() => { const inputs = [...document.querySelector('.folder-select').closest('.rename-folder').querySelectorAll('.diff-select input:not(:disabled)')]; return inputs.filter((input) => input.checked).length !== ${selectionBaseline.checked}; })()`);
await evaluate("document.querySelector('.folder-select')?.click()");
await waitFor(`document.querySelector('.folder-select').closest('.rename-folder').querySelectorAll('.diff-select input:not(:disabled):checked').length === ${selectionBaseline.selectable}`);
await evaluate("document.querySelector('.folder-select')?.click()");
await waitFor("document.querySelector('.folder-select').closest('.rename-folder').querySelectorAll('.diff-select input:not(:disabled):checked').length === 0");
await evaluate("document.querySelector('.folder-select')?.click()");
await waitFor(`document.querySelector('.folder-select').closest('.rename-folder').querySelectorAll('.diff-select input:not(:disabled):checked').length === ${selectionBaseline.selectable}`);
const selectionInteraction = await evaluate(`({
  baseline: ${JSON.stringify(selectionBaseline)},
  selected: document.querySelectorAll('.diff-select input:checked').length,
  firstFolderAction: document.querySelector('.folder-select')?.textContent,
})`);

await setViewport(390, 844);
await navigate();
await evaluate("document.querySelectorAll('.accordion-trigger')[3]?.click()");
await waitFor("!!document.querySelector('.nfo-preview') && document.querySelectorAll('.rename-diff').length === 73");
const mobile = await evaluate(`({
  rows: document.querySelectorAll('.rename-diff').length,
  folders: document.querySelectorAll('.rename-folder').length,
  selected: document.querySelectorAll('.diff-select input:checked').length,
  overflow: document.documentElement.scrollWidth > innerWidth,
  drawer: (() => { const r = document.querySelector('.scrape-drawer').getBoundingClientRect(); return { left: r.left, right: r.right, width: r.width }; })(),
})`);
await evaluate("document.querySelector('.folder-toggle')?.click()");
await waitFor("document.querySelectorAll('.rename-folder.collapsed').length === 1");
const mobileCollapse = await evaluate(`({
  collapsedFolders: document.querySelectorAll('.rename-folder.collapsed').length,
  visibleRows: document.querySelectorAll('.rename-diff').length,
  overflow: document.documentElement.scrollWidth > innerWidth,
  expanded: document.querySelector('.folder-toggle')?.getAttribute('aria-expanded'),
})`);
await capture("nfo-preview-01-mobile.png");

await navigate(0);
await evaluate("document.querySelectorAll('.accordion-trigger')[1]?.click()");
await waitFor("document.querySelectorAll('.episode-card').length === 12 && [...document.querySelectorAll('.scrape-info-panel img')].every((image) => image.complete && image.naturalWidth > 0)");
const scrapeInfoMobile = await evaluate(`({
  episodes: document.querySelectorAll('.episode-card').length,
  images: document.querySelectorAll('.scrape-info-panel img').length,
  overflow: document.documentElement.scrollWidth > innerWidth,
  episodeStripScrollable: (() => { const strip = document.querySelector('.episode-strip'); return strip.scrollWidth > strip.clientWidth; })(),
})`);
await capture("scrape-info-01-mobile.png");

console.log(JSON.stringify({ scrapeInfo, nfoGeneration, desktop, collapseInteraction, selectionInteraction, mobile, mobileCollapse, scrapeInfoMobile, errors }, null, 2));
socket.close();
