import { ArrowRight, ArrowsClockwise, CaretDown, CheckCircle, FolderSimple, Subtitles, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import type { SubtitleMatchEntry, SubtitleMatchPreview, SubtitleRenameResult } from "../../api/types";

type Props = {
  preview: SubtitleMatchPreview | undefined;
  loading: boolean;
  error: boolean;
  renaming: boolean;
  renameError: boolean;
  result: SubtitleRenameResult | undefined;
  onRefresh: () => void;
  onRename: () => void;
};

const reasonText: Record<string, string> = {
  FOLDER_EXCLUDED: "文件夹已排除",
  SUBTITLE_EMPTY: "字幕文件为空",
  SUBTITLE_VIDEO_AMBIGUOUS: "匹配到多个视频",
  SUBTITLE_VIDEO_NOT_FOUND: "未找到同目录对应剧集",
  SUBTITLE_LANGUAGE_UNKNOWN: "未识别简繁或语言标记",
  SUBTITLE_TARGET_CONFLICT: "多个字幕会生成同一名称",
  SUBTITLE_TARGET_EXISTS: "目标字幕已存在，不会覆盖",
  SUBTITLE_ALREADY_MATCHED: "已能被播放器识别",
};

export function SubtitleMatchPanel({ preview, loading, error, renaming, renameError, result, onRefresh, onRename }: Props) {
  const [confirming, setConfirming] = useState(false);
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const groups = useMemo(() => groupByFolder(preview?.entries ?? []), [preview]);

  useEffect(() => setCollapsedFolders(new Set()), [preview?.media_id]);
  useEffect(() => {
    if (result) setConfirming(false);
  }, [result]);

  return <div className="naming-preview subtitle-preview">
    <div className="naming-preview-head">
      <div><strong>字幕匹配预览</strong><small>按同目录剧集编号匹配；视频文件保持不变</small></div>
      <button className="preview-refresh" type="button" onClick={onRefresh} disabled={loading || renaming}>
        <ArrowsClockwise size={16} />{loading ? "分析中" : "更新预览"}
      </button>
    </div>
    {error ? <p className="preview-state error"><WarningCircle size={17} />字幕分析失败，请检查媒体目录</p> : null}
    {!error && loading && !preview ? <p className="preview-state">正在匹配字幕与剧集文件…</p> : null}
    {preview ? <>
      <div className="preview-counts" aria-label="字幕匹配统计">
        <span>{preview.total} 个字幕</span>
        <span className="rename">{preview.rename_count} 个可重命名</span>
        {preview.unchanged_count ? <span>{preview.unchanged_count} 个已匹配</span> : null}
        {preview.review_count ? <span className="review">{preview.review_count} 个待确认</span> : null}
        {preview.conflict_count ? <span className="conflict">{preview.conflict_count} 个冲突</span> : null}
      </div>
      <div className="rename-folder-list">
        {groups.map(([folder, entries]) => {
          const collapsed = collapsedFolders.has(folder);
          return <section className={`rename-folder ${collapsed ? "collapsed" : ""}`} key={folder}>
            <header className="rename-folder-head">
              <button className="folder-toggle" type="button" aria-expanded={!collapsed} onClick={() => setCollapsedFolders((current) => toggleSetValue(current, folder))}>
                <FolderSimple size={17} /><strong title={folder}>{folder === "." ? "根目录" : folder}</strong><small>{entries.length} 个字幕</small><CaretDown size={15} />
              </button>
            </header>
            {!collapsed ? <div className="rename-diff-list">
              {entries.map((entry) => <SubtitleRow entry={entry} key={entry.source_relative_path} />)}
            </div> : null}
          </section>;
        })}
      </div>
      {preview.total === 0 ? <p className="preview-state">未发现可处理的外置字幕文件。</p> : null}
      {preview.rename_count > 0 ? <div className="subtitle-rename-action">
        <div><strong>将处理 {preview.rename_count} 个字幕</strong><small>采用复制校验后删除源文件；冲突、未匹配与已有目标均会跳过。</small></div>
        {!confirming ? <button className="secondary-button" type="button" onClick={() => setConfirming(true)}>重命名字幕</button> : <div className="subtitle-confirm-actions"><button className="secondary-button" type="button" onClick={() => setConfirming(false)} disabled={renaming}>取消</button><button className="primary-button" type="button" onClick={onRename} disabled={renaming}>{renaming ? "处理中" : "确认重命名"}</button></div>}
      </div> : null}
      {renameError ? <p className="preview-state error"><WarningCircle size={17} />字幕重命名失败；未覆盖任何已有目标文件</p> : null}
      {result ? <p className="preview-state success"><CheckCircle size={17} weight="fill" />已重命名 {result.renamed_files.length} 个字幕，跳过 {result.skipped_files.length} 个。</p> : null}
    </> : null}
  </div>;
}

function SubtitleRow({ entry }: { entry: SubtitleMatchEntry }) {
  const reason = entry.reason ? (reasonText[entry.reason] ?? entry.reason) : "将与对应视频使用相同主文件名";
  const statusLabel = entry.status === "rename" ? "待重命名" : entry.status === "unchanged" ? "已匹配" : entry.status === "conflict" ? "冲突" : "需确认";
  return <div className={`rename-diff subtitle-diff ${entry.status}`}>
    <span className={`subtitle-language ${entry.language_tag ? "known" : ""}`}>{entry.language_tag ?? "未知语言"}</span>
    <div className="diff-main">
      <div className="diff-name"><span title={entry.source_relative_path}>{entry.source_name}</span><ArrowRight size={14} /><strong title={entry.target_relative_path ?? undefined}>{entry.target_name ?? "未匹配"}</strong></div>
      <small>{entry.video_name ? `对应视频：${entry.video_name}` : reason}</small>
    </div>
    <div className="diff-status">{entry.status === "conflict" || entry.status === "review" ? <WarningCircle size={17} weight="fill" /> : entry.status === "rename" ? <Subtitles size={17} weight="fill" /> : <CheckCircle size={17} weight="fill" />}<span title={reason}>{statusLabel}</span></div>
  </div>;
}

function groupByFolder(entries: SubtitleMatchEntry[]) {
  const groups = new Map<string, SubtitleMatchEntry[]>();
  entries.forEach((entry) => groups.set(entry.folder, [...(groups.get(entry.folder) ?? []), entry]));
  return [...groups.entries()];
}

function toggleSetValue(current: Set<string>, value: string) {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}
