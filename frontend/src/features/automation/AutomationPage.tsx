import { ArrowsClockwise, DownloadSimple, ListBullets, Rss, Television } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { automationApi } from "./api";
import type { Feed, Subscription } from "./types";
import "./automation.css";

type Tab = "rules" | "rss" | "releases" | "downloads" | "events";
const tabItems: { id: Tab; label: string; icon: typeof Rss }[] = [
  { id: "rules", label: "追番规则", icon: Television },
  { id: "rss", label: "RSS", icon: Rss },
  { id: "releases", label: "发布候选", icon: ListBullets },
  { id: "downloads", label: "下载任务", icon: DownloadSimple },
  { id: "events", label: "活动记录", icon: ListBullets },
];

export function AutomationPage() {
  const [tab, setTab] = useState<Tab>("rules");
  return <div className="automation-page">
    <header className="page-header"><div><span className="eyebrow">CyMediaFlow</span><h1>AutoBangumi</h1><p className="automation-subtitle">订阅、下载与整理</p></div></header>
    <div className="automation-tabs" role="tablist" aria-label="自动追番功能">
      {tabItems.map(({ id, label, icon: Icon }) => <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? "selected" : ""} onClick={() => setTab(id)}><Icon size={17} />{label}</button>)}
    </div>
    {tab === "rules" ? <RulesPanel /> : tab === "rss" ? <RssPanel /> : tab === "releases" ? <ReleasesPanel /> : tab === "downloads" ? <DownloadsPanel /> : <EventsPanel />}
  </div>;
}

const emptyRule: Omit<Subscription, "id"> = {
  feed_id: 0, title: "", folder_name: "", aliases: [], season: 1,
  episode_offset: 0, preferred_group: null, preferred_resolution: null,
  exclude_keywords: [], enabled: true,
};

