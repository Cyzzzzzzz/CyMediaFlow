import { ArrowsClockwise, DownloadSimple, ListBullets, Plus, Rss, Television, SquaresFour } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { automationApi } from "./api";
import type { Feed, Release, Subscription } from "./types";
import { CalendarPanel, NotificationsPanel, useAutomationEvents } from "./CalendarNotifications";
import { DownloadActions, OrphanTasks } from "./DownloadActions";
import { ReleaseReviewDialog, ResourceSearchPanel } from "./ResourceSearchPanel";
import { featureApi } from "./featureApi";
import { AddRssDialog } from "./AddRssDialog";
import { SubscriptionEditor } from "./SubscriptionEditor";
import { sameWork, SubscriptionShelf } from "./SubscriptionShelf";
import "./automation.css";
import "./subscriptions.css";

type Tab = "shelf" | "rules" | "rss" | "releases" | "downloads" | "events" | "search" | "calendar" | "notifications";
const tabItems: { id: Tab; label: string; icon: typeof Rss }[] = [
  { id: "shelf", label: "订阅番剧", icon: SquaresFour },
  { id: "rules", label: "追番规则", icon: Television },
  { id: "rss", label: "RSS", icon: Rss },
  { id: "search", label: "资源搜索", icon: ListBullets },
  { id: "releases", label: "发布候选", icon: ListBullets },
  { id: "downloads", label: "下载任务", icon: DownloadSimple },
  { id: "calendar", label: "播出日历", icon: SquaresFour },
  { id: "notifications", label: "通知", icon: ListBullets },
  { id: "events", label: "活动记录", icon: ListBullets },
];

export function AutomationPage() {
  useAutomationEvents();
  const [tab, setTab] = useState<Tab>("shelf");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Subscription | "new" | null>(null);
  const [downloadRule, setDownloadRule] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const rules = useQuery({ queryKey: ["automation", "rules"], queryFn: automationApi.rules });
  const feeds = useQuery({ queryKey: ["automation", "feeds"], queryFn: automationApi.feeds });
  return <div className="automation-page">
    <header className="page-header automation-page-header"><div><span className="eyebrow">CyMediaFlow</span><h1>AutoBangumi</h1><p className="automation-subtitle">你的追番片单</p></div><button type="button" className="primary-button" onClick={() => setAdding(true)}><Plus size={17} />新增 RSS 订阅</button></header>
    <div className="automation-tabs" role="tablist" aria-label="自动追番功能">
      {tabItems.map(({ id, label, icon: Icon }) => <button key={id} type="button" role="tab" aria-selected={tab === id} className={tab === id ? "selected" : ""} onClick={() => setTab(id)}><Icon size={17} />{label}</button>)}
    </div>
    {message ? <div className="subscription-notice" role="status"><span>{message}</span><button type="button" className="quiet-button" onClick={() => setMessage("")}>关闭</button></div> : null}
    {tab === "shelf" ? <SubscriptionShelf rules={rules.data ?? []} loading={rules.isLoading} error={rules.error} onEdit={setEditing} onAdd={() => setAdding(true)} /> : tab === "rules" ? <RulesPanel rules={rules.data ?? []} feeds={feeds.data ?? []} onEdit={setEditing} onAdd={() => setEditing("new")} /> : tab === "rss" ? <RssPanel /> : tab === "releases" ? <ReleasesPanel /> : tab === "downloads" ? <DownloadsPanel ruleId={downloadRule} onClear={() => setDownloadRule(null)} /> : tab === "search" ? <ResourceSearchPanel /> : tab === "calendar" ? <CalendarPanel onEdit={setEditing} /> : tab === "notifications" ? <NotificationsPanel /> : <EventsPanel />}
    {adding ? <AddRssDialog onClose={() => setAdding(false)} onSuccess={(text) => { setMessage(text); setAdding(false); setTab("shelf"); }} /> : null}
    {editing !== null ? <SubscriptionEditor key={editing === "new" ? "new" : editing.id} rule={editing === "new" ? null : editing} feeds={feeds.data ?? []} siblings={editing === "new" ? [] : (rules.data ?? []).filter((item) => sameWork(item, editing))} onSelect={setEditing} onClose={() => setEditing(null)} onDownloads={(id) => { setEditing(null); setDownloadRule(id); setTab("downloads"); }} /> : null}
  </div>;
}

