import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AddRssDialog } from "./AddRssDialog";
import { ReleaseReviewDialog } from "./ResourceSearchPanel";
import { emptySubscription } from "./subscriptionForm";
import type { Release } from "./types";

afterEach(() => vi.unstubAllGlobals());
const rule = { ...emptySubscription(), title: "Cyberpunk", source_title: "Cyberpunk", season: 2, allow_batch: true };
function response(data: unknown) {
  return Promise.resolve(new Response(JSON.stringify({ data }), { status: 200 }));
}
function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

it.each([true, false])("previews batch range without saving and preserves allow_batch=%s on confirmation", async (allowed) => {
  const success = vi.fn();
  const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/feeds/analyze")) return response({
      total_entries: 1, unrecognized: 0, truncated: false,
      candidates: [{ rule, entry_count: 1, batch_count: 1,
        episode_ranges: [{ season: 2, start: 1, end: 10 }],
        examples: ["Cyberpunk S02E01~10 1080p"], matches: [], warning: "元数据暂不可用，可手动编辑" }],
    });
    if (url.endsWith("/subscriptions/confirm")) return response({ created: 1, automation_enabled: false });
    throw new Error(`Unexpected URL: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  mount(<AddRssDialog onClose={vi.fn()} onSuccess={success} />);
  expect(fetchMock).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("RSS 地址"), { target: { value: "https://example.test/batch-rss" } });
  fireEvent.click(screen.getByRole("button", { name: "解析 RSS" }));
  expect(await screen.findByText(/识别到 1 条合集：S02E01–E10/)).toBeTruthy();
  expect(screen.getByText(/元数据暂不可用/)).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText("高级设置"));
  const toggle = screen.getByLabelText("允许合集（下载后逐文件核对剧集）") as HTMLInputElement;
  expect(toggle.checked).toBe(true);
  if (!allowed) fireEvent.click(toggle);
  if (!allowed) expect(screen.getByText(/当前未允许合集/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "确认订阅" }));
  await waitFor(() => expect(success).toHaveBeenCalledOnce());
  const saved = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/subscriptions/confirm"));
  expect(JSON.parse(String(saved?.[1]?.body)).rules[0]).toMatchObject({ season: 2, allow_batch: allowed, expected_episodes: null });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it("does not present a batch as episode one or allow download without batch permission", async () => {
  const release: Release = {
    id: 1, feed_id: 1, title: "Cyberpunk S02E01~10", decision: "review", reason: null,
    analysis: { title: "Cyberpunk", season: 2, episode: 1, episode_end: 10, group: null, resolution: "1080p", confidence: 90, warnings: ["MULTI_EPISODE_RELEASE"] },
  };
  const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    if (String(input).endsWith("/subscriptions")) return response([
      { ...rule, id: 1, feed_id: 1, allow_batch: false }, { ...rule, id: 2, feed_id: 1 },
    ]);
    if (String(input).endsWith("/download")) return response({ target_title: "Cyberpunk", season: 2, episode: null, confirmed: false });
    throw new Error(`Unexpected URL: ${input}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  mount(<ReleaseReviewDialog release={release} onClose={vi.fn()} />);
  await screen.findAllByRole("option", { name: /Cyberpunk/ });
  const selector = screen.getByLabelText("使用追番规则");
  fireEvent.change(selector, { target: { value: "1" } });
  expect(screen.queryByLabelText("目标集号（Emby）")).toBeNull();
  expect((screen.getByRole("button", { name: "预览下载" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(selector, { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "预览下载" }));
  expect(await screen.findByText(/S2 · 合集（逐文件映射）/)).toBeTruthy();
  const request = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/download"));
  expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ episode: null, confirm: false });
});
