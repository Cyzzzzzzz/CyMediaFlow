import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AutomationPage } from "./AutomationPage";

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

    expect(screen.getAllByRole("tab")).toHaveLength(5);
    fireEvent.click(screen.getByRole("tab", { name: "发布候选" }));
    expect(await screen.findByText("[ANi] Hero 01")).toBeTruthy();
    expect(screen.getByText("字幕组与偏好不符")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "下载任务" }));
    expect(await screen.findByText("还没有自动下载任务。")).toBeTruthy();
  });
});
