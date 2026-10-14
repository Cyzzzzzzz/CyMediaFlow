import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { automationApi } from "./api";
import { AutomationDialog } from "./AutomationDialog";
import {
  featureApi,
  type FilePlan,
  type Mapping,
  type Orphan,
} from "./featureApi";
import type { Download } from "./types";

export function DownloadActions({ job }: { job: Download }) {
  const client = useQueryClient();
  const [mapping, setMapping] = useState(false);
  const [pending, setPending] = useState<{
    action: string;
    plan?: FilePlan;
  } | null>(null);
  const action = useMutation({
    mutationFn: (value: { action: string; confirm?: boolean }) => {
      if (value.action === "revision" || value.action === "revision-restore")
        return featureApi.revision(
          job.id,
          job.naming!.revision_of!,
          !!value.confirm,
          value.action === "revision-restore",
        );
      return featureApi.action(job.id, value.action, !!value.confirm);
    },
    onSuccess: (result, value) => {
      if (
        ["restore", "revision", "revision-restore"].includes(value.action) &&
        !value.confirm
      )
        setPending({ action: value.action, plan: result });
      else {
        setPending(null);
        void client.invalidateQueries({ queryKey: ["automation"] });
      }
    },
  });
  return (
    <details className="download-actions">
      <summary>操作</summary>
      <div className="automation-actions">
        {job.torrent_hash && job.state !== "removed" ? (
          <>
            <button
              className="quiet-button"
              disabled={action.isPending}
              onClick={() =>
                action.mutate({
                  action: job.state === "paused" ? "resume" : "pause",
                })
              }
            >
              {job.state === "paused" ? "继续" : "暂停"}
            </button>
            {job.naming?.downloader !== "aria2" ? (
              <button
                className="quiet-button"
                disabled={action.isPending}
                onClick={() => action.mutate({ action: "recheck" })}
              >
                重新校验
              </button>
            ) : null}
            <button
              className="quiet-button"
              onClick={() => setPending({ action: "remove" })}
            >
              移除任务
            </button>
          </>
        ) : null}
        {job.progress === 100 &&
        ["review", "retry_sync", "waiting_files", "organized"].includes(
          job.state,
        ) ? (
          <>
            <button className="quiet-button" onClick={() => setMapping(true)}>
              文件映射与预览
            </button>
            <button
              className="quiet-button"
              onClick={() => action.mutate({ action: "organize" })}
            >
              继续整理
            </button>
            {!job.naming?.revision_of && job.naming?.downloader !== "aria2" ? (
              <button
                className="quiet-button"
                onClick={() => action.mutate({ action: "restore" })}
              >
                恢复原名称
              </button>
            ) : null}
          </>
        ) : null}
        {job.naming?.revision_of ? (
          <>
            <button
              className="quiet-button"
              onClick={() => action.mutate({ action: "revision" })}
            >
              替换预览
            </button>
            <button
              className="quiet-button"
              onClick={() => action.mutate({ action: "revision-restore" })}
            >
              恢复旧版
            </button>
          </>
        ) : null}
      </div>
      {action.error ? (
        <p role="alert" className="automation-note error">
          {action.error.message}
        </p>
      ) : null}
      {pending ? (
        <AutomationDialog
          title={pending.action === "remove" ? "移除下载任务" : "确认文件操作"}
          onClose={() => setPending(null)}
          busy={action.isPending}
          footer={
            <button
              className="primary-button"
              disabled={action.isPending}
              onClick={() =>
                action.mutate({ action: pending.action, confirm: true })
              }
            >
              确认执行
            </button>
          }
        >
          <p className="automation-note">
            {pending.action === "remove"
              ? "只移除下载器任务，保留媒体文件与下载记录。"
              : "检查文件名变化。旧版本通过下载器保存在隐藏备份目录，可恢复。"}
          </p>
          {pending.plan?.files.map((f, i) => (
            <div className="automation-preview-row" key={i}>
              <span>{f.source}</span>
              <strong>→ {f.target}</strong>
            </div>
          ))}
          {action.error ? <p role="alert">{action.error.message}</p> : null}
        </AutomationDialog>
      ) : null}
      {mapping ? (
        <FileMappingDialog job={job} onClose={() => setMapping(false)} />
      ) : null}
    </details>
  );
}

