import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AddRssDialog } from "./AddRssDialog";

afterEach(() => vi.unstubAllGlobals());

it.each([true, false])("shows failed RSS diagnostics without fetching logs automatically (id=%s)", async (hasId) => {
  const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({
    data: null,
    error: { code: "RSS_UNAVAILABLE", message: "RSS 连接建立或传输失败，请稍后重试", details: { reason: "CONNECTION" } },
    ...(hasId ? { request_id: "req_test_123" } : {}),
  }), { status: 503 })));
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AddRssDialog onClose={vi.fn()} onSuccess={vi.fn()} /></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText("RSS 地址"), { target: { value: "https://example.test/feed" } });
  fireEvent.click(screen.getByRole("button", { name: "解析 RSS" }));
  expect((await screen.findByRole("alert")).textContent).toContain("RSS 连接建立或传输失败");
  if (hasId) {
    expect(screen.getByText(/请求编号：req_test_123/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "查看异常日志" }).getAttribute("href")).toBe("/api/v1/system/error-logs?request_id=req_test_123");
  } else {
    expect(screen.queryByRole("link", { name: "查看异常日志" })).toBeNull();
  }
  expect(fetchMock).toHaveBeenCalledOnce();
});
