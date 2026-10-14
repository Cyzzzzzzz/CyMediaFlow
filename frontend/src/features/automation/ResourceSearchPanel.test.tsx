import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { ResourceSearchPanel } from "./ResourceSearchPanel";
import { emptySubscription } from "./subscriptionForm";

afterEach(() => vi.unstubAllGlobals());

it("opens cached results without searching and previews the offset before download", async () => {
  const calls: { url: string; body: Record<string, unknown> }[] = [];
  const release = {
    id: 1,
    title: "[ANi] Hero - 13 [1080p]",
    analysis: { title: "Hero", episode: 13, group: "ANi", resolution: "1080p" },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input, init) => {
      const url = String(input);
      let data: unknown = {};
      if (init?.method === "POST")
        calls.push({ url, body: JSON.parse(init.body) });
      if (url.endsWith("/features/settings"))
        data = { sources: [{ id: "pt", name: "Custom PT", enabled: true }] };
      else if (url.endsWith("/settings"))
        data = { default_exclude_keywords: [] };
      else if (url.endsWith("/subscriptions"))
        data = [
          {
            ...emptySubscription(),
            id: 5,
            title: "Hero",
            season: 2,
            episode_offset: -12,
          },
        ];
      else if (url.endsWith("/search"))
        data = { query: "Hero", items: [release], feed_id: 3 };
      else if (url.endsWith("/download"))
        data = {
          target_title: "Hero",
          season: 2,
          episode: 1,
          confirmed: !!JSON.parse(init.body).confirm,
        };
      return new Response(JSON.stringify({ data }), { status: 200 });
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <ResourceSearchPanel />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  expect(await screen.findByText(release.title)).toBeTruthy();
  expect(calls).toEqual([]);
  await user.click(screen.getByRole("button", { name: "下载" }));
  await user.selectOptions(await screen.findByLabelText("使用追番规则"), "5");
  expect(
    (screen.getByLabelText("目标集号（Emby）") as HTMLInputElement).value,
  ).toBe("1");
  await user.click(screen.getByRole("button", { name: "预览下载" }));
  await screen.findByRole("button", { name: "确认下载" });
  expect(calls[0].body).toMatchObject({
    subscription_id: 5,
    episode: 1,
    confirm: false,
  });
  await user.click(screen.getByRole("button", { name: "确认下载" }));
  await screen.findByText("已在下载器确认创建");
  expect(calls[1].body.confirm).toBe(true);
  expect(calls.some((c) => c.url.endsWith("/search"))).toBe(false);
  await user.keyboard("{Escape}");
  await user.type(screen.getByLabelText("资源搜索关键词"), "Hero");
  await user.click(screen.getByRole("button", { name: "搜索资源" }));
  await waitFor(() =>
    expect(calls[2].body).toMatchObject({ source_id: "pt", query: "Hero" }),
  );
});
