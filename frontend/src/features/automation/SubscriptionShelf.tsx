import { MagnifyingGlass, Rss } from "@phosphor-icons/react";
import { useState } from "react";
import { SubscriptionPoster } from "./SubscriptionPoster";
import type { Subscription } from "./types";

export function sameWork(left: Subscription, right: Subscription) {
  return left.title === right.title && left.season + (left.season_offset ?? 0) === right.season + (right.season_offset ?? 0);
}

export function SubscriptionShelf({ rules, loading, error, onEdit, onAdd }: {
  rules: Subscription[]; loading: boolean; error: Error | null;
  onEdit: (rule: Subscription) => void; onAdd: () => void;
}) {
  const [query, setQuery] = useState("");
  const [archived, setArchived] = useState(false);
  const filtered = rules.filter((item) => Boolean(item.archived) === archived && [item.title, item.source_title, ...item.aliases].some((text) => text?.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())));
  const groups: Subscription[][] = [];
  for (const rule of filtered) {
    const group = groups.find((items) => sameWork(items[0], rule));
    if (group) group.push(rule); else groups.push([rule]);
  }
  return <section className="subscription-shelf" aria-label="订阅番剧封面列表">
    <div className="subscription-shelf-toolbar"><div className="subscription-view-toggle"><button type="button" aria-pressed={!archived} onClick={() => setArchived(false)}>订阅中 <span>{rules.filter((rule) => !rule.archived).length}</span></button><button type="button" aria-pressed={archived} onClick={() => setArchived(true)}>已归档</button></div><label className="subscription-filter"><MagnifyingGlass size={17} /><input aria-label="搜索订阅番剧" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索订阅番剧" /></label></div>
    {error ? <p role="alert" className="automation-note error">{error.message}</p> : loading ? <div className="page-state">正在读取订阅番剧…</div> : groups.length ? <div className="subscription-poster-grid">{groups.map((group, index) => {
      const rule = group.find((item) => item.poster_url || item.local_poster_url) ?? group[0];
      return <button key={group[0].id} type="button" className="subscription-poster-card" aria-label={`编辑 ${rule.title} 第 ${rule.season + rule.season_offset} 季`} onClick={() => onEdit(rule)}>
        <SubscriptionPoster title={rule.title} url={rule.poster_url} localUrl={rule.local_poster_url} priority={index < 6} />
        <strong title={rule.title}>{rule.title}</strong><span className="subscription-card-caption">Season {rule.season + rule.season_offset}<i />{archived ? "已归档" : !group.some((item) => item.enabled) ? "已停用" : group.length > 1 ? `${group.length} 条规则` : rule.preferred_group || "追番中"}</span>
      </button>;
    })}</div> : <div className="subscription-empty"><Rss size={36} weight="thin" /><h2>{query ? "没有找到订阅" : archived ? "还没有归档番剧" : "从一部想看的番剧开始"}</h2><p>{query ? "试试作品名称或发布标题。" : archived ? "归档后保留配置，不再接收新发布。" : "添加 RSS，确认作品和规则，它就会出现在这里。"}</p>{!query && !archived ? <button type="button" className="secondary-button" onClick={onAdd}>添加第一个订阅</button> : null}</div>}
  </section>;
}
