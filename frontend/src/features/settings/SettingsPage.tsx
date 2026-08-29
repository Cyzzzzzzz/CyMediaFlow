import { EyeSlash, FilmSlate, FolderOpen, GlobeHemisphereWest, ImageSquare } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { apiRequest } from "../../api/client";
import type { SettingsUpdate, SettingsView } from "../../api/types";

const defaultProxy = "http://192.168.5.124:20181";
const emptyForm: SettingsUpdate = {
  media_root: "",
  bangumi_access_token: null,
  clear_bangumi_access_token: false,
  bangumi_proxy_enabled: true,
  bangumi_proxy_url: defaultProxy,
  tmdb_access_token: null,
  clear_tmdb_access_token: false,
  tmdb_proxy_enabled: false,
  tmdb_proxy_url: null,
  operation_mode: "nfo_managed_update",
  episode_artwork_fallback_enabled: true,
  episode_artwork_capture_percent: 25,
  ffprobe_path: "ffprobe",
  ffmpeg_path: "ffmpeg",
  ignore_marker_enabled: true,
  ignore_folder_patterns: ["特典映像", "映像特典", "特典", "对话", "电话", "電話", "SP", "PV", "NCOP", "NCED", "NCOP&NCED", "menu", "menus", "Fonts"],
};

