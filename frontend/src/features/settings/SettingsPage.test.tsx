import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SettingsView } from "../../api/types";
import { SettingsPage } from "./SettingsPage";

const settings: SettingsView = {
  media_root: "/media",
  allowed_media_root: "/media",
  allowed_media_roots: ["/media"],
  media_root_exists: true,
  media_root_readable: true,
  bangumi_configured: true,
  bangumi_api_url: "https://api.bgm.tv",
  tmdb_configured: true,
  tmdb_api_url: "https://api.themoviedb.org/3",
  operation_mode: "nfo_managed_update",
  bangumi_proxy_enabled: true,
  bangumi_proxy_url: "http://192.168.5.124:20181/",
  tmdb_proxy_enabled: false,
  tmdb_proxy_url: null,
  episode_artwork_fallback_enabled: true,
  episode_artwork_capture_percent: 25,
  ffprobe_path: "ffprobe",
  ffprobe_available: true,
  ffmpeg_path: "ffmpeg",
  ffmpeg_available: true,
  ignore_marker_enabled: true,
  ignore_folder_patterns: ["SP"],
  ignore_marker_matched_count: 0,
  ignore_marker_created_count: 0,
  ignore_marker_existing_count: 0,
  ignore_marker_failed_count: 0,
};

function response(data: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads and saves default exclusion tags without submitting media settings", async () => {
    const user = userEvent.setup();
    const config = { enabled: false, interval_minutes: 15, qb_url: "", qb_username: "", qb_save_root: "", rss_proxy_url: "", qb_password_configured: false, default_exclude_keywords: ["720p"] };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/v1/automation/settings") return response({ data: init?.method === "PUT" ? { ...config, ...JSON.parse(String(init.body)) } : config });
      return response({ data: settings });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();
    await screen.findByRole("button", { name: "编辑排除词 720p" });
    await user.type(screen.getByLabelText("默认排除词"), "繁日{Enter}合集");
    // The final pending word is committed on blur before the save handler executes.
    await user.click(screen.getByRole("button", { name: "保存自动追番设置" }));
    await screen.findByText("设置已保存");
    const saved = fetchMock.mock.calls.filter(([, init]) => init?.method === "PUT");
    expect(saved).toHaveLength(1);
    expect(saved[0][0]).toBe("/api/v1/automation/settings");
    expect(JSON.parse(String(saved[0][1]?.body)).default_exclude_keywords).toEqual(["720p", "繁日", "合集"]);
  });

  it("shows the effective media root after switching it", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/v1/automation/settings") return response({ data: { enabled: false, interval_minutes: 15, qb_url: "", qb_username: "", qb_save_root: "", rss_proxy_url: "", qb_password_configured: false }, request_id: "automation" });
      return init?.method === "PUT"
        ? response({ data: { ...settings, media_root: "/media/anime" }, request_id: "put" })
        : response({ data: settings, request_id: "get" });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    const input = await screen.findByDisplayValue("/media");
    fireEvent.change(input, { target: { value: "anime" } });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    expect(await screen.findByText("设置已生效，正在扫描 /media/anime")).toBeTruthy();
    const request = fetchMock.mock.calls.find((call) => call[1]?.method === "PUT")!;
    expect(request[0]).toBe("/api/v1/settings");
    expect(JSON.parse(String(request[1]?.body)).media_root).toBe("anime");
  });

  it("shows the backend path validation message", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input) === "/api/v1/automation/settings") return response({ data: { enabled: false, interval_minutes: 15, qb_url: "", qb_username: "", qb_save_root: "", rss_proxy_url: "", qb_password_configured: false }, request_id: "automation" });
      return init?.method === "PUT"
        ? response({
            error: {
              code: "MEDIA_ROOT_OUTSIDE_ALLOWED_ROOT",
              message: "Docker/NAS 请填写容器路径 /media 或其子目录",
              details: { allowed_media_root: "/media" },
            },
            request_id: "put",
          }, 400)
        : response({ data: settings, request_id: "get" });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    const input = await screen.findByDisplayValue("/media");
    fireEvent.change(input, { target: { value: "/volume2/media" } });
    fireEvent.click(screen.getByRole("button", { name: "保存设置" }));

    await waitFor(() => expect(screen.getByText("Docker/NAS 请填写容器路径 /media 或其子目录")).toBeTruthy());
  });
});