function RulesPanel() {
  const client = useQueryClient();
  const rules = useQuery({ queryKey: ["automation", "rules"], queryFn: automationApi.rules });
  const feeds = useQuery({ queryKey: ["automation", "feeds"], queryFn: automationApi.feeds });
  const [editing, setEditing] = useState<number | null | "new">(null);
  const [form, setForm] = useState(emptyRule);
  const [error, setError] = useState("");
  const save = useMutation({ mutationFn: () => automationApi.saveRule(editing === "new" ? null : editing, form), onSuccess: () => { client.invalidateQueries({ queryKey: ["automation", "rules"] }); setEditing(null); setError(""); }, onError: (cause) => setError(cause.message) });
  const remove = useMutation({ mutationFn: automationApi.deleteRule, onSuccess: () => client.invalidateQueries({ queryKey: ["automation", "rules"] }) });
  const start = (rule?: Subscription) => { setForm(rule ? { ...rule } : { ...emptyRule, feed_id: feeds.data?.[0]?.id ?? 0 }); setEditing(rule?.id ?? "new"); setError(""); };
  const update = <K extends keyof typeof form>(key: K, value: typeof form[K]) => setForm((old) => ({ ...old, [key]: value }));

  return <section className="automation-panel">
    <div className="automation-panel-head"><div><h2>追番规则</h2><p>每个规则限定一部作品和一个 RSS 源。只有匹配且通过过滤的发布才会自动下载。</p></div><button type="button" className="primary-button" onClick={() => start()} disabled={!feeds.data?.length}>添加规则</button></div>
    {!feeds.data?.length ? <div className="page-state">请先在 RSS 子标签添加订阅源。</div> : null}
    <div className="automation-card-list">{rules.data?.map((rule) => <article className="automation-card" key={rule.id}>
      <div><strong>{rule.title}</strong><span>{feeds.data?.find((feed) => feed.id === rule.feed_id)?.name ?? "未知 RSS"} · Season {rule.season} {rule.preferred_group ? `· ${rule.preferred_group}` : ""}</span></div>
      <span className={`automation-pill ${rule.enabled ? "ok" : ""}`}>{rule.enabled ? "运行中" : "已停用"}</span>
      <button type="button" className="secondary-button" onClick={() => start(rule)}>编辑</button>
      <button type="button" className="quiet-button" onClick={() => { if (window.confirm(`删除“${rule.title}”规则？已下载任务记录会保留。`)) remove.mutate(rule.id); }}>删除</button>
    </article>)}</div>
    {rules.isLoading ? <div className="page-state">正在读取规则…</div> : !rules.data?.length && feeds.data?.length ? <div className="page-state">还没有追番规则。</div> : null}
    {editing !== null ? <div className="automation-overlay" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setEditing(null); }}><section className="automation-drawer" role="dialog" aria-modal="true" aria-label="追番规则">
      <header><div><span className="eyebrow">AutoBangumi</span><h2>{editing === "new" ? "添加追番规则" : "编辑追番规则"}</h2></div><button type="button" className="quiet-button" onClick={() => setEditing(null)}>关闭</button></header>
      <div className="automation-form">
        <label>RSS 源<select value={form.feed_id} onChange={(e) => update("feed_id", Number(e.target.value))}>{feeds.data?.map((feed) => <option key={feed.id} value={feed.id}>{feed.name}</option>)}</select></label>
        <label>作品标题<input value={form.title} onChange={(e) => update("title", e.target.value)} placeholder="例如：吹响吧！上低音号" /></label>
        <label>下载目录名<input value={form.folder_name} onChange={(e) => update("folder_name", e.target.value)} placeholder="留空则使用作品标题" /></label>
        <label>标题别名（每行一个）<textarea rows={3} value={form.aliases.join("\n")} onChange={(e) => update("aliases", e.target.value.split("\n"))} placeholder="英文／日文发布标题" /></label>
        <div className="automation-form-grid"><label>本地季号<input type="number" min="0" max="99" value={form.season} onChange={(e) => update("season", Number(e.target.value))} /></label><label>集数偏移<input type="number" value={form.episode_offset} onChange={(e) => update("episode_offset", Number(e.target.value))} /></label></div>
        <div className="automation-form-grid"><label>偏好字幕组<input value={form.preferred_group ?? ""} onChange={(e) => update("preferred_group", e.target.value || null)} placeholder="可不填" /></label><label>偏好清晰度<input value={form.preferred_resolution ?? ""} onChange={(e) => update("preferred_resolution", e.target.value || null)} placeholder="1080p" /></label></div>
        <label>排除词（每行一个）<textarea rows={2} value={form.exclude_keywords.join("\n")} onChange={(e) => update("exclude_keywords", e.target.value.split("\n"))} /></label>
        <label className="automation-check"><input type="checkbox" checked={form.enabled} onChange={(e) => update("enabled", e.target.checked)} />启用规则</label>
        <p className="automation-note">下载器保存目录会加上“作品目录 / Season N”。不确定的标题、多视频种子和目标冲突会停在待审核。</p>
        {error ? <p className="automation-note error">{error}</p> : null}
        <button type="button" className="primary-button" onClick={() => save.mutate()} disabled={save.isPending || !form.title.trim() || !form.feed_id}>保存规则</button>
      </div>
    </section></div> : null}
  </section>;
}

