import { ArrowRight, ArrowsClockwise, CaretDown, CheckCircle, FileText, FolderSimple, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import type { NfoPreview, NfoPreviewEntry } from "../../api/types";

type Props = {
  preview: NfoPreview | undefined;
  loading: boolean;
  error: boolean;
  excludedPaths: string[];
  excludedFolders: string[];
  renameFolders: string[];
  includedPaths: string[];
  onSelectionChange: (excludedPaths: string[], includedPaths: string[], excludedFolders: string[]) => void;
  onRenameFoldersChange: (renameFolders: string[]) => void;
  onRefresh: () => void;
};

const actionText: Record<NfoPreviewEntry["action"], string> = {
  create: "待生成",
  rename: "仅改 NFO 名",
  unchanged: "已同名",
  review: "默认跳过",
  conflict: "存在冲突",
};

const reasonText: Record<string, string> = {
  NON_BANGUMI_CONTENT: "附加内容，默认不处理",
  BANGUMI_NOT_MATCHED: "未绑定元数据条目，默认不处理",
  EPISODE_OUTSIDE_BANGUMI_RANGE: "超出元数据集数范围，默认不处理",
  TARGET_NFO_CONFLICT: "目标 NFO 名称冲突",
  AMBIGUOUS_NFO_PAIRING: "存在多个视频或 NFO 候选，需人工确认",
  NFO_ACTION_NOT_REQUIRED: "NFO 已与视频同名或无需处理",
  SINGLE_EPISODE_MAPPING_REQUIRES_ONE_VIDEO: "单文件映射要求目录内恰好有一个正片视频",
  INVALID_LOCAL_EPISODE_NUMBER: "调整后的 Emby 集号必须大于 0",
  EPISODE_SOURCE_NOT_MAPPED: "尚未配置覆盖此分集的来源规则",
  FOLDER_EXCLUDED: "已手动排除文件夹",
};

export function NfoPreviewPanel({ preview, loading, error, excludedPaths, excludedFolders, renameFolders, includedPaths, onSelectionChange, onRenameFoldersChange, onRefresh }: Props) {
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const groups = useMemo(() => groupByFolder(preview?.entries ?? []), [preview]);

  useEffect(() => {
    const excluded = new Set(excludedPaths);
    const included = new Set(includedPaths);
    setSelectedPaths(new Set(preview?.entries.filter((entry) => !folderIsExcluded(entry.folder, excludedFolders) && (included.has(entry.target_nfo_relative_path) || (entry.default_selected && !excluded.has(entry.target_nfo_relative_path)))).map((entry) => entry.target_nfo_relative_path) ?? []));
  }, [excludedFolders, excludedPaths, includedPaths, preview]);

  useEffect(() => setCollapsedFolders(new Set()), [preview?.media_id]);

  const commitSelection = (next: Set<string>, explicitExcluded = new Set(excludedPaths), nextExcludedFolders = excludedFolders) => {
    setSelectedPaths(next);
    if (!preview) return;
    preview.entries.forEach((entry) => {
      if (next.has(entry.target_nfo_relative_path)) explicitExcluded.delete(entry.target_nfo_relative_path);
      else if (entry.default_selected && !folderIsExcluded(entry.folder, nextExcludedFolders)) explicitExcluded.add(entry.target_nfo_relative_path);
    });
    const excluded = [...explicitExcluded];
    const included = preview.entries.filter((entry) => !entry.default_selected && next.has(entry.target_nfo_relative_path)).map((entry) => entry.target_nfo_relative_path);
    onSelectionChange(excluded, included, nextExcludedFolders);
  };

  const toggleEntry = (entry: NfoPreviewEntry, selected: boolean) => {
    const next = new Set(selectedPaths);
    if (selected) next.add(entry.target_nfo_relative_path);
    else next.delete(entry.target_nfo_relative_path);
    commitSelection(next);
  };

  const toggleFolder = (entries: NfoPreviewEntry[], selected: boolean) => {
    const next = new Set(selectedPaths);
    const explicitExcluded = new Set(excludedPaths);
    entries.filter(canSelect).forEach((entry) => {
      if (selected) {
        next.add(entry.target_nfo_relative_path);
        explicitExcluded.delete(entry.target_nfo_relative_path);
      } else {
        next.delete(entry.target_nfo_relative_path);
        explicitExcluded.add(entry.target_nfo_relative_path);
      }
    });
    commitSelection(next, explicitExcluded);
  };

  const toggleExplicitSkip = (entry: NfoPreviewEntry) => {
    const next = new Set(selectedPaths);
    const explicitExcluded = new Set(excludedPaths);
    if (explicitExcluded.has(entry.target_nfo_relative_path)) {
      explicitExcluded.delete(entry.target_nfo_relative_path);
    } else {
      next.delete(entry.target_nfo_relative_path);
      explicitExcluded.add(entry.target_nfo_relative_path);
    }
    commitSelection(next, explicitExcluded);
  };

  const toggleFolderExclusion = (folder: string, entries: NfoPreviewEntry[]) => {
    const next = new Set(selectedPaths);
    const directExcludedFolder = excludedFolders.find((candidate) => normalizeFolder(candidate) === normalizeFolder(folder));
    const nextExcludedFolders = new Set(excludedFolders);
    if (directExcludedFolder) {
      nextExcludedFolders.delete(directExcludedFolder);
      entries.filter((entry) => entry.default_selected && !excludedPaths.includes(entry.target_nfo_relative_path)).forEach((entry) => next.add(entry.target_nfo_relative_path));
    } else {
      nextExcludedFolders.add(folder);
      entries.forEach((entry) => next.delete(entry.target_nfo_relative_path));
    }
    commitSelection(next, new Set(excludedPaths), [...nextExcludedFolders]);
  };

  return <div className="naming-preview nfo-preview">
    <div className="naming-preview-head">
      <div><strong>NFO 文件预览</strong><small>优先显示上次分析缓存；视频文件名保持不变</small></div>
      <button className="preview-refresh" type="button" onClick={onRefresh} disabled={loading}>
        <ArrowsClockwise size={16} />{loading ? "分析中" : "更新预览"}
      </button>
    </div>
    {error ? <p className="preview-state error"><WarningCircle size={17} />预览失败，请检查映射后重试</p> : null}
    {!error && loading && !preview ? <p className="preview-state">正在检查视频与 NFO 配对…</p> : null}
    {preview ? <>
      <div className="preview-counts" aria-label="NFO 预览统计">
        <span>{preview.total} 个视频</span>
        <span className="rename">{selectedPaths.size} 项待处理</span>
        {preview.unchanged_count ? <span>{preview.unchanged_count} 个已配对</span> : null}
        {preview.default_skipped_count ? <span className="review">{preview.default_skipped_count} 个默认跳过</span> : null}
        {preview.conflict_count ? <span className="conflict">{preview.conflict_count} 个冲突</span> : null}
      </div>
      <div className="rename-folder-list">
        {groups.map(([folder, entries]) => {
          const selectable = entries.filter(canSelect);
          const allSelected = selectable.length > 0 && selectable.every((entry) => selectedPaths.has(entry.target_nfo_relative_path));
          const collapsed = collapsedFolders.has(folder);
          const directlyExcluded = excludedFolders.some((candidate) => normalizeFolder(candidate) === normalizeFolder(folder));
          const inheritedExcluded = !directlyExcluded && folderIsExcluded(folder, excludedFolders);
          const usesStandardName = renameFolders.some((candidate) => normalizeFolder(candidate) === normalizeFolder(folder));
          return <section className={`rename-folder ${collapsed ? "collapsed" : ""}`} key={folder}>
            <header className="rename-folder-head">
              <button className="folder-toggle" type="button" aria-expanded={!collapsed} onClick={() => setCollapsedFolders((current) => toggleSetValue(current, folder))}><FolderSimple size={17} /><strong title={folder}>{folder === "." ? "根目录" : folder}</strong><small>{entries.length} 个文件</small><CaretDown size={15} /></button>
              <div className="folder-actions">
                <label className={`folder-rename ${usesStandardName ? "active" : ""}`} title="仅修改本文件夹内的分集 NFO 名称，不修改视频文件">
                  <input type="checkbox" checked={usesStandardName} onChange={(event) => onRenameFoldersChange(toggleFolderValue(renameFolders, folder, event.target.checked))} />NFO：标题 SxxExx
                </label>
                {selectable.length && !directlyExcluded && !inheritedExcluded ? <button className="folder-select" type="button" onClick={() => toggleFolder(entries, !allSelected)}>{allSelected ? "取消本文件夹" : "选择本文件夹"}</button> : null}
                <button className={`folder-exclude ${directlyExcluded || inheritedExcluded ? "active" : ""}`} type="button" disabled={inheritedExcluded} onClick={() => toggleFolderExclusion(folder, entries)}>{directlyExcluded ? "取消排除" : inheritedExcluded ? "已随上级排除" : "排除并添加 .ignore"}</button>
              </div>
            </header>
            {!collapsed ? <div className="rename-diff-list">
              {entries.map((entry) => <NfoRow entry={entry} selected={selectedPaths.has(entry.target_nfo_relative_path)} explicitlySkipped={excludedPaths.includes(entry.target_nfo_relative_path)} folderExcluded={directlyExcluded || inheritedExcluded} onToggle={(checked) => toggleEntry(entry, checked)} onSkip={() => toggleExplicitSkip(entry)} key={entry.video_relative_path} />)}
            </div> : null}
          </section>;
        })}
      </div>
      {excludedFolders.length ? <p className="preview-ignore-hint">保存配置时会在手动排除的文件夹内创建 `.ignore`；取消排除不会自动删除已有标记。</p> : null}
    </> : null}
  </div>;
}

function NfoRow({ entry, selected, explicitlySkipped, folderExcluded, onToggle, onSkip }: { entry: NfoPreviewEntry; selected: boolean; explicitlySkipped: boolean; folderExcluded: boolean; onToggle: (selected: boolean) => void; onSkip: () => void }) {
  const selectable = canSelect(entry);
  const sourceName = entry.source_nfo_name ?? (entry.action === "create" ? "尚无 NFO" : entry.video_name);
  const reason = folderExcluded ? reasonText.FOLDER_EXCLUDED : entry.selection_reason ? reasonText[entry.selection_reason] : null;
  const visibleAction = entry.action === "unchanged" && selected ? "待更新" : !selected && reason && (entry.action === "create" || entry.action === "rename" || entry.action === "unchanged") ? "默认跳过" : actionText[entry.action];
  return <div className={`rename-diff ${entry.action === "create" ? "rename" : entry.action} ${selected ? "selected" : "deselected"}`}>
    <label className="diff-select">
      <input type="checkbox" checked={selected} disabled={!selectable || folderExcluded} onChange={(event) => onToggle(event.target.checked)} aria-label={`处理 NFO ${entry.target_nfo_name}`} />
      <span>{selected ? "已选择" : "不处理"}</span>
    </label>
    <div className="diff-main">
      <div className="diff-name"><span title={entry.source_nfo_relative_path ?? entry.video_relative_path}>{sourceName}</span><ArrowRight size={14} /><strong title={entry.target_nfo_relative_path}>{entry.target_nfo_name}</strong></div>
      <small>{reason || `对应视频：${entry.video_name}`}</small>
    </div>
    <div className="diff-status">{entry.action === "conflict" || entry.action === "review" ? <WarningCircle size={17} weight="fill" /> : entry.action === "create" ? <FileText size={17} weight="fill" /> : <CheckCircle size={17} weight="fill" />}<span>{visibleAction}</span>{entry.selection_reason === "EPISODE_SOURCE_NOT_MAPPED" ? <button className="explicit-skip" type="button" onClick={onSkip}>{explicitlySkipped ? "取消跳过" : "跳过此文件"}</button> : null}</div>
  </div>;
}

function canSelect(entry: NfoPreviewEntry) {
  return entry.action === "create" || entry.action === "rename" || entry.action === "unchanged";
}

function groupByFolder(entries: NfoPreviewEntry[]) {
  const groups = new Map<string, NfoPreviewEntry[]>();
  entries.forEach((entry) => groups.set(entry.folder, [...(groups.get(entry.folder) ?? []), entry]));
  return [...groups.entries()];
}

function toggleSetValue(current: Set<string>, value: string) {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function toggleFolderValue(folders: string[], folder: string, enabled: boolean) {
  const normalized = normalizeFolder(folder);
  const next = folders.filter((candidate) => normalizeFolder(candidate) !== normalized);
  if (enabled) next.push(folder);
  return next;
}

function folderIsExcluded(folder: string, excludedFolders: string[]) {
  const normalized = normalizeFolder(folder);
  return excludedFolders.some((excludedFolder) => {
    const excluded = normalizeFolder(excludedFolder);
    return excluded === "." || normalized === excluded || normalized.startsWith(`${excluded}/`);
  });
}

function normalizeFolder(folder: string) {
  return folder.replaceAll("\\", "/").replace(/^\/+|\/+$/g, "").toLocaleLowerCase() || ".";
}