function RulesPanel({ rules, feeds, onEdit, onAdd }: { rules: Subscription[]; feeds: Feed[]; onEdit: (rule: Subscription) => void; onAdd: () => void }) {
  return <section className="automation-panel">
    <div className="automation-panel-head"><div><h2>追番规则</h2><p>与封面列表共用规则。每条规则只作用于对应作品和 RSS 源。</p></div><button type="button" className="secondary-button" onClick={onAdd} disabled={!feeds.length}>添加规则</button></div>
    <div className="automation-card-list">{rules.map((rule) => <article className="automation-card" key={rule.id}>
      <div><strong>{rule.title}</strong><span>{feeds.find((feed) => feed.id === rule.feed_id)?.name ?? "已删除 RSS"} · Season {rule.season + rule.season_offset} {rule.preferred_group ? `· ${rule.preferred_group}` : ""}</span></div>
      <span className={`automation-pill ${rule.enabled && !rule.archived ? "ok" : ""}`}>{rule.archived ? "已归档" : rule.enabled ? "已启用" : "已停用"}</span>
      <button type="button" className="secondary-button" onClick={() => onEdit(rule)}>编辑</button>
    </article>)}</div>
    {!rules.length ? <div className="page-state">还没有追番规则。点击“新增 RSS 订阅”开始。</div> : null}
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
  const refresh = useMutation({ mutationFn: automationApi.refreshFeed, onSuccess: (result) => { client.invalidateQueries({ queryKey: ["automation"] }); setMessage(`已读取 ${result.fetched} 条，确认创建 ${result.submitted} 条，等待确认 ${result.pending ?? 0} 条，失败 ${result.failed ?? 0} 条`); }, onError: (e) => setMessage(e.message) });
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

function DownloadsPanel({ ruleId, onClear }: { ruleId: number | null; onClear: () => void }) {
  const client = useQueryClient();
  const downloads = useQuery({ queryKey: ["automation", "downloads"], queryFn: automationApi.downloads });
  const releases = useQuery({ queryKey: ["automation", "releases"], queryFn: automationApi.releases });
  const sync = useMutation({ mutationFn: automationApi.syncDownloads, onSuccess: () => client.invalidateQueries({ queryKey: ["automation"] }) });
  const retry = useMutation({ mutationFn: automationApi.retryDownload, onSuccess: () => client.invalidateQueries({ queryKey: ["automation"] }) });
  return <section className="automation-panel"><div className="automation-panel-head"><div><h2>下载任务</h2><p>查到 qBittorrent 实际任务后才确认创建；长时间等待时可同步状态后重试。</p></div><button type="button" className="secondary-button" onClick={() => sync.mutate()} disabled={sync.isPending || retry.isPending}><ArrowsClockwise size={16} />同步状态</button></div>
    {ruleId !== null ? <p className="automation-note">只显示规则 #{ruleId} 的任务 <button type="button" className="quiet-button" onClick={onClear}>查看全部</button></p> : null}
    {sync.isError ? <p role="alert" className="automation-note error">{sync.error.message}</p> : null}
    {retry.isError ? <p role="alert" className="automation-note error">{retry.error.message}</p> : null}
    <div className="automation-card-list">{downloads.data?.filter((job) => ruleId === null || job.subscription_id === ruleId).map((job) => <article className="automation-card" key={job.id}><div><strong>{releases.data?.find((release) => release.id === job.release_id)?.title ?? `任务 #${job.id}`}</strong><span>{job.save_path}</span>{job.state === "waiting_rename" ? <small className="automation-note">{job.error || "等待下载器确认重命名，将自动复查，无需人工审核"}</small> : job.error ? <small className="automation-note error">{job.error}</small> : null}</div><span className={`automation-pill ${job.state === "organized" ? "ok" : ""}`}>{job.state === "downloading" ? `下载中 ${job.progress}%` : job.state === "submitted" && !job.torrent_hash ? "等待确认" : downloadLabels[job.state] ?? job.state}</span>{!job.torrent_hash && ["retry", "missing"].includes(job.state) ? <button type="button" className="secondary-button" disabled={sync.isPending || retry.isPending} onClick={() => retry.mutate(job.id)}>{retry.isPending && retry.variables === job.id ? "重试中…" : "重试添加"}</button> : null}<DownloadActions job={job} /></article>)}</div>
    <OrphanTasks />
    {!downloads.data?.some((job) => ruleId === null || job.subscription_id === ruleId) ? <div className="page-state">还没有自动下载任务。</div> : null}
  </section>;
}

const downloadLabels: Record<string, string> = {
  paused: "已暂停", checking: "校验中", removed: "已移除", superseded: "旧版已备份", revision_ready: "新版待替换",
  planned: "待提交", confirming: "等待确认", submitted: "已确认创建", retry: "添加失败",
  missing: "未找到任务", retry_sync: "同步失败", waiting_files: "等待文件", waiting_rename: "等待改名确认", organizing: "整理中", organized: "已整理", review: "待审核",
};
const decisionLabels: Record<string, string> = {
  excluded: "手动排除",
  new: "待分析", ready: "已匹配", skipped: "已跳过", review: "待审核", queued: "已确认创建",
  confirming: "等待确认", retry: "添加失败", missing: "未找到任务", waiting_rename: "等待改名确认",
};

function ReleasesPanel() {
  const client = useQueryClient();
  const [review, setReview] = useState<Release | null>(null);
  const skip = useMutation({ mutationFn: featureApi.skip, onSuccess: () => client.invalidateQueries({ queryKey: ["automation", "releases"] }) });
  const releases = useQuery({ queryKey: ["automation", "releases"], queryFn: automationApi.releases });
  const feeds = useQuery({ queryKey: ["automation", "feeds"], queryFn: automationApi.feeds });
  const [feedId, setFeedId] = useState(0);
  const visible = releases.data?.filter((release) => !feedId || release.feed_id === feedId);
  return <section className="automation-panel">
    <div className="automation-panel-head"><div><h2>发布候选</h2><p>保留最近 100 条解析结果；跳过和待审核的原因在这里查看。</p></div><select aria-label="筛选 RSS 源" value={feedId} onChange={(event) => setFeedId(Number(event.target.value))}><option value={0}>全部 RSS</option>{feeds.data?.map((feed) => <option key={feed.id} value={feed.id}>{feed.name}</option>)}</select></div>
    <div className="automation-card-list">{visible?.map((release) => <article className="automation-card" key={release.id}>
      <div><strong>{release.title}</strong><span>{feeds.data?.find((feed) => feed.id === release.feed_id)?.name ?? "未知 RSS"} · {release.analysis.title ?? "标题未识别"} · {release.analysis.episode !== null ? `E${release.analysis.episode}` : "集号未识别"} · 可信度 {release.analysis.confidence}%</span>{release.decision === "waiting_rename" ? <small className="automation-note">{release.reason || "等待下载器确认重命名，将自动复查，无需人工审核"}</small> : release.reason ? <small className="automation-note">{release.reason}</small> : null}</div>
      <span className={`automation-pill ${release.decision === "queued" ? "ok" : ""}`}>{decisionLabels[release.decision] ?? release.decision}</span>
      {release.decision !== "waiting_rename" ? <button className="secondary-button" onClick={() => setReview(release)}>审核 / 下载</button> : null}<button className="quiet-button" disabled={skip.isPending} onClick={() => skip.mutate(release.id)}>排除</button>
    </article>)}</div>
    {releases.isLoading ? <div className="page-state">正在读取发布候选…</div> : !visible?.length ? <div className="page-state">还没有发布候选。请先刷新 RSS。</div> : null}
    {review ? <ReleaseReviewDialog release={review} onClose={() => setReview(null)} /> : null}
    {skip.error ? <p role="alert">{skip.error.message}</p> : null}
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
