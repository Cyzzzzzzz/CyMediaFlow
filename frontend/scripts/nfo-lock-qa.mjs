import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const endpoint = "http://127.0.0.1:9224";
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
    const promise = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) promise.reject(new Error(message.error.message));
    else promise.resolve(message.result);
  }
  if (message.method === "Runtime.exceptionThrown") browserErrors.push(message.params.exceptionDetails.text);
  if (message.method === "Runtime.consoleAPICalled" && message.params.type === "error") {
    browserErrors.push(message.params.args.map((argument) => argument.value ?? argument.description).join(" "));
  }
});
function command(method, params = {}) {
  const id = ++commandId;
  socket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}
async function evaluate(expression) {
  const result = await command("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
  return result.result.value;
}
async function waitFor(expression, timeout = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`Timed out waiting for ${expression}`);
}

await command("Page.enable");
await command("Runtime.enable");
await command("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
await command("Page.navigate", { url: "http://127.0.0.1:5173/?open=first" });
await waitFor("document.readyState === 'complete' && !!document.querySelector('.scrape-drawer')");
await evaluate("document.querySelectorAll('.accordion-trigger')[1]?.click()");
await waitFor("[...document.querySelectorAll('button')].some((button) => button.textContent.includes('编辑与锁定'))");
await evaluate("[...document.querySelectorAll('button')].find((button) => button.textContent.includes('编辑与锁定'))?.click()");
await waitFor("document.querySelectorAll('.nfo-edit-field').length >= 10");
await evaluate("document.querySelector('.nfo-policy-editor')?.scrollIntoView({ block: 'start' })");
await new Promise((resolve) => setTimeout(resolve, 250));

const state = await evaluate(`({
  editorFields: document.querySelectorAll('.nfo-edit-field').length,
  actionText: document.querySelector('.nfo-generation-card .preview-refresh')?.textContent,
  screenshotFallbackCopy: document.querySelector('.nfo-generation-card')?.textContent.includes('本地视频截图'),
  confirmationVisible: !!document.querySelector('.nfo-generation-confirm'),
  overflow: document.documentElement.scrollWidth > innerWidth,
})`);
const capture = await command("Page.captureScreenshot", { format: "png", fromSurface: true });
const outputDirectory = path.resolve(".data/design-qa");
await mkdir(outputDirectory, { recursive: true });
await writeFile(path.join(outputDirectory, "nfo-lock-editor-01.png"), Buffer.from(capture.data, "base64"));
console.log(JSON.stringify({ state, browserErrors }, null, 2));
socket.close();
