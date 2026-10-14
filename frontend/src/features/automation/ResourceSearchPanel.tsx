import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { automationApi } from "./api";
import { AutomationDialog } from "./AutomationDialog";
import { featureApi } from "./featureApi";
import { SubscriptionFields } from "./SubscriptionFields";
import { emptySubscription, validSubscription } from "./subscriptionForm";
import type { Release, SubscriptionDraft } from "./types";

export function ReleaseReviewDialog({
  release,
  onClose,
}: {
  release: Release;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const rules = useQuery({
    queryKey: ["automation", "rules"],
    queryFn: automationApi.rules,
  });
  const [ruleId, setRuleId] = useState(0);
  const [episode, setEpisode] = useState<number | null>(
    release.analysis.episode,
  );
  const selected = rules.data?.find((r) => r.id === ruleId);
  const preview = useMutation({
    mutationFn: () => featureApi.download(release.id, ruleId, false, episode),
  });
  const download = useMutation({
    mutationFn: () => featureApi.download(release.id, ruleId, true, episode),
    onSuccess: () => client.invalidateQueries({ queryKey: ["automation"] }),
  });
  const suggest = useMutation({
    mutationFn: () => featureApi.suggest(release.title),
  });
  const error = preview.error ?? download.error ?? suggest.error;
  return (
    <AutomationDialog
      title="确认下载与剧集映射"
      onClose={onClose}
      busy={download.isPending}
    >
      <p className="automation-note">{release.title}</p>
      <div className="automation-form">
        <label>
          使用追番规则
          <select
            value={ruleId}
            onChange={(e) => {
              const id = Number(e.target.value);
              setRuleId(id);
              const rule = rules.data?.find((r) => r.id === id);
              setEpisode(
                release.analysis.episode === null
                  ? null
                  : release.analysis.episode + (rule?.episode_offset ?? 0),
              );
              preview.reset();
            }}
          >
            <option value={0}>请选择目标作品</option>
            {rules.data?.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title} · S{r.season + r.season_offset} ·{" "}
                {r.preferred_group || "不限字幕组"}
              </option>
            ))}
          </select>
        </label>
        <label>
          目标集号（Emby）
          <input
            type="number"
            min={0}
            max={999}
            value={episode ?? ""}
            onChange={(e) => {
              setEpisode(e.target.value === "" ? null : Number(e.target.value));
              preview.reset();
            }}
          />
        </label>
        <p className="automation-note">
          {selected?.allow_batch
            ? "合集按下载后的每个视频分别映射，请检查文件级预览。"
            : "请核对目标季度与集号，手动确认会使用这条规则的目录和下载器。"}
        </p>
        <div className="automation-actions">
          <button
            className="secondary-button"
            disabled={!ruleId || preview.isPending}
            onClick={() => preview.mutate()}
          >
            预览下载
          </button>
          <button
            className="quiet-button"
            disabled={suggest.isPending}
            onClick={() => suggest.mutate()}
          >
            辅助解析
          </button>
        </div>
        {suggest.data ? (
          <div className="automation-note">
            建议：{suggest.data.suggestion.title} · S
            {suggest.data.suggestion.season ?? "?"}E
            {suggest.data.suggestion.episode ?? "?"}
            <button
              className="quiet-button"
              onClick={() => {
                setEpisode(
                  suggest.data.suggestion.episode === null
                    ? null
                    : suggest.data.suggestion.episode +
                        (selected?.episode_offset ?? 0),
                );
                preview.reset();
              }}
            >
              采用集号建议
            </button>
            <small>需人工核对。建议不会自动创建任务。</small>
          </div>
        ) : null}
        {preview.data ? (
          <div className="automation-preview">
            <p>
              {preview.data.target_title} · S{preview.data.season}E
              {preview.data.episode ?? "合集"}
            </p>
            {preview.data.existing_job ? (
              <p>已有任务 #{preview.data.existing_job}</p>
            ) : (
              <button
                className="primary-button"
                disabled={download.isPending}
                onClick={() => download.mutate()}
              >
                确认下载
              </button>
            )}
          </div>
        ) : null}
        {download.data ? (
          <p role="status">
            {download.data.confirmed
              ? "已在下载器确认创建"
              : `任务状态：${download.data.state ?? "等待确认"}`}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="automation-note error">
            {error.message}
          </p>
        ) : null}
      </div>
    </AutomationDialog>
  );
}