export function SettingsPage() {
  const client = useQueryClient();
  const [form, setForm] = useState<SettingsUpdate>(emptyForm);
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiRequest<SettingsView>("/api/v1/settings"),
  });
  const save = useMutation({
    mutationFn: () => apiRequest<SettingsView>("/api/v1/settings", {
      method: "PUT",
      body: JSON.stringify(form),
    }),
    onSuccess: (data) => {
      client.setQueryData(["settings"], data);
      setForm((current) => ({
        ...current,
        bangumi_access_token: null,
        tmdb_access_token: null,
        clear_bangumi_access_token: false,
        clear_tmdb_access_token: false,
      }));
      client.removeQueries({ queryKey: ["library"] });
    },
  });

  useEffect(() => {
    if (!settings.data) return;
    setForm({
      ...emptyForm,
      media_root: settings.data.media_root,
      bangumi_proxy_enabled: settings.data.bangumi_proxy_enabled,
      bangumi_proxy_url: settings.data.bangumi_proxy_url || defaultProxy,
      tmdb_proxy_enabled: settings.data.tmdb_proxy_enabled,
      tmdb_proxy_url: settings.data.tmdb_proxy_url,
      operation_mode: settings.data.operation_mode,
      episode_artwork_fallback_enabled: settings.data.episode_artwork_fallback_enabled,
      episode_artwork_capture_percent: settings.data.episode_artwork_capture_percent,
      ffprobe_path: settings.data.ffprobe_path,
      ffmpeg_path: settings.data.ffmpeg_path,
      ignore_marker_enabled: settings.data.ignore_marker_enabled,
      ignore_folder_patterns: settings.data.ignore_folder_patterns,
    });
  }, [settings.data]);

  const update = <K extends keyof SettingsUpdate>(key: K, value: SettingsUpdate[K]) => {
    save.reset();
    setForm((current) => ({ ...current, [key]: value }));
  };
  const allowedMediaRoots = settings.data?.allowed_media_roots?.length
    ? settings.data.allowed_media_roots
    : settings.data?.allowed_media_root ? [settings.data.allowed_media_root] : [];

  return <div className="settings-page">
    <header className="page-header"><div><span className="eyebrow">CyMediaFlow</span><h1>设置</h1></div></header>

    <SettingsSection icon={<FolderOpen size={22} />} title="媒体目录" description={allowedMediaRoots.length ? `已授权 ${allowedMediaRoots.length} 个根目录` : "读取允许范围中…"}>
      <label className="proxy-field"><span>媒体目录路径</span><input list="allowed-media-roots" value={form.media_root} onChange={(event) => update("media_root", event.target.value)} /></label>
      <datalist id="allowed-media-roots">{allowedMediaRoots.map((root) => <option value={root} key={root} />)}</datalist>
      <p className="settings-inline-hint">可填写允许范围内的绝对路径或相对路径。Docker/NAS 必须填写容器路径（通常是 /media 或 /media/子目录），不能填写 /volume… 等宿主机路径；更换宿主机挂载源需修改 .env 的 MEDIA_ROOT 并重建容器。</p>
      <p className="settings-inline-hint">当前实际扫描：{settings.data?.media_root ?? "读取中…"} · {settings.data?.media_root_readable ? "可读取" : "不可读取"}。保存后立即重建媒体索引，不会移动或重命名文件。</p>
    </SettingsSection>

    <SettingsSection icon={<EyeSlash size={22} />} title="Emby 忽略目录" description="为匹配的文件夹创建 .ignore">
      <label className="toggle-row"><span>自动创建 .ignore</span><input type="checkbox" checked={form.ignore_marker_enabled} onChange={(event) => update("ignore_marker_enabled", event.target.checked)} /></label>
      <label className="proxy-field"><span>文件夹名称或路径规则（每行一条，支持 * 和 ?）</span><textarea rows={7} value={form.ignore_folder_patterns.join("\n")} onChange={(event) => update("ignore_folder_patterns", event.target.value.split("\n"))} disabled={!form.ignore_marker_enabled} /></label>
      <p className="settings-inline-hint">保存后立即同步。已匹配 {settings.data?.ignore_marker_matched_count ?? 0} 个目录；本次新建 {settings.data?.ignore_marker_created_count ?? 0} 个，已有 {settings.data?.ignore_marker_existing_count ?? 0} 个，失败 {settings.data?.ignore_marker_failed_count ?? 0} 个。关闭或删除规则不会移除已有 .ignore。</p>
    </SettingsSection>

    <SettingsSection icon={<GlobeHemisphereWest size={22} />} title="Bangumi" description={settings.data?.bangumi_configured ? "Token 已配置" : "Token 未配置"}>
      <SecretField label="Access Token" configured={settings.data?.bangumi_configured ?? false} value={form.bangumi_access_token ?? ""} clear={form.clear_bangumi_access_token} onValue={(value) => update("bangumi_access_token", value || null)} onClear={(value) => update("clear_bangumi_access_token", value)} />
      <label className="toggle-row"><span>使用网络代理</span><input type="checkbox" checked={form.bangumi_proxy_enabled} onChange={(event) => update("bangumi_proxy_enabled", event.target.checked)} /></label>
      <label className="proxy-field"><span>HTTP 代理地址</span><input value={form.bangumi_proxy_url ?? ""} onChange={(event) => update("bangumi_proxy_url", event.target.value || null)} disabled={!form.bangumi_proxy_enabled} placeholder={defaultProxy} /></label>
    </SettingsSection>

    <SettingsSection icon={<FilmSlate size={22} />} title="TMDB" description={settings.data?.tmdb_configured ? "API Read Access Token 已配置" : "等待配置 Token"}>
      <SecretField label="API Read Access Token" configured={settings.data?.tmdb_configured ?? false} value={form.tmdb_access_token ?? ""} clear={form.clear_tmdb_access_token} onValue={(value) => update("tmdb_access_token", value || null)} onClear={(value) => update("clear_tmdb_access_token", value)} />
      <label className="toggle-row"><span>使用网络代理</span><input type="checkbox" checked={form.tmdb_proxy_enabled} onChange={(event) => update("tmdb_proxy_enabled", event.target.checked)} /></label>
      <label className="proxy-field"><span>HTTP 代理地址</span><input value={form.tmdb_proxy_url ?? ""} onChange={(event) => update("tmdb_proxy_url", event.target.value || null)} disabled={!form.tmdb_proxy_enabled} placeholder={defaultProxy} /></label>
      <p className="settings-inline-hint">This product uses the TMDB API but is not endorsed or certified by TMDB.</p>
    </SettingsSection>

    <SettingsSection icon={<ImageSquare size={22} />} title="文件操作与本地图片" description="写入 NFO、海报、背景图、Logo 与分集剧照">
      <label className="proxy-field"><span>NFO 写入策略</span><select value={form.operation_mode} onChange={(event) => update("operation_mode", event.target.value as SettingsUpdate["operation_mode"])}><option value="nfo_managed_update">可控覆盖（字段锁保护）</option><option value="nfo_create_only">仅创建缺失 NFO</option></select></label>
      <label className="proxy-field"><span>ffprobe 路径</span><input value={form.ffprobe_path} onChange={(event) => update("ffprobe_path", event.target.value)} /></label>
      <p className="settings-inline-hint">{settings.data?.ffprobe_available ? "路径可用，可读取媒体流信息。" : "未找到 ffprobe，媒体流信息不会写入 NFO。"}</p>
      <label className="proxy-field"><span>ffmpeg 路径</span><input value={form.ffmpeg_path} onChange={(event) => update("ffmpeg_path", event.target.value)} /></label>
      <p className="settings-inline-hint">{settings.data?.ffmpeg_available ? "路径可用，可从本地视频生成分集截图。" : "未找到 ffmpeg，本地分集截图会生成失败。"}</p>
      <label className="toggle-row"><span>没有任何可用预览图时从视频截图</span><input type="checkbox" checked={form.episode_artwork_fallback_enabled} onChange={(event) => update("episode_artwork_fallback_enabled", event.target.checked)} /></label>
      <label className="proxy-field"><span>截图位置：视频时长的 {form.episode_artwork_capture_percent}%</span><input type="range" min="5" max="90" step="5" value={form.episode_artwork_capture_percent} onChange={(event) => update("episode_artwork_capture_percent", Number(event.target.value))} disabled={!form.episode_artwork_fallback_enabled} /></label>
    </SettingsSection>

    <div className="settings-savebar"><span>{save.isSuccess ? `设置已生效，正在扫描 ${settings.data?.media_root ?? form.media_root}` : save.isError ? save.error.message : "Token 不会通过接口回传"}</span><button className="primary-button" type="button" onClick={() => save.mutate()} disabled={save.isPending || !form.media_root}>{save.isPending ? "保存中" : "保存设置"}</button></div>
  </div>;
}

function SettingsSection({ icon, title, description, children }: { icon: ReactNode; title: string; description: string; children: ReactNode }) {
  return <section className="proxy-card settings-section"><div className="proxy-title"><span className="setting-icon">{icon}</span><span><strong>{title}</strong><small>{description}</small></span></div><div className="settings-section-body">{children}</div></section>;
}

function SecretField({ label, configured, value, clear, onValue, onClear }: { label: string; configured: boolean; value: string; clear: boolean; onValue: (value: string) => void; onClear: (value: boolean) => void }) {
  return <><label className="proxy-field"><span>{label}</span><input type="password" value={value} onChange={(event) => onValue(event.target.value)} disabled={clear} placeholder={configured ? "已配置；留空表示不修改" : "粘贴 Token"} autoComplete="off" /></label>{configured ? <label className="toggle-row danger-toggle"><span>清除已保存的 Token</span><input type="checkbox" checked={clear} onChange={(event) => onClear(event.target.checked)} /></label> : null}</>;
}
