import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AccessGate } from "./AccessGate";

afterEach(() => vi.unstubAllGlobals());

it("refreshes the active gate and clears previous-user data after login", async () => {
  let loggedIn = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, init) => {
      if (String(url).endsWith("/login")) {
        expect(JSON.parse(init.body).username).toBe("admin");
        loggedIn = true;
      }
      return new Response(
        JSON.stringify({
          data: {
            enabled: true,
            passkey_configured: false,
            user: loggedIn
              ? { id: "1", username: "admin", role: "admin" }
              : null,
          },
        }),
        { status: 200 },
      );
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  client.setQueryData(["automation", "notifications"], { previousUser: true });
  render(
    <QueryClientProvider client={client}>
      <AccessGate>
        <h1>媒体首页</h1>
      </AccessGate>
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("用户名"), "admin");
  await user.type(screen.getByLabelText("密码"), "test-password-long");
  await user.click(screen.getByRole("button", { name: "登录" }));
  expect(await screen.findByRole("heading", { name: "媒体首页" })).toBeTruthy();
  expect(client.getQueryData(["automation", "notifications"])).toBeUndefined();
});
