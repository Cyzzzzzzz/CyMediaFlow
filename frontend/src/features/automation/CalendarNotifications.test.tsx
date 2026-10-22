import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CalendarPanel } from "./CalendarNotifications";
import { SubscriptionFields } from "./SubscriptionFields";
import { featureApi } from "./featureApi";
import { emptySubscription } from "./subscriptionForm";
import type { Subscription } from "./types";

afterEach(() => vi.restoreAllMocks());

const monday: Subscription = {
  ...emptySubscription(), id: 1, feed_id: 1, title: "黑暗召唤师在地下恋爱中",
  air_weekday: 0, local_poster_url: "/api/v1/images/test-poster",
  poster_url: "https://lain.bgm.tv/pic/cover/l/test.jpg",
};
const sunday: Subscription = { ...monday, id: 2, title: "周日的番剧", air_weekday: 6 };
const pending: Subscription = { ...monday, id: 3, title: "尚未确定放送日的番剧", air_weekday: null, poster_url: null, local_poster_url: null };

function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

it("keeps compact cards grouped by weekday and opens the selected rule", async () => {
  const query = vi.spyOn(featureApi, "calendar").mockResolvedValue({ items: [monday, sunday, pending], updated_at: null });
  const refresh = vi.spyOn(featureApi, "refreshCalendar");
  const edit = vi.fn();
  mount(<CalendarPanel onEdit={edit} />);

  const card = await screen.findByRole("button", { name: `编辑追番规则：${monday.title}` });
  expect(screen.getAllByRole("region")).toHaveLength(8);
  expect(within(screen.getByRole("region", { name: "周一" })).getByRole("button")).toBe(card);
  expect(within(screen.getByRole("region", { name: "周日" })).getByRole("button").title).toBe(sunday.title);
  expect(within(screen.getByRole("region", { name: "待定" })).getByRole("button").title).toBe(pending.title);
  expect(card.querySelector(".calendar-anime-title")?.textContent).toBe(monday.title);
  expect(card.querySelector(".subscription-poster")).toBeTruthy();
  fireEvent.click(card);
  expect(edit).toHaveBeenCalledExactlyOnceWith(monday);
  expect(query).toHaveBeenCalledOnce();
  expect(refresh).not.toHaveBeenCalled();
});

it("keeps local artwork first and falls back to a remote poster then the placeholder", async () => {
  vi.spyOn(featureApi, "calendar").mockResolvedValue({ items: [monday], updated_at: null });
  mount(<CalendarPanel onEdit={vi.fn()} />);
  const img = await screen.findByRole("img", { name: `${monday.title} 海报` });
  expect(img.getAttribute("src")).toBe(monday.local_poster_url);
  fireEvent.error(img);
  expect(img.getAttribute("src")).toContain("/api/v1/automation/poster?url=");
  fireEvent.error(img);
  const card = screen.getByRole("button", { name: `编辑追番规则：${monday.title}` });
  expect(card.querySelector(".subscription-poster-placeholder")).toBeTruthy();
  expect(card.querySelector(".calendar-anime-title")?.textContent).toBe(monday.title);
});

it("only refreshes remote calendar data after an explicit click and updates its grouping", async () => {
  vi.spyOn(featureApi, "calendar").mockResolvedValue({ items: [pending], updated_at: null });
  const refresh = vi.spyOn(featureApi, "refreshCalendar").mockResolvedValue({ items: [{ ...pending, air_weekday: 1 }], updated_at: "2026-10-22" });
  mount(<CalendarPanel onEdit={vi.fn()} />);
  await screen.findByRole("button", { name: `编辑追番规则：${pending.title}` });
  expect(refresh).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "更新 Bangumi 日历" }));
  await waitFor(() => expect(within(screen.getByRole("region", { name: "周二" })).getByRole("button").title).toBe(pending.title));
  expect(within(screen.getByRole("region", { name: "待定" })).queryByRole("button")).toBeNull();
  expect(refresh).toHaveBeenCalledOnce();
});

it("keeps the previous calendar available when a manual refresh fails", async () => {
  vi.spyOn(featureApi, "calendar").mockResolvedValue({ items: [monday], updated_at: null });
  vi.spyOn(featureApi, "refreshCalendar").mockRejectedValue(new Error("日历服务暂不可用"));
  mount(<CalendarPanel onEdit={vi.fn()} />);
  await screen.findByRole("button", { name: `编辑追番规则：${monday.title}` });
  fireEvent.click(screen.getByRole("button", { name: "更新 Bangumi 日历" }));
  expect((await screen.findByRole("alert")).textContent).toContain("日历服务暂不可用");
  expect(screen.getByRole("button", { name: `编辑追番规则：${monday.title}` })).toBeTruthy();
});

it("explains the saved directory scope without moving or modifying an existing task", () => {
  const change = vi.fn();
  mount(<SubscriptionFields value={monday} onChange={change} />);
  const input = screen.getByLabelText("下载目录名");
  const hint = document.getElementById(input.getAttribute("aria-describedby")!);
  expect(hint?.textContent).toContain("已有任务（含重试）保留提交时的配置");
  fireEvent.change(input, { target: { value: "黑暗召唤师在地下恋爱中" } });
  expect(change).toHaveBeenCalledWith({ ...monday, folder_name: "黑暗召唤师在地下恋爱中" });
});