export function ResourceSearchPanel() {
  const client = useQueryClient();
  const config = useQuery({
    queryKey: ["automation", "features"],
    queryFn: featureApi.settings,
  });
  const defaults = useQuery({
    queryKey: ["automation", "settings"],
    queryFn: automationApi.settings,
  });
  const cache = useQuery({
    queryKey: ["automation", "resource-search"],
    queryFn: featureApi.searchCache,
  });
  const [source, setSource] = useState("mikan");
  const sources = config.data?.sources.filter((s) => s.enabled) ?? [];
  const activeSource = sources.some((s) => s.id === source)
    ? source
    : (sources[0]?.id ?? "");
  const [query, setQuery] = useState("");
  const [review, setReview] = useState<Release | null>(null);
  const [draft, setDraft] = useState<SubscriptionDraft | null>(null);
  const [filter, setFilter] = useState("");
  const search = useMutation({
    mutationFn: () => featureApi.search(activeSource, query),
    onSuccess: (result) =>
      client.setQueryData(["automation", "resource-search"], result),
  });
  const subscribe = useMutation({
    mutationFn: () => featureApi.subscribe(cache.data!.feed_id!, draft!),
    onSuccess: () => {
      setDraft(null);
      void client.invalidateQueries({ queryKey: ["automation", "rules"] });
      void client.invalidateQueries({ queryKey: ["automation", "feeds"] });
    },
  });
  return (
    <section className="automation-panel">
      <div className="automation-panel-head">
        <div>
          <h2>资源搜索</h2>
          <p>保留上一次结果；点击搜索才访问站点。</p>
        </div>
      </div>
      <form
        className="automation-inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim() && activeSource) search.mutate();
        }}
      >
        <select
          aria-label="资源搜索站点"
          value={activeSource}
          onChange={(e) => setSource(e.target.value)}
        >
          {config.data?.sources
            .filter((s) => s.enabled)
            .map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
        </select>
        <input
          aria-label="资源搜索关键词"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={cache.data?.query || "输入番剧名称"}
        />
        <button
          className="primary-button"
          disabled={search.isPending || !query.trim() || !activeSource}
        >
          {search.isPending ? "搜索中…" : "搜索资源"}
        </button>
      </form>
      {search.error ? (
        <p role="alert" className="automation-note error">
          {search.error.message}
        </p>
      ) : null}
      {cache.data?.query ? (
        <p className="automation-note">
          上次搜索：{cache.data.query} · {cache.data.items.length} 条
        </p>
      ) : null}
      <input
        className="automation-filter"
        aria-label="筛选搜索结果"
        placeholder="筛选字幕组、清晰度或名称"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div className="automation-card-list">
        {cache.data?.items
          .filter((r) => r.title.toLowerCase().includes(filter.toLowerCase()))
          .map((release) => (
            <article className="automation-card" key={release.id}>
              <div>
                <strong>{release.title}</strong>
                <span>
                  {release.analysis.group ?? "未知字幕组"} ·{" "}
                  {release.analysis.resolution ?? "未知清晰度"} · E
                  {release.analysis.episode ?? "待映射"}
                </span>
              </div>
              <button
                className="secondary-button"
                onClick={() => setReview(release)}
              >
                下载
              </button>
              <button
                className="quiet-button"
                onClick={() =>
                  setDraft({
                    ...emptySubscription(
                      defaults.data?.default_exclude_keywords,
                    ),
                    title: release.analysis.title ?? release.title,
                    source_title: release.analysis.title ?? "",
                    season: release.analysis.season ?? 1,
                    preferred_group: release.analysis.group,
                    preferred_resolution: release.analysis.resolution,
                  })
                }
              >
                订阅
              </button>
            </article>
          ))}
      </div>
      {!cache.data?.items.length ? (
        <p className="page-state">搜索后可选择单次下载或持续订阅。</p>
      ) : null}
      {review ? (
        <ReleaseReviewDialog release={review} onClose={() => setReview(null)} />
      ) : null}
      {draft ? (
        <AutomationDialog
          title="从搜索创建订阅"
          onClose={() => setDraft(null)}
          busy={subscribe.isPending}
          footer={
            <button
              className="primary-button"
              disabled={!validSubscription(draft) || subscribe.isPending}
              onClick={() => subscribe.mutate()}
            >
              确认订阅
            </button>
          }
        >
          <SubscriptionFields value={draft} onChange={setDraft} />
          <p className="automation-note">
            订阅此搜索 RSS，按这里的作品与过滤条件接收后续发布。
          </p>
          {subscribe.error ? (
            <p role="alert">{subscribe.error.message}</p>
          ) : null}
        </AutomationDialog>
      ) : null}
    </section>
  );
}
