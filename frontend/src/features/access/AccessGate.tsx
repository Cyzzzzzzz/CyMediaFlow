import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { accessApi, usePasskey } from "./accessApi";
import "./access.css";

export function AccessGate({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["access", "status"],
    queryFn: accessApi.status,
    retry: false,
  });
  useEffect(() => {
    const update = () => {
      void client.invalidateQueries({ queryKey: ["access", "status"] });
    };
    window.addEventListener("cymf-auth-expired", update);
    return () => window.removeEventListener("cymf-auth-expired", update);
  }, [client]);
  if (status.isPending)
    return <div className="page-state">正在连接 CyMediaFlow…</div>;
  if (status.error)
    return (
      <div className="page-state">
        <p>{status.error.message}</p>
        <button
          className="secondary-button"
          onClick={() => void status.refetch()}
        >
          重新连接
        </button>
      </div>
    );
  if (status.data.enabled && !status.data.user)
    return <LoginForm passkey={status.data.passkey_configured} />;
  return children;
}

function LoginForm({ passkey }: { passkey: boolean }) {
  const client = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const done = async () => {
    // Drop the previous user's cached data without detaching the gate's active observer.
    client.removeQueries({
      predicate: (query) =>
        query.queryKey[0] !== "access" || query.queryKey[1] !== "status",
    });
    await client.invalidateQueries({ queryKey: ["access", "status"] });
  };
  const login = useMutation({
    mutationFn: () => accessApi.login(username, password),
    onSuccess: done,
  });
  const key = useMutation({
    mutationFn: () => usePasskey(false),
    onSuccess: done,
  });
  return (
    <main className="access-login">
      <form
        className="access-login-card"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate();
        }}
      >
        <img src="/favicon.svg" alt="" width={42} height={42} />
        <h1>CyMediaFlow</h1>
        <p>登录你的媒体空间</p>
        <label>
          用户名
          <input
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>
        <label>
          密码
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button className="primary-button" disabled={login.isPending}>
          登录
        </button>
        {passkey ? (
          <button
            className="secondary-button"
            type="button"
            disabled={key.isPending}
            onClick={() => key.mutate()}
          >
            使用 Passkey 登录
          </button>
        ) : null}
        {login.error || key.error ? (
          <p role="alert">{(login.error ?? key.error)?.message}</p>
        ) : null}
      </form>
    </main>
  );
}
