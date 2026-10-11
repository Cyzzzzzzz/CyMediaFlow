import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AutomationPage } from "./AutomationPage";
import { emptySubscription } from "./subscriptionForm";

function response(data: unknown) {
  return Promise.resolve(new Response(JSON.stringify({ data, request_id: "test" }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
}

describe("AutomationPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("keeps automation tasks under sub-tabs and explains release decisions", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/feeds")) return response([{ id: 1, name: "Hero RSS", url: "https://example.org/…", enabled: true, status: "connected", last_checked_at: null, last_error: null }]);
      if (url.endsWith("/subscriptions")) return response([]);
      if (url.endsWith("/releases")) return response([{ id: 7, feed_id: 1, title: "[ANi] Hero 01", analysis: { title: "Hero", episode: 1, season: 1, group: "ANi", resolution: "1080p", confidence: 90, warnings: [] }, decision: "skipped", reason: "字幕组与偏好不符" }]);
      if (url.endsWith("/downloads") || url.endsWith("/events")) return response([]);
      throw new Error(`Unexpected URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><AutomationPage /></QueryClientProvider>);

    expect(screen.getAllByRole("tab")).toHaveLength(6);
    fireEvent.click(screen.getByRole("tab", { name: "发布候选" }));
    expect(await screen.findByText("[ANi] Hero 01")).toBeTruthy();
    expect(screen.getByText("字幕组与偏好不符")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "下载任务" }));
    expect(await screen.findByText("还没有自动下载任务。")).toBeTruthy();
  });

  const feed = { id: 1, name: "Hero RSS", url: "https://example.org/…", enabled: true, status: "connected", last_checked_at: null, last_error: null };
  const rule = { ...emptySubscription(), id: 1, feed_id: 1, title: "Hero", source_title: "Hero", season: 2, aliases: ["Hero"], preferred_group: "ANi" };
  function mount() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={client}><AutomationPage /></QueryClientProvider>);
  }

  it("opens the shelf first and shares a cancel-safe editor with the rules tab", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/feeds")) return response([feed]);
      if (url.endsWith("/subscriptions/1") && init?.method === "PUT") return response(JSON.parse(String(init.body)));
      if (url.endsWith("/subscriptions")) return response([rule]);
      throw new Error(`Unexpected URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();
    expect(screen.getByRole("tab", { name: "订阅番剧" }).getAttribute("aria-selected")).toBe("true");
    const poster = await screen.findByRole("button", { name: "编辑 Hero 第 2 季" });
    fireEvent.click(poster);
    let dialog = screen.getByRole("dialog", { name: "编辑追番规则" });
    expect(dialog.querySelector("details[open]")).toBeNull();
    fireEvent.change(within(dialog).getByLabelText("作品标题"), { target: { value: "Not saved" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "追番规则" }));
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    dialog = screen.getByRole("dialog");
    expect((within(dialog).getByLabelText("作品标题") as HTMLInputElement).value).toBe("Hero");
    fireEvent.click(within(dialog).getByText("高级设置"));
    fireEvent.change(within(dialog).getByLabelText("集数偏移"), { target: { value: "-12" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "应用修改" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const saved = fetchMock.mock.calls.find(([url, options]) => String(url).endsWith("/subscriptions/1") && options?.method === "PUT");
    expect(JSON.parse(String(saved?.[1]?.body))).toMatchObject({ title: "Hero", season: 2, episode_offset: -12, feed_id: 1 });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("search") || String(url).includes("analyze") || String(url).includes("refresh"))).toBe(false);
  });

  it("only analyzes RSS on request and saves the confirmed rule, never on opening", async () => {
    const candidate = { rule, entry_count: 3, examples: ["[ANi] Hero - 13"], matches: [], warning: null };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/feeds") || url.endsWith("/subscriptions")) return response([]);
      if (url.endsWith("/feeds/analyze")) return response({ candidates: [candidate], total_entries: 3, unrecognized: 0, truncated: false });
      if (url.endsWith("/subscriptions/confirm")) return response({ created: 1, automation_enabled: false });
      throw new Error(`Unexpected URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();
    fireEvent.click(screen.getByRole("button", { name: "新增 RSS 订阅" }));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("analyze"))).toBe(false);
    fireEvent.change(screen.getByLabelText("RSS 地址"), { target: { value: "https://example.org/rss" } });
    fireEvent.click(screen.getByRole("button", { name: "解析 RSS" }));
    expect(await screen.findByText("RSS 解析结果")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("confirm"))).toBe(false);
    expect((screen.getByLabelText("作品标题") as HTMLInputElement).value).toBe("Hero");
    fireEvent.click(screen.getByRole("button", { name: "确认订阅" }));
    expect(await screen.findByText(/自动追番尚未开启/)).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("lets aggregate subscribers select only the intended candidate and edit it", async () => {
    const other = { ...rule, title: "Other", source_title: "Other" };
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/feeds") || url.endsWith("/subscriptions")) return response([]);
      if (url.endsWith("/feeds/analyze")) return response({ candidates: [rule, other].map((value) => ({ rule: value, entry_count: 1, examples: [], matches: [], warning: null })), total_entries: 2, unrecognized: 0, truncated: false });
      if (url.endsWith("/subscriptions/confirm")) return response({ created: 1, automation_enabled: true });
      throw new Error(`Unexpected URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();
    fireEvent.click(screen.getByRole("button", { name: "新增 RSS 订阅" }));
    fireEvent.change(screen.getByLabelText("RSS 地址"), { target: { value: "https://a.test/rss" } });
    fireEvent.click(screen.getByLabelText("聚合 RSS（一个源包含多部番剧）"));
    fireEvent.click(screen.getByRole("button", { name: "解析 RSS" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "订阅 Hero ANi" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "订阅 Other ANi" }));
    fireEvent.click(screen.getByRole("button", { name: /Other.*Season/ }));
    fireEvent.change(screen.getByLabelText("季度"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "确认订阅（1）" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const saved = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/subscriptions/confirm"));
    const payload = JSON.parse(String(saved?.[1]?.body));
    expect(payload.rules).toHaveLength(1);
    expect(payload.rules[0]).toMatchObject({ title: "Other", season: 3 });
  });

  it("groups same-work rules behind one poster and shows archived rules separately", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      if (String(input).endsWith("/feeds")) return response([feed]);
      return response([rule, { ...rule, id: 2, preferred_group: "LoliHouse" }, { ...rule, id: 3, title: "Archived", archived: true }]);
    }));
    mount();
    expect(await screen.findAllByRole("button", { name: "编辑 Hero 第 2 季" })).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "编辑 Archived 第 2 季" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "编辑 Hero 第 2 季" }));
    expect(screen.getByLabelText("此番剧有 2 条规则")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "已归档" }));
    expect(screen.getByRole("button", { name: "编辑 Archived 第 2 季" })).toBeTruthy();
  });

  it("requires explicit metadata search and keeps the original release alias", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/feeds")) return response([feed]);
      if (url.endsWith("/subscriptions")) return response([rule]);
      if (url.endsWith("/metadata/search")) return response([{ provider: "bangumi", external_id: "123", title: "中文作品", original_title: "Hero", year: 2026, image_url: "https://lain.bgm.tv/pic/cover/l/test.jpg" }]);
      if (url.endsWith("/subscriptions/1")) return response(rule);
      throw new Error(`Unexpected URL: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "编辑 Hero 第 2 季" }));
    fireEvent.click(screen.getByText("作品与海报匹配"));
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));
    fireEvent.click(await screen.findByRole("button", { name: /中文作品.*2026/ }));
    expect((screen.getByLabelText("作品标题") as HTMLInputElement).value).toBe("中文作品");
    fireEvent.click(screen.getByRole("button", { name: "应用修改" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const saved = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/subscriptions/1"));
    const payload = JSON.parse(String(saved?.[1]?.body));
    expect(payload).toMatchObject({ provider: "bangumi", provider_id: "123", aliases: ["Hero"], season: 2 });
  });
});
