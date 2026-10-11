import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { automationApi } from "./api";
import { SubscriptionPoster } from "./SubscriptionPoster";
import { applyMetadata } from "./subscriptionForm";
import type { SubscriptionDraft, SubscriptionMatch } from "./types";

type Props = { value: SubscriptionDraft; onChange: (value: SubscriptionDraft) => void; localPoster?: string | null; matches?: SubscriptionMatch[] };
const weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"];

export function SubscriptionFields({ value, onChange, localPoster, matches = [] }: Props) {
  const [provider, setProvider] = useState<"bangumi" | "tmdb">(value.provider ?? "bangumi");
  const [query, setQuery] = useState(value.title);
  const search = useMutation({ mutationFn: () => automationApi.searchMetadata(provider, query) });
  const set = <K extends keyof SubscriptionDraft>(key: K, next: SubscriptionDraft[K]) => onChange({ ...value, [key]: next });
  const hits = search.data ?? matches;
  const season = value.season + value.season_offset;
  const episode = 1 + value.episode_offset;
  return <div className="subscription-fields automation-form">
    <div className="subscription-identity">
      <SubscriptionPoster title={value.title} url={value.poster_url} localUrl={localPoster} priority />
      <div className="subscription-identity-fields">
        <label>作品标题<input value={value.title} onChange={(e) => set("title", e.target.value)} placeholder="作品名称，用于整理命名" maxLength={180} /></label>
        <div className="automation-form-grid"><label>年份<input type="number" min={1900} max={2100} value={value.year ?? ""} onChange={(e) => set("year", e.target.value ? Number(e.target.value) : null)} placeholder="未识别" /></label><label>季度<input type="number" min={0} max={99} value={value.season} onChange={(e) => set("season", Number(e.target.value))} /></label></div>
        {value.source_title ? <p className="subscription-original" title={value.source_title}>发布标题 · {value.source_title}</p> : null}
        <div className="subscription-tags">{[value.release_group, value.resolution, value.subtitle, value.source, value.provider?.toUpperCase()].filter(Boolean).map((tag, index) => <span key={`${tag}-${index}`}>{tag}</span>)}</div>
      </div>
    </div>
    <details className="subscription-section">
      <summary>作品与海报匹配 <span>{value.provider ? `${value.provider.toUpperCase()} · ${value.provider_id}` : "未绑定元数据"}</span></summary>
      <div className="subscription-section-body">
        <div className="subscription-search"><select aria-label="匹配来源" value={provider} onChange={(e) => { setProvider(e.target.value as typeof provider); search.reset(); }}><option value="bangumi">Bangumi</option><option value="tmdb">TMDB</option></select><input aria-label="作品搜索关键词" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && query.trim() && !search.isPending) { e.preventDefault(); search.mutate(); } }} /><button type="button" className="secondary-button" disabled={search.isPending || !query.trim()} onClick={() => search.mutate()}>{search.isPending ? "搜索中…" : "搜索"}</button></div>
        <p className="automation-note">仅点击搜索时联网。选择条目更新名称、年份与海报，不改变季度。</p>
        {search.isError ? <p role="alert" className="automation-note error">{search.error.message}</p> : null}
        {hits.length ? <div className="subscription-match-list">{hits.map((match) => <button type="button" key={`${match.provider}-${match.external_id}`} className={value.provider === match.provider && value.provider_id === match.external_id ? "selected" : ""} onClick={() => onChange(applyMetadata(value, match))}><span>{match.title}</span><small>{match.year ?? "年份未知"} · {match.provider.toUpperCase()} · {match.external_id}</small></button>)}</div> : search.isSuccess ? <p className="automation-note">没有找到作品，请换一个关键词。</p> : null}
      </div>
    </details>
    <details className="subscription-section">
      <summary>高级设置 <span>过滤 · 偏移 · 下载偏好</span></summary>
      <div className="subscription-section-body">
        <label>下载目录名<input value={value.folder_name} onChange={(e) => set("folder_name", e.target.value)} placeholder="留空使用作品标题" maxLength={180} /></label>
        <label>标题别名（每行一个）<textarea rows={2} value={value.aliases.join("\n")} onChange={(e) => set("aliases", e.target.value.split("\n"))} placeholder="用于匹配 RSS 的英文／日文标题" /></label>
        <label>排除词（每行一个）<textarea rows={2} value={value.exclude_keywords.join("\n")} onChange={(e) => set("exclude_keywords", e.target.value.split("\n"))} placeholder="发布标题包含任意排除词时跳过；不是正则表达式" /></label>
        <div className="automation-form-grid"><label>季度偏移<input type="number" min={-99} max={99} value={value.season_offset} onChange={(e) => set("season_offset", Number(e.target.value))} /></label><label>集数偏移<input type="number" min={-999} max={999} value={value.episode_offset} onChange={(e) => set("episode_offset", Number(e.target.value))} /></label></div>
        <p className="automation-note">目标季 = 季度 + 季度偏移；目标集 = 发布集号 + 集数偏移。例如发布第 13 集从 01 开始，集数偏移填 -12。特典按 S00 处理后加季度偏移，负集号不会下载。</p>
        <p className="subscription-naming-preview">{value.folder_name || value.title || "作品"} / Season {season} / {value.title || "作品"} S{String(season).padStart(2, "0")}E{episode >= 0 ? String(episode).padStart(2, "0") : "…"}.mkv <small>以发布第 1 集示例</small></p>
        <div className="automation-form-grid"><label>偏好字幕组<input value={value.preferred_group ?? ""} onChange={(e) => set("preferred_group", e.target.value || null)} placeholder="不限" /></label><label>偏好清晰度<input value={value.preferred_resolution ?? ""} onChange={(e) => set("preferred_resolution", e.target.value || null)} placeholder="不限，例如 1080p" /></label></div>
        <div className="automation-form-grid"><label>偏好字幕<select value={value.preferred_subtitle ?? ""} onChange={(e) => set("preferred_subtitle", (e.target.value || null) as SubscriptionDraft["preferred_subtitle"])}><option value="">不限</option><option value="CHS">简体中文</option><option value="CHT">繁体中文</option></select></label><label>放送星期<select value={value.air_weekday ?? ""} onChange={(e) => set("air_weekday", e.target.value ? Number(e.target.value) : null)}><option value="">未指定</option>{weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></label></div>
        <p className="automation-note">放送星期用于展示，不限制 RSS 检查时间。已提交的下载任务不受归档或停用影响。</p>
        <label className="automation-check"><input type="checkbox" checked={value.enabled} onChange={(e) => set("enabled", e.target.checked)} />启用此规则（仍受设置页自动追番总开关控制）</label>
      </div>
    </details>
  </div>;
}