function RssPanel() {
  const client = useQueryClient();
  const feeds = useQuery({ queryKey: ["automation", "feeds"], queryFn: automationApi.feeds });
  const [editing, setEditing] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [previewId, setPreviewId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const save = useMutation({ mutationFn: () => automationApi.saveFeed(editing, { name, url: url || null, enabled: true }), onSuccess: () => { client.invalidateQueries({ queryKey: ["automation", "feeds"] }); setEditing(null); setName(""); setUrl(""); setMessage("RSS 已保存"); }, onError: (e) => setMessage(e.message) });
  const preview = useMutation({ mutationFn: automationApi.previewFeed, onSuccess: (_data, id) => { setPreviewId(id); client.invalidateQueries({ queryKey: ["automation", "feeds"] }); }, onError: (e) => setMessage(e.message) });
  const refresh = useMutation({ mutationFn: automationApi.refreshFeed, onSuccess: (result) => { client.invalidateQueries({ queryKey: ["automation"] }); setMessage(`已读取 ${result.fetched} 条，提交 ${result.submitted} 条`); }, onError: (e) => setMessage(e.message) });
  const toggle = useMutation({ mutationFn: (feed: Feed) => automationApi.saveFeed(feed.id, { name: feed.name, url: null, enabled: !feed.enabled }), onSuccess: () => client.invalidateQueries({ queryKey: ["automation", "feeds"] }) });
  const remove = useMutation({ mutationFn: automationApi.deleteFeed, onSuccess: () => client.invalidateQueries({ queryKey: ["automation"] }) });
  return <section className="automation-panel">
    <div className="automation-panel-head"><div><h2>RSS 订阅</h2><p>先预览发布标题，再创建对应的追番规则。</p></div></div>
    <div className="automation-inline-form"><input aria-label="RSS 名称" value={name} onChange={(e) => setName(e.target.value)} placeholder="RSS 名称" /><input aria-label="RSS 地址" value={url} onChange={(e) => setUrl(e.target.value)} placeholder={editing ? "留空保持原地址" : "https://example.com/feed.xml"} /><button type="button" className="primary-button" onClick={() => save.mutate()} disabled={save.isPending || !name || (!url && !editing)}>{editing ? "保存" : "添加 RSS"}</button>{editing ? <button type="button" className="quiet-button" onClick={() => { setEditing(null); setName(""); setUrl(""); }}>取消</button> : null}</div>
    {message ? <p className="automation-note">{message}</p> : null}
    <div className="automation-card-list">{feeds.data?.map((feed) => <article className="automation-card" key={feed.id}>
      <div><strong>{feed.name}</strong><span>{feed.url} · {feed.last_checked_at ? `上次检查 ${new Date(feed.last_checked_at).toLocaleString()}` : "尚未检查"}</span>{feed.last_error ? <small className="automation-note error">{feed.last_error}</small> : null}</div>
      <span className={`automation-pill ${feed.status === "connected" && feed.enabled ? "ok" : ""}`}>{feed.enabled ? feed.status === "connected" ? "已连接" : feed.status === "error" ? "连接错误" : "待检查" : "已停用"}</span>
      <button type="button" className="secondary-button" onClick={() => preview.mutate(feed.id)}>预览</button>
      <button type="button" className="secondary-button" onClick={() => refresh.mutate(feed.id)}>刷新</button>
      <button type="button" className="quiet-button" onClick={() => { setEditing(feed.id); setName(feed.name); setUrl(""); }}>编辑</button>
      <button type="button" className="quiet-button" onClick={() => toggle.mutate(feed)}>{feed.enabled ? "停用" : "启用"}</button>
      <button type="button" className="quiet-button" onClick={() => { if (window.confirm(`删除 RSS“${feed.name}”？关联规则将停用。`)) remove.mutate(feed.id); }}>删除</button>
    </article>)}</div>
    {!feeds.data?.length ? <div className="page-state">还没有 RSS 订阅。</div> : null}
    {previewId !== null && preview.data ? <div className="automation-preview"><div className="automation-panel-head"><h3>发布解析预览</h3><button type="button" className="quiet-button" onClick={() => setPreviewId(null)}>收起</button></div>{preview.data.map((item, index) => <div className="automation-preview-row" key={`${item.title}-${index}`}><strong>{item.title}</strong><span>{item.analysis.title ?? "标题待确认"} · {item.analysis.episode !== null ? `E${item.analysis.episode}` : "集号待确认"} · {item.analysis.group ?? "未知字幕组"} · 可信度 {item.analysis.confidence}%</span></div>)}</div> : null}
  </section>;
}

function DownloadsPanel() {
  const client = useQueryClient();
  const downloads = useQuery({ queryKey: ["automation", "downloads"], queryFn: automationApi.downloads });
  const releases = useQuery({ queryKey: ["automation", "releases"], queryFn: automationApi.releases });
  const sync = useMutation({ mutationFn: automationApi.syncDownloads, onSuccess: () => client.invalidateQueries({ queryKey: ["automation"] }) });
  return <section className="automation-panel"><div className="automation-panel-head"><div><h2>下载任务</h2><p>这里显示由 CyMediaFlow 添加的 qBittorrent 任务。</p></div><button type="button" className="secondary-button" onClick={() => sync.mutate()} disabled={sync.isPending}><ArrowsClockwise size={16} />同步状态</button></div>
    <div className="automation-card-list">{downloads.data?.map((job) => <article className="automation-card" key={job.id}><div><strong>{releases.data?.find((release) => release.id === job.release_id)?.title ?? `任务 #${job.id}`}</strong><span>{job.save_path}</span>{job.error ? <small className="automation-note error">{job.error}</small> : null}</div><span className={`automation-pill ${job.state === "organized" ? "ok" : ""}`}>{job.state === "organized" ? "已整理" : job.state === "review" ? "待审核" : job.state === "downloading" ? `下载中 ${job.progress}%` : job.state === "waiting_files" ? "等待文件" : job.state}</span></article>)}</div>
    {!downloads.data?.length ? <div className="page-state">还没有自动下载任务。</div> : null}
  </section>;
}

const decisionLabels: Record<string, string> = {
  new: "待分析", ready: "已匹配", skipped: "已跳过", review: "待审核", queued: "已加入下载",
};

function ReleasesPanel() {
  const releases = useQuery({ queryKey: ["automation", "releases"], queryFn: automationApi.releases });
  const feeds = useQuery({ queryKey: ["automation", "feeds"], queryFn: automationApi.feeds });
  const [feedId, setFeedId] = useState(0);
  const visible = releases.data?.filter((release) => !feedId || release.feed_id === feedId);
  return <section className="automation-panel">
    <div className="automation-panel-head"><div><h2>发布候选</h2><p>保留最近 100 条解析结果；跳过和待审核的原因在这里查看。</p></div><select aria-label="筛选 RSS 源" value={feedId} onChange={(event) => setFeedId(Number(event.target.value))}><option value={0}>全部 RSS</option>{feeds.data?.map((feed) => <option key={feed.id} value={feed.id}>{feed.name}</option>)}</select></div>
    <div className="automation-card-list">{visible?.map((release) => <article className="automation-card" key={release.id}>
      <div><strong>{release.title}</strong><span>{feeds.data?.find((feed) => feed.id === release.feed_id)?.name ?? "未知 RSS"} · {release.analysis.title ?? "标题未识别"} · {release.analysis.episode !== null ? `E${release.analysis.episode}` : "集号未识别"} · 可信度 {release.analysis.confidence}%</span>{release.reason ? <small className="automation-note">{release.reason}</small> : null}</div>
      <span className={`automation-pill ${release.decision === "queued" ? "ok" : ""}`}>{decisionLabels[release.decision] ?? release.decision}</span>
    </article>)}</div>
    {releases.isLoading ? <div className="page-state">正在读取发布候选…</div> : !visible?.length ? <div className="page-state">还没有发布候选。请先刷新 RSS。</div> : null}
  </section>;
}

function EventsPanel() {
  const client = useQueryClient();
  const events = useQuery({ queryKey: ["automation", "events"], queryFn: automationApi.events });
  const refresh = useMutation({ mutationFn: automationApi.run, onSuccess: () => client.invalidateQueries({ queryKey: ["automation"] }) });
  return <section className="automation-panel"><div className="automation-panel-head"><div><h2>活动记录</h2><p>每轮 RSS 刷新、下载与整理的结果。</p></div><button type="button" className="secondary-button" onClick={() => refresh.mutate()} disabled={refresh.isPending}><ArrowsClockwise size={16} />立即检查全部</button></div>
    {refresh.isError ? <p className="automation-note error">{refresh.error.message}</p> : null}
    <div className="automation-card-list">{events.data?.map((item) => <article className="automation-card" key={item.id}><div><strong>{item.message}</strong><span>{new Date(item.created_at).toLocaleString()} · {item.kind}</span></div></article>)}</div>
    {!events.data?.length ? <div className="page-state">尚无活动记录。</div> : null}
  </section>;
}
