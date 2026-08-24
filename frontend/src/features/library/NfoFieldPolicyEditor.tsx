import { Lock, LockOpen, PencilSimple } from "@phosphor-icons/react";
import { useState } from "react";

import type { ExternalIdentity, LocalScrapeInfo, MetadataCandidate } from "../../api/types";

type Props = {
  localInfo?: LocalScrapeInfo;
  provider?: MetadataCandidate;
  providerName?: string;
  lockedFields: string[];
  manualValues: Record<string, unknown>;
  onChange: (lockedFields: string[], manualValues: Record<string, unknown>) => void;
};

type EditableField = {
  key: string;
  label: string;
  value: string;
  multiline?: boolean;
  code?: boolean;
  hint?: string;
};

export function NfoFieldPolicyEditor({ localInfo, provider, providerName = "元数据来源", lockedFields, manualValues, onChange }: Props) {
  const [editing, setEditing] = useState(false);
  const series = localInfo?.series;
  const seriesFields: EditableField[] = [
    { key: "series.title", label: "剧集标题", value: series?.title ?? provider?.title ?? "" },
    { key: "series.originaltitle", label: "剧集原始标题", value: series?.original_title ?? provider?.original_title ?? "" },
    { key: "series.plot", label: "剧集简介", value: series?.plot ?? provider?.summary ?? "", multiline: true },
    { key: "series.year", label: "年份", value: text(series?.year ?? provider?.year) },
    { key: "series.premiered", label: "首播日期", value: series?.premiered ?? "" },
    { key: "series.runtime", label: "时长（分钟）", value: text(series?.runtime) },
    { key: "series.rating", label: "评分", value: text(series?.rating) },
    { key: "series.tags", label: "标签", value: series?.tags.join("\n") ?? "", multiline: true },
    { key: "series.studios", label: "制作", value: series?.studios.join("\n") ?? "", multiline: true },
    { key: "series.directors", label: "导演", value: series?.directors.join("\n") ?? "", multiline: true },
    { key: "series.writers", label: "编剧", value: series?.writers.join("\n") ?? "", multiline: true },
    { key: "series.cast", label: "演员与声优", value: series?.cast.join("\n") ?? "", multiline: true, hint: "每行一人" },
    { key: "series.ids", label: "剧集外部 ID", value: identities(series?.external_ids ?? []), multiline: true, hint: "每行 provider=id" },
    { key: "series.artwork", label: "剧集海报引用", value: series?.artwork.join("\n") ?? "", multiline: true, hint: `当前海报来源：${sourceText(series?.poster_source)}` },
    { key: "series.provider_data", label: "剧集来源扩展数据", value: series?.provider_data ?? "", multiline: true, code: true, hint: "支持 bangumi/tmdb XML 节点" },
  ];

  const updateValue = (field: EditableField, value: string, scope?: string) => {
    const key = lockKey(field.key, scope);
    const currentLocks = normalizeScopedLocks(lockedFields, localInfo);
    const nextLocks = currentLocks.includes(key) ? currentLocks : [...currentLocks, key];
    onChange(nextLocks, setManualValue(manualValues, field.key, value, scope));
  };

  const toggle = (field: EditableField, scope?: string, groupFields: EditableField[] = [field]) => {
    const key = lockKey(field.key, scope);
    const currentLocks = expandGroupLock(
      normalizeScopedLocks(lockedFields, localInfo),
      groupFields,
      scope,
    );
    const locked = currentLocks.includes(key);
    const nextLocks = locked ? currentLocks.filter((item) => item !== key) : [...currentLocks, key];
    let nextValues = { ...manualValues };
    if (locked) nextValues = deleteManualValue(nextValues, field.key, scope);
    else Object.assign(nextValues, setManualValue(nextValues, field.key, field.value, scope));
    onChange(nextLocks, nextValues);
  };

  const toggleGroup = (fields: EditableField[], scope?: string) => {
    const currentLocks = normalizeScopedLocks(lockedFields, localInfo);
    const keys = fields.map((field) => lockKey(field.key, scope));
    const groupKey = lockKey(groupLockKey(fields), scope);
    const allLocked = currentLocks.includes(groupKey) || keys.every((key) => currentLocks.includes(key));
    const nextLockSet = new Set(currentLocks);
    let nextValues = { ...manualValues };
    nextLockSet.delete(groupKey);
    for (const key of keys) nextLockSet.delete(key);
    for (const field of fields) {
      if (allLocked) {
        nextValues = deleteManualValue(nextValues, field.key, scope);
      } else {
        nextValues = setManualValue(
          nextValues,
          field.key,
          manualValue(manualValues, field.key, field.value, scope),
          scope,
        );
      }
    }
    if (!allLocked) nextLockSet.add(groupKey);
    onChange([...nextLockSet], nextValues);
  };

  const groupLocked = (fields: EditableField[], scope?: string) => fields.every(
    (field) => isFieldLocked(lockedFields, field.key, scope),
  );

  const renderField = (field: EditableField, scope?: string, groupFields: EditableField[] = [field]) => <FieldEditor
    key={`${field.key}-${scope ?? "series"}`}
    field={field}
    value={manualValue(manualValues, field.key, field.value, scope)}
    locked={isFieldLocked(lockedFields, field.key, scope)}
    onValue={(value) => updateValue(field, value, scope)}
    onToggle={() => toggle(field, scope, groupFields)}
  />;

  return <section className="nfo-policy-editor">
    <div className="nfo-policy-head">
      <div><strong>字段编辑与保护</strong><small>输入会自动锁定当前字段；锁定后重新获取 {providerName} 数据也不会覆盖手工值。</small></div>
      <button className="preview-refresh" type="button" onClick={() => setEditing((value) => !value)}>
        <PencilSimple size={15} />{editing ? "收起编辑" : "编辑与锁定"}
      </button>
    </div>
    {editing ? <div className="nfo-policy-body">
      <details className="nfo-metadata-fold">
        <summary><span>剧集字段 <small>{seriesFields.length} 项 · {series ? "本地 NFO" : "来源数据"}</small></span><BatchLockButton allLocked={groupLocked(seriesFields)} label="全部剧集字段" onToggle={() => toggleGroup(seriesFields)} /></summary>
        <div className="nfo-edit-grid">{seriesFields.map((field) => renderField(field, undefined, seriesFields))}</div>
      </details>

      {(localInfo?.seasons ?? []).map((season) => {
        const seasonScope = String(season.season_number);
        const seasonFields: EditableField[] = [
          { key: "season.title", label: "季度标题", value: season.title ?? "" },
          { key: "season.originaltitle", label: "季度原始标题", value: season.original_title ?? "" },
          { key: "season.plot", label: "季度简介", value: season.plot ?? "", multiline: true },
          { key: "season.cast", label: "季度演员", value: season.cast.join("\n"), multiline: true, hint: "每行一人" },
          { key: "season.ids", label: "季度外部 ID", value: identities(season.external_ids), multiline: true, hint: "每行 provider=id" },
          { key: "season.artwork", label: "季度海报引用", value: season.artwork.join("\n"), multiline: true, hint: `当前海报来源：${sourceText(season.poster_source)}` },
          { key: "season.provider_data", label: "季度来源扩展数据", value: season.provider_data ?? "", multiline: true, code: true, hint: "支持 bangumi/tmdb XML 节点" },
        ];
        return <details className="nfo-metadata-fold" key={season.season_number}>
          <summary><span>第 {season.season_number} 季 <small>{seasonFields.length} 个季度字段 · {season.episodes.length} 集</small></span><BatchLockButton allLocked={groupLocked(seasonFields, seasonScope)} label={`第 ${season.season_number} 季季度字段`} onToggle={() => toggleGroup(seasonFields, seasonScope)} /></summary>
          <div className="nfo-edit-grid">{seasonFields.map((field) => renderField(field, seasonScope, seasonFields))}</div>
          <div className="nfo-episode-edit-list">
            {season.episodes.map((episode) => {
              const episodeScope = `${episode.season_number}:${episode.episode_number}`;
              const episodeFields: EditableField[] = [
                { key: "episodes.title", label: "分集标题", value: episode.title },
                { key: "episodes.originaltitle", label: "分集原始标题", value: episode.original_title ?? "" },
                { key: "episodes.plot", label: "分集简介", value: episode.plot ?? "", multiline: true },
                { key: "episodes.aired", label: "分集日期", value: episode.aired ?? "" },
                { key: "episodes.runtime", label: "分集时长（分钟）", value: text(episode.runtime) },
                { key: "episodes.ids", label: "分集外部 ID", value: identities(episode.external_ids), multiline: true, hint: "每行 provider=id" },
                { key: "episodes.provider_data", label: "分集来源扩展数据", value: episode.provider_data ?? "", multiline: true, code: true, hint: "支持 bangumiepisode/tmdbepisode XML 节点" },
                { key: "episodes.media_streams", label: "媒体流信息", value: episode.media_streams ?? "", multiline: true, code: true, hint: episode.media_streams ? "完整 fileinfo XML" : "当前 NFO 没有 fileinfo" },
                { key: "episodes.artwork", label: "分集截图封面", value: episode.artwork.join("\n"), multiline: true, hint: `当前图片来源：${sourceText(episode.poster_source)}` },
              ];
              return <details className="nfo-metadata-fold episode" key={episodeScope}>
                <summary><span>S{pad(episode.season_number)}E{pad(episode.episode_number)} · {episode.title}<small>{episodeFields.length} 项</small></span><BatchLockButton allLocked={groupLocked(episodeFields, episodeScope)} label={`S${pad(episode.season_number)}E${pad(episode.episode_number)} 全部字段`} onToggle={() => toggleGroup(episodeFields, episodeScope)} /></summary>
                <div className="nfo-edit-grid">{episodeFields.map((field) => renderField(field, episodeScope, episodeFields))}</div>
              </details>;
            })}
          </div>
        </details>;
      })}
      {!localInfo?.seasons.length ? <p className="subtle">生成本地季度和分集 NFO 后，可在这里逐季、逐集编辑字段。</p> : null}
    </div> : lockedFields.length ? <div className="nfo-policy-summary"><Lock size={14} weight="fill" />已保护 {lockedFields.length} 类字段</div> : null}
  </section>;
}