function FileMappingDialog({
  job,
  onClose,
}: {
  job: Download;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const files = useQuery({
    queryKey: ["automation", "job-files", job.id],
    queryFn: () => featureApi.files(job.id),
  });
  const [mappings, setMappings] = useState<Record<string, Mapping>>({});
  const organize = useMutation({
    mutationFn: (confirm: boolean) =>
      featureApi.organize(job.id, Object.values(mappings), confirm),
    onSuccess: (_data, confirm) => {
      if (confirm) void client.invalidateQueries({ queryKey: ["automation"] });
    },
  });
  function set(path: string, episode: number) {
    setMappings((old) => {
      const next = { ...old };
      if (Number.isNaN(episode)) delete next[path];
      else
        next[path] = { source: path, season: job.naming?.season ?? 1, episode };
      return next;
    });
    organize.reset();
  }
  return (
    <AutomationDialog
      title="文件映射与整理预览"
      onClose={onClose}
      busy={organize.isPending}
    >
      <p className="automation-note">
        编号明确的文件自动识别；缺少集号时手动填写。操作仅作用于此任务。
      </p>
      <div className="automation-form">
        {files.data
          ?.filter((f) => /\.(mkv|mp4|avi|mov|m4v|ts|webm)$/i.test(f.name))
          .map((file) => (
            <label key={file.name}>
              {file.name}
              <input
                aria-label={`集号 ${file.name}`}
                type="number"
                min={0}
                max={999}
                placeholder="自动识别"
                value={mappings[file.name]?.episode ?? ""}
                onChange={(e) => set(file.name, e.target.valueAsNumber)}
              />
            </label>
          ))}
      </div>
      <button
        className="secondary-button"
        disabled={organize.isPending || !files.data}
        onClick={() => organize.mutate(false)}
      >
        生成预览
      </button>
      {organize.data ? (
        <div className="automation-preview">
          {organize.data.files.map((f, i) => (
            <div className="automation-preview-row" key={i}>
              <span>{f.source}</span>
              <strong>→ {f.target}</strong>
            </div>
          ))}
          {!organize.data.executed ? (
            <button
              className="primary-button"
              disabled={organize.isPending}
              onClick={() => organize.mutate(true)}
            >
              确认整理
            </button>
          ) : (
            <p role="status">已执行，状态：{organize.data.state}</p>
          )}
        </div>
      ) : null}
      {organize.error || files.error ? (
        <p role="alert">{(organize.error ?? files.error)?.message}</p>
      ) : null}
    </AutomationDialog>
  );
}

export function OrphanTasks() {
  const [selected, setSelected] = useState<Orphan | null>(null);
  const [ruleId, setRuleId] = useState(0);
  const [episode, setEpisode] = useState(1);
  const rules = useQuery({
    queryKey: ["automation", "rules"],
    queryFn: automationApi.rules,
  });
  const scan = useMutation({ mutationFn: featureApi.orphans });
  const adopt = useMutation({
    mutationFn: () => featureApi.adopt(selected!.hash, ruleId, episode),
    onSuccess: () => {
      setSelected(null);
      scan.mutate();
    },
  });
  return (
    <details className="subscription-section">
      <summary>孤儿任务</summary>
      <div className="subscription-section-body">
        <p className="automation-note">
          只列出带 CyMediaFlow 标签但没有本地跟踪记录的 qBittorrent 任务。
        </p>
        <button
          className="secondary-button"
          disabled={scan.isPending}
          onClick={() => scan.mutate()}
        >
          检查孤儿任务
        </button>
        {scan.data?.map((job) => (
          <article className="automation-card" key={job.hash}>
            <div>
              <strong>{job.name}</strong>
              <span>{job.save_path}</span>
            </div>
            <button className="quiet-button" onClick={() => setSelected(job)}>
              关联规则
            </button>
          </article>
        ))}
        {scan.isSuccess && !scan.data.length ? <p>没有发现孤儿任务。</p> : null}
        {scan.error ? <p role="alert">{scan.error.message}</p> : null}
      </div>
      {selected ? (
        <AutomationDialog
          title="关联孤儿任务"
          onClose={() => setSelected(null)}
        >
          <div className="automation-form">
            <p>{selected.name}</p>
            <label>
              追番规则
              <select
                value={ruleId}
                onChange={(e) => setRuleId(Number(e.target.value))}
              >
                <option value={0}>请选择</option>
                {rules.data?.map((r) => (
                  <option value={r.id} key={r.id}>
                    {r.title} S{r.season}
                  </option>
                ))}
              </select>
            </label>
            <label>
              目标集号
              <input
                type="number"
                min={0}
                max={999}
                value={episode}
                onChange={(e) => setEpisode(Number(e.target.value))}
              />
            </label>
            <button
              className="primary-button"
              disabled={!ruleId || adopt.isPending}
              onClick={() => adopt.mutate()}
            >
              确认关联
            </button>
            {adopt.error ? <p role="alert">{adopt.error.message}</p> : null}
          </div>
        </AutomationDialog>
      ) : null}
    </details>
  );
}
