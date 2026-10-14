import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { accessApi, usePasskey, type Account } from "./accessApi";
import "./access.css";
import "../automation/automation.css";
import "../automation/subscriptions.css";

export function SecuritySettings() {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["access", "status"],
    queryFn: accessApi.status,
  });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const setup = useMutation({
    mutationFn: () => accessApi.setup(username, password),
    onSuccess: () => {
      setPassword("");
      void client.invalidateQueries({ queryKey: ["access"] });
    },
  });
  const logout = useMutation({
    mutationFn: accessApi.logout,
    onSuccess: () => {
      client.clear();
      window.location.reload();
    },
  });
  return (
    <section className="automation-panel security-settings">
      <h3>账号与访问</h3>
      {status.isPending ? (
        <p>正在读取…</p>
      ) : !status.data?.enabled ? (
        <details className="subscription-section">
          <summary>启用账号登录</summary>
          <form
            className="subscription-section-body automation-form"
            onSubmit={(e) => {
              e.preventDefault();
              setup.mutate();
            }}
          >
            <p className="automation-note">
              创建首个管理员后，所有页面和 API
              都需要登录。现有媒体和订阅仍由后台任务管理。
            </p>
            <label>
              管理员用户名
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
            <label>
              密码（至少 12 位）
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            <button className="primary-button" disabled={setup.isPending}>
              创建管理员并启用登录
            </button>
          </form>
        </details>
      ) : status.data.user ? (
        <>
          <div className="automation-panel-head">
            <p>
              当前账号：{status.data.user.username} · {status.data.user.role}
            </p>
            <button
              className="secondary-button"
              onClick={() => logout.mutate()}
            >
              退出登录
            </button>
          </div>
          {status.data.user.role === "admin" ? (
            <UserManagement current={status.data.user} />
          ) : null}
          <TokenSettings role={status.data.user.role} />
          <PasskeySettings admin={status.data.user.role === "admin"} />
        </>
      ) : (
        <p>请先登录。</p>
      )}
      {setup.error || status.error || logout.error ? (
        <p role="alert">
          {(setup.error ?? status.error ?? logout.error)?.message}
        </p>
      ) : null}
    </section>
  );
}

function UserManagement({ current }: { current: Account }) {
  const client = useQueryClient();
  const users = useQuery({
    queryKey: ["access", "users"],
    queryFn: accessApi.users,
  });
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [editing, setEditing] = useState<Account | null>(null);
  const done = () => {
    setPassword("");
    setEditing(null);
    void client.invalidateQueries({ queryKey: ["access"] });
  };
  const add = useMutation({
    mutationFn: () => accessApi.addUser(name, password, role),
    onSuccess: done,
  });
  const update = useMutation({
    mutationFn: (user: Account) =>
      accessApi.updateUser(user.id, {
        enabled: user.enabled ?? true,
        role: user.role,
        ...(password ? { password } : {}),
      }),
    onSuccess: done,
  });
  return (
    <details className="subscription-section">
      <summary>用户管理</summary>
      <div className="subscription-section-body automation-form">
        <p className="automation-note">
          管理员管理配置与账号；操作员处理媒体与追番；只读用户浏览内容。修改权限或密码会撤销该用户所有会话和令牌。
        </p>
        {users.data?.map((user) => (
          <article className="automation-card" key={user.id}>
            <div>
              <strong>
                {user.username}
                {user.id === current.id ? "（当前）" : ""}
              </strong>
              <span>
                {user.role} · {user.enabled ? "启用" : "停用"}
              </span>
            </div>
            <button
              className="quiet-button"
              onClick={() => {
                setEditing(user);
                setPassword("");
              }}
            >
              修改
            </button>
          </article>
        ))}
        {editing ? (
          <>
            <label>
              角色
              <select
                value={editing.role}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    role: e.target.value as Account["role"],
                  })
                }
              >
                <option value="viewer">只读</option>
                <option value="operator">操作员</option>
                <option value="admin">管理员</option>
              </select>
            </label>
            <label className="automation-check">
              <input
                type="checkbox"
                checked={editing.enabled}
                onChange={(e) =>
                  setEditing({ ...editing, enabled: e.target.checked })
                }
              />
              启用账号
            </label>
            <label>
              新密码（留空保留）
              <input
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <button
              className="primary-button"
              disabled={update.isPending}
              onClick={() => update.mutate(editing)}
            >
              保存账号
            </button>
            <button className="quiet-button" onClick={() => setEditing(null)}>
              取消修改
            </button>
          </>
        ) : (
          <>
            <label>
              新用户名
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label>
              初始密码
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </label>
            <label>
              角色
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                <option value="viewer">只读</option>
                <option value="operator">操作员</option>
                <option value="admin">管理员</option>
              </select>
            </label>
            <button
              className="secondary-button"
              disabled={!name || password.length < 12 || add.isPending}
              onClick={() => add.mutate()}
            >
              添加用户
            </button>
          </>
        )}
        {add.error || update.error || users.error ? (
          <p role="alert">
            {(add.error ?? update.error ?? users.error)?.message}
          </p>
        ) : null}
      </div>
    </details>
  );
}