function BatchLockButton({ allLocked, label, onToggle }: { allLocked: boolean; label: string; onToggle: () => void }) {
  return <button
    className={`nfo-batch-lock ${allLocked ? "locked" : ""}`}
    type="button"
    aria-label={`${allLocked ? "解锁" : "锁定"}${label}`}
    title={allLocked ? "批量解锁该组字段" : "批量锁定该组字段"}
    onClick={(event) => {
      event.preventDefault();
      event.stopPropagation();
      onToggle();
    }}
  >
    {allLocked ? <Lock size={13} weight="fill" /> : <LockOpen size={13} />}
    {allLocked ? "全部解锁" : "全部锁定"}
  </button>;
}

function FieldEditor({ field, value, locked, onValue, onToggle }: { field: EditableField; value: string; locked: boolean; onValue: (value: string) => void; onToggle: () => void }) {
  return <label className={`nfo-edit-field ${locked ? "locked" : ""} ${field.code ? "code" : ""}`}>
    <span>{field.label}{field.hint ? <small>{field.hint}</small> : null}</span>
    <div>
      {field.multiline ? <textarea value={value} rows={field.code ? 7 : 3} spellCheck={!field.code} onChange={(event) => onValue(event.target.value)} />
        : <input value={value} onChange={(event) => onValue(event.target.value)} />}
      <button type="button" onClick={onToggle} aria-label={`${locked ? "解锁" : "锁定"}${field.label}`} title={locked ? "解锁后允许自动更新" : "锁定当前字段"}>
        {locked ? <Lock size={16} weight="fill" /> : <LockOpen size={16} />}
      </button>
    </div>
  </label>;
}

