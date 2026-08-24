import { ArrowRight, ArrowsClockwise, CaretDown, CheckCircle, FolderSimple, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import type { NamingPreview, NamingPreviewEntry } from "../../api/types";

type Props = {
  preview: NamingPreview | undefined;
  loading: boolean;
  error: boolean;
  excludedPaths: string[];
  includedPaths: string[];
  onSelectionChange: (excludedPaths: string[], includedPaths: string[]) => void;
  onRefresh: () => void;
};

const statusText: Record<NamingPreviewEntry["status"], string> = {
  rename: "可重命名",
  unchanged: "无需修改",
  review: "需要确认",
  conflict: "存在冲突",
};

const reasonText: Record<string, string> = {
  NON_BANGUMI_CONTENT: "附加内容，默认不重命名",
  BANGUMI_NOT_MATCHED: "未绑定元数据条目，默认不重命名",
  EPISODE_OUTSIDE_BANGUMI_RANGE: "超出元数据集数范围，默认不重命名",
  TARGET_PATH_CONFLICT: "目标文件名冲突",
  NOT_A_RENAME: "没有可执行的重命名差异",
};

export function NamingPreviewPanel({ preview, loading, error, excludedPaths, includedPaths, onSelectionChange, onRefresh }: Props) {
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const groups = useMemo(() => groupByFolder(preview?.entries ?? []), [preview]);

  useEffect(() => {
    const excluded = new Set(excludedPaths);
    const included = new Set(includedPaths);
    setSelectedPaths(new Set(preview?.entries.filter((entry) => included.has(entry.source_relative_path) || (entry.default_selected && !excluded.has(entry.source_relative_path))).map((entry) => entry.source_relative_path) ?? []));
  }, [excludedPaths, includedPaths, preview]);

  useEffect(() => setCollapsedFolders(new Set()), [preview?.media_id]);

  const commitSelection = (next: Set<string>) => {
    setSelectedPaths(next);
    if (!preview) return;
    const excluded = preview.entries.filter((entry) => entry.default_selected && !next.has(entry.source_relative_path)).map((entry) => entry.source_relative_path);
    const included = preview.entries.filter((entry) => !entry.default_selected && next.has(entry.source_relative_path)).map((entry) => entry.source_relative_path);
    onSelectionChange(excluded, included);
  };

  const toggleEntry = (entry: NamingPreviewEntry, selected: boolean) => {
    const next = new Set(selectedPaths);
    if (selected) next.add(entry.source_relative_path);
    else next.delete(entry.source_relative_path);
    commitSelection(next);
  };

  const toggleFolder = (entries: NamingPreviewEntry[], selected: boolean) => {
    const next = new Set(selectedPaths);
    entries.filter(canSelect).forEach((entry) => {
      if (selected) next.add(entry.source_relative_path);
      else next.delete(entry.source_relative_path);
    });
    commitSelection(next);
  };

  return <div className="naming-preview">
    <div className="naming-preview-head">
      <div><strong>重命名预览</strong><small>可逐项取消；当前仍是只读预览</small></div>
      <button className="preview-refresh" type="button" onClick={onRefresh} disabled={loading}>
        <ArrowsClockwise size={16} />{loading ? "分析中" : "更新预览"}
      </button>
    </div>
    {error ? <p className="preview-state error"><WarningCircle size={17} />预览失败，请检查模板后重试</p> : null}
    {!error && loading && !preview ? <p className="preview-state">正在解析媒体文件…</p> : null}
    {preview ? <>
      <div className="preview-counts" aria-label="预览统计">
        <span>{preview.total} 个视频</span>
        <span className="rename">{selectedPaths.size} 个已选择</span>
        {preview.default_skipped_count ? <span className="review">{preview.default_skipped_count} 个默认跳过</span> : null}
        {preview.conflict_count ? <span className="conflict">{preview.conflict_count} 个冲突</span> : null}
      </div>
      <div className="rename-folder-list">
        {groups.map(([folder, entries]) => {
          const selectable = entries.filter(canSelect);
          const allSelected = selectable.length > 0 && selectable.every((entry) => selectedPaths.has(entry.source_relative_path));
          const collapsed = collapsedFolders.has(folder);
          return <section className={`rename-folder ${collapsed ? "collapsed" : ""}`} key={folder}>
            <header className="rename-folder-head">
              <button className="folder-toggle" type="button" aria-expanded={!collapsed} onClick={() => setCollapsedFolders((current) => toggleSetValue(current, folder))}><FolderSimple size={17} /><strong title={folder}>{folder === "." ? "根目录" : folder}</strong><small>{entries.length} 个文件</small><CaretDown size={15} /></button>
              {selectable.length ? <button className="folder-select" type="button" onClick={() => toggleFolder(entries, !allSelected)}>{allSelected ? "取消本文件夹" : "选择本文件夹"}</button> : null}
            </header>
            {!collapsed ? <div className="rename-diff-list">
              {entries.map((entry) => <DiffRow entry={entry} selected={selectedPaths.has(entry.source_relative_path)} onToggle={(checked) => toggleEntry(entry, checked)} key={entry.source_relative_path} />)}
            </div> : null}
          </section>;
        })}
      </div>
    </> : null}
  </div>;
}

function DiffRow({ entry, selected, onToggle }: { entry: NamingPreviewEntry; selected: boolean; onToggle: (selected: boolean) => void }) {
  const episode = entry.parsed.episode_start ?? entry.parsed.absolute_episode_start ?? entry.parsed.special_number;
  const season = entry.parsed.season;
  const meta = [
    entry.parsed.special_type && episode !== null ? `${entry.parsed.special_type} ${pad(episode)}` : season !== null && episode !== null ? `S${pad(season)}E${pad(episode)}` : episode !== null ? `绝对集 ${pad(episode)}` : null,
    entry.parsed.resolution,
    `${Math.round(entry.parsed.confidence)}%`,
  ].filter(Boolean).join(" · ");
  const selectable = canSelect(entry);
  const reason = entry.selection_reason ? reasonText[entry.selection_reason] : null;
  return <div className={`rename-diff ${entry.status} ${selected ? "selected" : "deselected"}`}>
    <label className="diff-select">
      <input type="checkbox" checked={selected} disabled={!selectable} onChange={(event) => onToggle(event.target.checked)} aria-label={`重命名 ${entry.source_name}`} />
      <span>{selected ? "已选择" : "不重命名"}</span>
    </label>
    <div className="diff-main">
      <div className="diff-name"><span title={entry.source_relative_path}>{entry.source_name}</span><ArrowRight size={14} /><strong title={entry.target_relative_path}>{entry.target_name}</strong></div>
      <small>{reason || meta || "未识别季集信息"}</small>
    </div>
    <div className="diff-status">{entry.status === "rename" || entry.status === "unchanged" ? <CheckCircle size={17} weight="fill" /> : <WarningCircle size={17} weight="fill" />}<span>{statusText[entry.status]}</span></div>
  </div>;
}

function canSelect(entry: NamingPreviewEntry) {
  return entry.status === "rename" && entry.source_relative_path !== entry.target_relative_path;
}

function groupByFolder(entries: NamingPreviewEntry[]) {
  const groups = new Map<string, NamingPreviewEntry[]>();
  entries.forEach((entry) => groups.set(entry.folder, [...(groups.get(entry.folder) ?? []), entry]));
  return [...groups.entries()];
}

function toggleSetValue(current: Set<string>, value: string) {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function pad(value: number) { return String(value).padStart(2, "0"); }
