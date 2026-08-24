import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const endpoint = "http://127.0.0.1:9224";
const outputDirectory = path.resolve(".data/design-qa");
await mkdir(outputDirectory, { recursive: true });

const targets = await fetch(`${endpoint}/json`).then((response) => response.json());
const target = targets.find((entry) => entry.type === "page");
if (!target) throw new Error("No Edge page target is available on port 9224.");

const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

let commandId = 0;
const pending = new Map();
const browserErrors = [];
socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  }
  if (message.method === "Runtime.exceptionThrown") {
    browserErrors.push(message.params.exceptionDetails.text);
  }
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
    browserErrors.push(message.params.args.map((argument) => argument.value ?? argument.description).join(" "));
  }
});

function command(method, params = {}) {
  const id = ++commandId;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function evaluate(expression, awaitPromise = false) {
  const result = await command("Runtime.evaluate", { expression, awaitPromise, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}

async function waitFor(expression, timeout = 15000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeout) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`Timed out waiting for: ${expression}`);
}

async function setViewport(width, height) {
  await command("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile: false });
}

async function navigate(url) {
  await command("Page.navigate", { url });
  await waitFor("document.readyState === 'complete'");
}

async function screenshot(filename) {
  const capture = await command("Page.captureScreenshot", { format: "png", fromSurface: true, captureBeyondViewport: false });
  await writeFile(path.join(outputDirectory, filename), Buffer.from(capture.data, "base64"));
}

await command("Page.enable");
await command("Runtime.enable");

await setViewport(1751, 898);
await navigate("http://127.0.0.1:5173/?open=first");
await waitFor("document.querySelectorAll('.poster-card').length >= 5 && document.querySelectorAll('.candidate').length === 1");
await waitFor("[...document.images].every((image) => image.complete && image.naturalWidth > 0)", 30000);
await evaluate("document.querySelector('.candidate:not(.selected)')?.click()");

const accordionStates = [];
for (const index of [1, 2, 3, 0]) {
  await evaluate(`document.querySelectorAll('.accordion-trigger')[${index}]?.click()`);
  await new Promise((resolve) => setTimeout(resolve, 220));
  accordionStates.push(await evaluate(`({ index: ${index}, openCount: document.querySelectorAll('.accordion.open').length, expanded: document.querySelectorAll('.accordion-trigger')[${index}]?.getAttribute('aria-expanded') })`));
}

const desktop = await evaluate(`({
  viewport: [innerWidth, innerHeight],
  drawer: (() => { const r = document.querySelector('.scrape-drawer').getBoundingClientRect(); return { x: r.x, width: r.width, height: r.height }; })(),
  posterCount: document.querySelectorAll('.poster-card').length,
  loadedImages: [...document.images].filter((image) => image.complete && image.naturalWidth > 0).length,
  imageCount: document.images.length,
  selectedCandidates: document.querySelectorAll('.candidate.selected').length,
  overflow: document.documentElement.scrollWidth > innerWidth,
  openAccordion: document.querySelector('.accordion.open .accordion-heading strong')?.textContent,
})`);
await screenshot("implementation-07.png");

const drawerRect = await evaluate(`(() => { const r = document.querySelector('.scrape-drawer').getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; })()`);
const drawerCapture = await command("Page.captureScreenshot", { format: "png", fromSurface: true, clip: { ...drawerRect, scale: 1 } });
await writeFile(path.join(outputDirectory, "implementation-07-drawer.png"), Buffer.from(drawerCapture.data, "base64"));

await navigate("http://127.0.0.1:5173/settings");
await waitFor("document.querySelector('.proxy-field input')?.value.startsWith('http://192.168.5.124:20181')");
await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent.includes('保存代理'))?.click()`);
await waitFor("document.querySelector('.proxy-actions')?.textContent.includes('代理配置已保存')");
const settings = await evaluate(`({
  proxy: document.querySelector('.proxy-field input')?.value,
  enabled: document.querySelector('.toggle-row input')?.checked,
  saved: document.querySelector('.proxy-actions')?.textContent.includes('代理配置已保存'),
  overflow: document.documentElement.scrollWidth > innerWidth,
})`);
await screenshot("implementation-07-settings.png");

await setViewport(390, 844);
await navigate("http://127.0.0.1:5173/?open=first");
await waitFor("document.querySelector('.scrape-drawer') && document.querySelectorAll('.poster-card').length >= 5 && document.querySelectorAll('.candidate').length === 1");
await waitFor("[...document.images].every((image) => image.complete && image.naturalWidth > 0)", 30000);
await evaluate("document.querySelector('.candidate:not(.selected)')?.click()");
await waitFor("document.querySelectorAll('.candidate.selected').length === 1");
await new Promise((resolve) => setTimeout(resolve, 500));
const mobile = await evaluate(`({
  viewport: [innerWidth, innerHeight],
  drawer: (() => { const r = document.querySelector('.scrape-drawer').getBoundingClientRect(); return { x: r.x, width: r.width, height: r.height }; })(),
  footer: (() => { const r = document.querySelector('.drawer-footer').getBoundingClientRect(); return { x: r.x, right: r.right, y: r.y, bottom: r.bottom }; })(),
  overflow: document.documentElement.scrollWidth > innerWidth,
  scrollWidth: document.documentElement.scrollWidth,
  wideElements: [...document.querySelectorAll('body *')].map((element) => { const r = element.getBoundingClientRect(); return { selector: element.className || element.tagName, left: r.left, right: r.right, width: r.width }; }).filter((entry) => entry.left < -0.5 || entry.right > innerWidth + 0.5).slice(0, 8),
  iconButtons: [...document.querySelectorAll('.icon-button')].map((element) => { const r = element.getBoundingClientRect(); return { parent: element.parentElement?.className, left: r.left, right: r.right }; }),
  loadedImages: [...document.images].filter((image) => image.complete && image.naturalWidth > 0).length,
  imageCount: document.images.length,
})`);
await screenshot("implementation-07-mobile.png");

await evaluate("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))");
await waitFor("!document.querySelector('.scrape-drawer')");
const escapeClosed = await evaluate("!document.querySelector('.scrape-drawer')");

console.log(JSON.stringify({ desktop, accordionStates, settings, mobile, escapeClosed, browserErrors }, null, 2));
socket.close();
