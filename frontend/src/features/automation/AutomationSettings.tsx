import { Rss } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { apiRequest } from "../../api/client";
import { KeywordTags } from "../../components/KeywordTags";
import { automationApi } from "./api";
import type { AutomationConfig } from "./types";
import "./automation.css";

type Form = Omit<AutomationConfig, "qb_password_configured"> & {
  qb_password: string; clear_qb_password: boolean;
};
const blank: Form = {
  enabled: false, interval_minutes: 15, qb_url: "", qb_username: "",
  qb_save_root: "", rss_proxy_url: "", qb_password: "", clear_qb_password: false,
  default_exclude_keywords: [],
};

export function AutomationSettings() {
  const client = useQueryClient();
  const [form, setForm] = useState<Form>(blank);
  const config = useQuery({ queryKey: ["automation", "settings"], queryFn: automationApi.settings });
  const save = useMutation({
    mutationFn: () => apiRequest<AutomationConfig>("/api/v1/automation/settings", { method: "PUT", body: JSON.stringify({ ...form, qb_password: form.qb_password || null }) }),
    onSuccess: (data) => {
      client.setQueryData(["automation", "settings"], data);
      setForm((old) => ({ ...old, qb_password: "", clear_qb_password: false }));
    },
  });
  const test = useMutation({ mutationFn: () => apiRequest<{ version: string }>("/api/v1/automation/downloader/test", { method: "POST" }) });
  useEffect(() => {
    if (!config.data) return;
    setForm({
      enabled: config.data.enabled, interval_minutes: config.data.interval_minutes,
      qb_url: config.data.qb_url, qb_username: config.data.qb_username,
      qb_save_root: config.data.qb_save_root, rss_proxy_url: config.data.rss_proxy_url,
      qb_password: "", clear_qb_password: false,
      default_exclude_keywords: config.data.default_exclude_keywords ?? [],
    });
  }, [config.data]);
  const update = <K extends keyof Form>(key: K, value: Form[K]) => setForm((old) => ({ ...old, [key]: value }));

  return <section className="proxy-card settings-section">
    <div className="proxy-title"><span className="setting-icon"><Rss size={22} /></span><span><strong>RSS 与 qBittorrent</strong><small>下载链路默认关闭；启用后按规则自动处理</small></span></div>
    <div className="settings-section-body">
      <label className="toggle-row"><span>启用自动追番</span><input type="checkbox" checked={form.enabled} onChange={(e) => update("enabled", e.target.checked)} /></label>
      <label className="proxy-field"><span>RSS 检查间隔（分钟）</span><input type="number" min="1" max="1440" value={form.interval_minutes} onChange={(e) => update("interval_minutes", Number(e.target.value))} /></label>
      <label className="proxy-field"><span>qBittorrent Web API 地址</span><input value={form.qb_url} onChange={(e) => update("qb_url", e.target.value)} placeholder="http://192.168.5.124:8080" /></label>
      <label className="proxy-field"><span>用户名</span><input value={form.qb_username} onChange={(e) => update("qb_username", e.target.value)} autoComplete="off" /></label>
      <label className="proxy-field"><span>密码</span><input type="password" value={form.qb_password} onChange={(e) => update("qb_password", e.target.value)} placeholder={config.data?.qb_password_configured ? "已配置；留空保持不变" : "请输入 qBittorrent 密码"} autoComplete="new-password" /></label>
      {config.data?.qb_password_configured ? <label className="toggle-row"><span>清除已保存的下载器密码</span><input type="checkbox" checked={form.clear_qb_password} onChange={(e) => update("clear_qb_password", e.target.checked)} /></label> : null}
      <label className="proxy-field"><span>下载器视角的保存根目录</span><input value={form.qb_save_root} onChange={(e) => update("qb_save_root", e.target.value)} placeholder="/downloads/Bangumi" /></label>
      <label className="proxy-field"><span>RSS 代理（可选）</span><input value={form.rss_proxy_url} onChange={(e) => update("rss_proxy_url", e.target.value)} placeholder="http://192.168.5.124:20181" /></label>
      <p className="settings-inline-hint">RSS 代理只用于抓取订阅，不影响 Bangumi、TMDB 或局域网内的 qBittorrent。</p>
      <p className="settings-inline-hint">该目录必须与上方 CyMediaFlow 媒体目录指向同一份 NAS 文件。例如 qB 看见 /downloads/Bangumi，而 CyMediaFlow 看见 /media。下载器连接测试会使用已保存的设置，请先保存。</p>
      <KeywordTags label="默认排除词" value={form.default_exclude_keywords} onChange={(words) => update("default_exclude_keywords", words)} disabled={config.isPending || save.isPending} hint="回车添加，点击标签修改，× 删除。用于新建追番规则的预填；已保存规则保留各自的排除词。" />
      <div className="automation-actions">
        <button type="button" className="secondary-button" onClick={() => test.mutate()} disabled={test.isPending}>测试下载器</button>
        <button type="button" className="primary-button" onClick={() => save.mutate()} disabled={save.isPending || config.isPending || config.isError}>保存自动追番设置</button>
      </div>
      {save.isSuccess ? <p className="automation-note success">设置已保存</p> : null}
      {save.isError ? <p className="automation-note error">{save.error.message}</p> : null}
      {config.isError ? <p role="alert" className="automation-note error">{config.error.message}</p> : null}
      {test.isSuccess ? <p className="automation-note success">连接成功：qBittorrent {test.data.version}</p> : null}
      {test.isError ? <p className="automation-note error">{test.error.message}</p> : null}
    </div>
  </section>;
}
