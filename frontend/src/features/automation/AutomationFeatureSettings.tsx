import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  featureApi,
  post,
  type FeatureSettings,
  type Source,
} from "./featureApi";

type Form = FeatureSettings & {
  aria2_secret: string;
  webhook_url: string;
  webhook_secret: string;
  llm_api_key: string;
  clear_aria2_secret: boolean;
  clear_webhook_secret: boolean;
  clear_llm_api_key: boolean;
};
export function AutomationFeatureSettings() {
  const client = useQueryClient();
  const config = useQuery({
    queryKey: ["automation", "features"],
    queryFn: featureApi.settings,
  });
  const [form, setForm] = useState<Form | null>(null);
  const version = useQuery({
    queryKey: ["automation", "version"],
    queryFn: featureApi.version,
  });
  useEffect(() => {
    if (config.data)
      setForm({
        ...config.data,
        aria2_secret: "",
        webhook_url: "",
        webhook_secret: "",
        llm_api_key: "",
        clear_aria2_secret: false,
        clear_webhook_secret: false,
        clear_llm_api_key: false,
      });
  }, [config.data]);
  const save = useMutation({
    mutationFn: () =>
      featureApi.saveSettings({
        ...form,
        aria2_secret: form!.aria2_secret || null,
        webhook_url: form!.webhook_url || null,
        webhook_secret: form!.webhook_secret || null,
        llm_api_key: form!.llm_api_key || null,
      }),
    onSuccess: (data) => client.setQueryData(["automation", "features"], data),
  });
  const test = useMutation({
    mutationFn: (target: string) =>
      post<{ version?: string; sent?: boolean }>(target),
  });
  const check = useMutation({
    mutationFn: featureApi.checkVersion,
    onSuccess: (data) => client.setQueryData(["automation", "version"], data),
  });
  if (!form)
    return (
      <p className="automation-note">
        {config.error?.message ?? "正在读取扩展设置…"}
      </p>
    );
  const set = <K extends keyof Form>(key: K, value: Form[K]) =>
    setForm({ ...form, [key]: value });
  const setSource = (index: number, values: Partial<Source>) =>
    set(
      "sources",
      form.sources.map((s, i) => (i === index ? { ...s, ...values } : s)),
    );
  return (
    <section className="automation-panel feature-settings">
      <h3>自动追番扩展</h3>
      <label className="automation-check">
        <input
          type="checkbox"
          checked={form.calendar_auto_refresh ?? false}
          onChange={(e) => set("calendar_auto_refresh", e.target.checked)}
        />
        每日更新订阅放送日历
      </label>
      <details className="subscription-section">
        <summary>资源搜索站点</summary>
        <div className="subscription-section-body automation-form">
          {form.sources.map((s, i) => (
            <fieldset className="feature-source" key={i}>
              <legend>{s.name || "新搜索源"}</legend>
              <div className="automation-form-grid">
                <label>
                  标识
                  <input
                    value={s.id}
                    onChange={(e) => setSource(i, { id: e.target.value })}
                    placeholder="my-site"
                  />
                </label>
                <label>
                  名称
                  <input
                    value={s.name}
                    onChange={(e) => setSource(i, { name: e.target.value })}
                  />
                </label>
              </div>
              <label>
                搜索地址
                <input
                  value={s.url ?? ""}
                  onChange={(e) =>
                    setSource(i, { url: e.target.value || null })
                  }
                  placeholder={
                    s.address
                      ? `${s.address} · 留空保留原地址`
                      : "https://example.com/rss?q={query}"
                  }
                />
              </label>
              <label>
                类型
                <select
                  value={s.kind}
                  onChange={(e) =>
                    setSource(i, { kind: e.target.value as Source["kind"] })
                  }
                >
                  <option value="rss">RSS 模板（包含 {"{query}"}）</option>
                  <option value="torznab">Torznab / PT 索引器 API</option>
                </select>
              </label>
              {s.kind === "torznab" ? (
                <label>
                  API Key
                  <input
                    type="password"
                    value={s.api_key ?? ""}
                    onChange={(e) =>
                      setSource(i, { api_key: e.target.value || null })
                    }
                    placeholder={
                      s.api_key_configured
                        ? "已配置，留空保留"
                        : "索引器 API Key"
                    }
                  />
                </label>
              ) : null}
              <div className="automation-actions">
                <label className="automation-check">
                  <input
                    type="checkbox"
                    checked={s.enabled}
                    onChange={(e) =>
                      setSource(i, { enabled: e.target.checked })
                    }
                  />
                  启用
                </label>
                <button
                  className="quiet-button"
                  onClick={() =>
                    set(
                      "sources",
                      form.sources.filter((_, n) => n !== i),
                    )
                  }
                >
                  移除搜索源
                </button>
              </div>
            </fieldset>
          ))}
          <button
            className="secondary-button"
            onClick={() =>
              set("sources", [
                ...form.sources,
                {
                  id: `custom-${form.sources.length + 1}`,
                  name: "自定义",
                  kind: "rss",
                  enabled: true,
                  url: "",
                },
              ])
            }
          >
            添加搜索源
          </button>
          <p className="automation-note">
            PT 通过支持 Torznab
            的索引器接入；地址中的私密参数仅保存，接口不回传。
          </p>
        </div>
      </details>
      <details className="subscription-section">
        <summary>aria2 下载器</summary>
        <div className="subscription-section-body automation-form">
          <label>
            RPC 地址
            <input
              value={form.aria2_url}
              onChange={(e) => set("aria2_url", e.target.value)}
              placeholder="http://nas:6800/jsonrpc"
            />
          </label>
          <label>
            RPC 密钥
            <input
              type="password"
              value={form.aria2_secret}
              onChange={(e) => set("aria2_secret", e.target.value)}
              placeholder={
                form.aria2_secret_configured ? "已配置，留空保留" : "secret"
              }
            />
          </label>
          <label className="automation-check">
            <input
              type="checkbox"
              checked={form.clear_aria2_secret}
              onChange={(e) => set("clear_aria2_secret", e.target.checked)}
            />
            清除已保存密钥
          </label>
          <label>
            保存根目录
            <input
              value={form.aria2_save_root}
              onChange={(e) => set("aria2_save_root", e.target.value)}
              placeholder="/downloads/Bangumi"
            />
          </label>
          <p className="automation-note">
            与媒体目录映射到同一存储。在规则内选择
            aria2。完成后用硬链接生成标准名，保留下载器的源文件。
          </p>
          <button
            className="secondary-button"
            disabled={test.isPending}
            onClick={() => test.mutate("/aria2/test")}
          >
            测试 aria2（已保存配置）
          </button>
        </div>
      </details>
      <details className="subscription-section">
        <summary>外部通知</summary>
        <div className="subscription-section-body automation-form">
          <label className="automation-check">
            <input
              type="checkbox"
              checked={form.webhook_enabled}
              onChange={(e) => set("webhook_enabled", e.target.checked)}
            />
            启用 Webhook 通知
          </label>
          <label>
            Webhook 地址
            <input
              type="password"
              value={form.webhook_url}
              onChange={(e) => set("webhook_url", e.target.value)}
              placeholder={
                form.webhook_url_configured
                  ? "已配置，留空保留"
                  : "https://example.com/notify"
              }
            />
          </label>
          <label>
            签名密钥
            <input
              type="password"
              value={form.webhook_secret}
              onChange={(e) => set("webhook_secret", e.target.value)}
              placeholder={
                form.webhook_secret_configured
                  ? "已配置，留空保留"
                  : "可选，用于校验通知来源"
              }
            />
          </label>
          <label className="automation-check">
            <input
              type="checkbox"
              checked={form.clear_webhook_secret}
              onChange={(e) => set("clear_webhook_secret", e.target.checked)}
            />
            清除签名密钥
          </label>
          <div className="feature-event-options">
            {[
              ["download_added", "创建下载"],
              ["organized", "整理完成"],
              ["review", "待审核"],
              ["download_error", "下载失败"],
              ["rss_error", "RSS 失败"],
              ["revision", "修订替换"],
            ].map(([key, label]) => (
              <label className="automation-check" key={key}>
                <input
                  type="checkbox"
                  checked={form.webhook_events.includes(key)}
                  onChange={(e) =>
                    set(
                      "webhook_events",
                      e.target.checked
                        ? [...form.webhook_events, key]
                        : form.webhook_events.filter((k) => k !== key),
                    )
                  }
                />
                {label}
              </label>
            ))}
          </div>
          <button
            className="secondary-button"
            disabled={test.isPending}
            onClick={() => test.mutate("/notifications/test")}
          >
            发送测试通知（已保存配置）
          </button>
        </div>
      </details>
      <details className="subscription-section">
        <summary>LLM 辅助解析</summary>
        <div className="subscription-section-body automation-form">
          <label className="automation-check">
            <input
              type="checkbox"
              checked={form.llm_enabled}
              onChange={(e) => set("llm_enabled", e.target.checked)}
            />
            启用辅助解析
          </label>
          <label>
            兼容服务地址
            <input
              value={form.llm_url}
              onChange={(e) => set("llm_url", e.target.value)}
              placeholder="https://provider.example/v1"
            />
          </label>
          <label>
            模型
            <input
              value={form.llm_model}
              onChange={(e) => set("llm_model", e.target.value)}
            />
          </label>
          <label>
            API Key
            <input
              type="password"
              value={form.llm_api_key}
              onChange={(e) => set("llm_api_key", e.target.value)}
              placeholder={
                form.llm_api_key_configured ? "已配置，留空保留" : "API Key"
              }
            />
          </label>
          <label className="automation-check">
            <input
              type="checkbox"
              checked={form.clear_llm_api_key}
              onChange={(e) => set("clear_llm_api_key", e.target.checked)}
            />
            清除 API Key
          </label>
          <p className="automation-note">
            使用兼容 Chat Completions
            的服务。点击发布审核中的“辅助解析”才发送该条发布标题；建议需要人工核对。
          </p>
        </div>
      </details>
      <details className="subscription-section">
        <summary>版本检查</summary>
        <div className="subscription-section-body">
          <p className="automation-note">
            当前：{version.data?.current ?? "未知"}
            <br />
            远程：{version.data?.latest ?? "尚未检查"}
          </p>
          <label className="automation-check">
            <input
              type="checkbox"
              checked={form.version_auto_check}
              onChange={(e) => set("version_auto_check", e.target.checked)}
            />
            每日检查 GitHub main
          </label>
          <button
            className="secondary-button"
            disabled={check.isPending}
            onClick={() => check.mutate()}
          >
            检查更新
          </button>
          {version.data?.url ? (
            <a href={version.data.url} target="_blank" rel="noreferrer">
              查看变更
            </a>
          ) : null}
          <p className="automation-note">
            检查不会更新容器。升级继续使用 NAS 更新脚本。
          </p>
        </div>
      </details>
      <div className="automation-actions">
        <button
          className="primary-button"
          onClick={() => save.mutate()}
          disabled={save.isPending}
        >
          保存扩展设置
        </button>
        {save.isSuccess ? <span role="status">设置已保存</span> : null}
      </div>
      {test.isSuccess ? (
        <p role="status">{test.data.version || "测试通知已发送"}</p>
      ) : null}
      {save.error || test.error || check.error ? (
        <p role="alert" className="automation-note error">
          {(save.error ?? test.error ?? check.error)?.message}
        </p>
      ) : null}
    </section>
  );
}