function manualValue(values: Record<string, unknown>, key: string, fallback: string, scope?: string) {
  const stored = values[key];
  if (scope && isRecord(stored) && scope in stored) return String(stored[scope] ?? "");
  if (!scope && stored !== undefined && !isRecord(stored)) return String(stored ?? "");
  return fallback;
}

function setManualValue(values: Record<string, unknown>, key: string, value: string, scope?: string) {
  const next = { ...values };
  if (!scope) next[key] = value;
  else next[key] = { ...(isRecord(next[key]) ? next[key] : {}), [scope]: value };
  return next;
}

function deleteManualValue(values: Record<string, unknown>, key: string, scope?: string) {
  const next = { ...values };
  if (!scope) delete next[key];
  else if (isRecord(next[key])) {
    const scoped = { ...next[key] };
    delete scoped[scope];
    if (Object.keys(scoped).length) next[key] = scoped;
    else delete next[key];
  }
  return next;
}

function lockKey(key: string, scope?: string) {
  return scope ? `${key}@${scope}` : key;
}

function isFieldLocked(locks: string[], key: string, scope?: string) {
  const group = `${key.split(".", 1)[0]}.*`;
  return locks.includes(lockKey(key, scope))
    || locks.includes(lockKey(group, scope))
    || (!!scope && (locks.includes(key) || locks.includes(group)));
}

function groupLockKey(fields: EditableField[]) {
  const prefix = fields[0]?.key.split(".", 1)[0];
  if (!prefix || fields.some((field) => !field.key.startsWith(`${prefix}.`))) {
    throw new Error("批量锁定字段必须属于同一层级");
  }
  return `${prefix}.*`;
}

function expandGroupLock(locks: string[], fields: EditableField[], scope?: string) {
  const groupKey = lockKey(groupLockKey(fields), scope);
  if (!locks.includes(groupKey)) return locks;
  return [
    ...locks.filter((key) => key !== groupKey),
    ...fields.map((field) => lockKey(field.key, scope)),
  ];
}

function normalizeScopedLocks(locks: string[], localInfo?: LocalScrapeInfo) {
  const seasonScopes = (localInfo?.seasons ?? []).map((season) => String(season.season_number));
  const episodeScopes = (localInfo?.seasons ?? []).flatMap((season) => season.episodes.map(
    (episode) => `${episode.season_number}:${episode.episode_number}`,
  ));
  const next = new Set(locks);
  for (const field of locks) {
    if (field.includes("@")) continue;
    const scopes = field.startsWith("season.")
      ? seasonScopes
      : field.startsWith("episodes.")
        ? episodeScopes
        : [];
    if (!scopes.length) continue;
    next.delete(field);
    for (const scope of scopes) next.add(lockKey(field, scope));
  }
  return [...next];
}

function identities(values: ExternalIdentity[]) {
  return values.map((identity) => `${identity.provider}=${identity.external_id}`).join("\n");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function sourceText(value: string | undefined) {
  return ({ local: "本地文件", series_fallback: "沿用剧集海报", missing: "缺失", remote: "远程来源" } as Record<string, string>)[value ?? "missing"] ?? value;
}

function text(value: number | null | undefined) { return value === null || value === undefined ? "" : String(value); }
function pad(value: number) { return String(value).padStart(2, "0"); }