function TokenSettings({ role }: { role: string }) {
  const client = useQueryClient();
  const tokens = useQuery({
    queryKey: ["access", "tokens"],
    queryFn: accessApi.tokens,
  });
  const [name, setName] = useState("");
  const [scope, setScope] = useState("read");
  const [days, setDays] = useState(90);
  const [token, setToken] = useState("");
  const add = useMutation({
    mutationFn: () => accessApi.token(name, scope, days),
    onSuccess: (data) => {
      setToken(data.token);
      void client.invalidateQueries({ queryKey: ["access", "tokens"] });
    },
  });
  const revoke = useMutation({
    mutationFn: accessApi.revoke,
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["access", "tokens"] }),
  });
  return (
    <details className="subscription-section">
      <summary>API Token 与 MCP</summary>
      <div className="subscription-section-body automation-form">
        <p className="automation-note">
          API 使用 Authorization: Bearer Token。MCP 地址：
          {window.location.origin}/api/v1/mcp。令牌只显示一次，撤销后立即失效。
        </p>
        <label>
          用途名称
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="例如：本地 MCP 客户端"
          />
        </label>
        <label>
          权限
          <select value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="read">只读</option>
            {role !== "viewer" ? (
              <option value="automation">自动追番操作</option>
            ) : null}
            {role === "admin" ? <option value="all">完整权限</option> : null}
          </select>
        </label>
        <label>
          有效天数
          <input
            type="number"
            min={1}
            max={365}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          />
        </label>
        <button
          className="secondary-button"
          disabled={!name || add.isPending}
          onClick={() => add.mutate()}
        >
          生成令牌
        </button>
        {token ? (
          <div>
            <label>
              新令牌（仅本次可见）
              <input
                readOnly
                value={token}
                onFocus={(e) => e.target.select()}
              />
            </label>
            <button className="quiet-button" onClick={() => setToken("")}>
              已保存，隐藏令牌
            </button>
          </div>
        ) : null}
        {tokens.data?.map((t) => (
          <article className="automation-card" key={t.id}>
            <div>
              <strong>{t.name}</strong>
              <span>
                {t.scope} · {new Date(t.expires_at).toLocaleDateString()} 到期
              </span>
            </div>
            <button
              className="quiet-button"
              onClick={() => revoke.mutate(t.id)}
            >
              撤销
            </button>
          </article>
        ))}
        {add.error || revoke.error || tokens.error ? (
          <p role="alert">
            {(add.error ?? revoke.error ?? tokens.error)?.message}
          </p>
        ) : null}
      </div>
    </details>
  );
}

function PasskeySettings({ admin }: { admin: boolean }) {
  const client = useQueryClient();
  const config = useQuery({
    queryKey: ["access", "passkey-config"],
    queryFn: accessApi.config,
    enabled: admin,
  });
  const keys = useQuery({
    queryKey: ["access", "passkeys"],
    queryFn: accessApi.passkeys,
  });
  const [origin, setOrigin] = useState("");
  const [name, setName] = useState("我的设备");
  useEffect(() => {
    if (config.data) setOrigin(config.data.origin);
  }, [config.data]);
  const save = useMutation({
    mutationFn: () => accessApi.saveConfig(origin),
    onSuccess: () => client.invalidateQueries({ queryKey: ["access"] }),
  });
  const register = useMutation({
    mutationFn: () => usePasskey(true, name),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["access", "passkeys"] }),
  });
  const remove = useMutation({
    mutationFn: accessApi.removePasskey,
    onSuccess: () =>
      client.invalidateQueries({ queryKey: ["access", "passkeys"] }),
  });
  return (
    <details className="subscription-section">
      <summary>Passkey 登录</summary>
      <div className="subscription-section-body automation-form">
        <p className="automation-note">
          通过 HTTPS 域名访问 NAS 才能使用 Passkey；局域网 HTTP IP
          地址仍可使用密码登录。
        </p>
        {admin ? (
          <>
            <label>
              网站地址
              <input
                value={origin}
                onChange={(e) => setOrigin(e.target.value)}
                placeholder="https://media.example.com"
              />
            </label>
            <button className="secondary-button" onClick={() => save.mutate()}>
              保存 Passkey 地址
            </button>
          </>
        ) : null}
        <label>
          设备名称
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button
          className="secondary-button"
          disabled={register.isPending}
          onClick={() => register.mutate()}
        >
          注册当前设备 Passkey
        </button>
        {keys.data?.map((k) => (
          <article className="automation-card" key={k.id}>
            <strong>{k.name}</strong>
            <button
              className="quiet-button"
              onClick={() => remove.mutate(k.id)}
            >
              移除
            </button>
          </article>
        ))}
        {save.error || register.error || remove.error || keys.error ? (
          <p role="alert">
            {
              (save.error ?? register.error ?? remove.error ?? keys.error)
                ?.message
            }
          </p>
        ) : null}
      </div>
    </details>
  );
}
