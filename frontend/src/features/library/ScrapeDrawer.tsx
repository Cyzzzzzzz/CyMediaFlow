import { CaretDown, CheckCircle, Cube, FileText, FilmSlate, FloppyDisk, IdentificationBadge, ListNumbers, MagnifyingGlass, X } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { imageSource } from "../../api/images";
import type { LocalScrapeInfo, MediaBinding, MediaItem, MetadataCandidate } from "../../api/types";
import { libraryApi } from "./api";
import { NfoPreviewPanel } from "./NfoPreviewPanel";
import { ScrapeInfoPanel } from "./ScrapeInfoPanel";

type Props = { item: MediaItem; onClose: () => void };
type Section = "match" | "scrape" | "season" | "nfo" | "emby";
type Provider = "bangumi" | "tmdb";
const defaults: MediaBinding = {
  bangumi_id: null, tmdb_id: null, preferred_title: null, content_kind: "series", year: null,
  season_number: 1, episode_offset: 0, folder_template: "{title} ({year})/Season {season:02}",
  filename_template: "{title} S{season:02}E{episode:02}", emby_enabled: true, image_url: null, metadata: {},
};
const emptyPaths: string[] = [];

export function ScrapeDrawer({ item, onClose }: Props) {
  const client = useQueryClient();
  const nfoBangumiId = item.external_ids.find((identity) => identity.provider === "bangumi")?.external_id ?? null;
  const nfoTmdbId = item.external_ids.find((identity) => identity.provider === "tmdb")?.external_id ?? null;
  const initialProvider = (item.binding?.metadata.primary_provider === "tmdb" || (!item.binding?.bangumi_id && item.binding?.tmdb_id)) ? "tmdb" : "bangumi";
  const [openSection, setOpenSection] = useState<Section>("match");
  const [provider, setProvider] = useState<Provider>(initialProvider);
  const [query, setQuery] = useState(item.title);
  const [submittedQuery, setSubmittedQuery] = useState(item.title);
  const [form, setForm] = useState<MediaBinding>(defaults);
  const [detailId, setDetailId] = useState<string | null>(initialProvider === "tmdb" ? (item.binding?.tmdb_id ?? nfoTmdbId) : (item.binding?.bangumi_id ?? nfoBangumiId));
  const effectiveExternalId = provider === "tmdb" ? (form.tmdb_id || nfoTmdbId) : (form.bangumi_id || nfoBangumiId);
  const providerSeasonNumber = provider === "tmdb" ? numberValue(form.metadata.tmdb_season_number, form.season_number) : form.season_number;
  const episodeMappingMode = mappingMode(form.metadata.nfo_episode_mapping_mode);
  const localEpisodeNumber = numberValue(form.metadata.nfo_local_episode_number, 1);
  const providerEpisodeNumber = numberValue(form.metadata.nfo_provider_episode_number, 1);
  const localEpisodeOffset = numberValue(form.metadata.nfo_local_episode_offset, 0);
  const binding = useQuery({ queryKey: ["binding", item.id], queryFn: () => libraryApi.binding(item.id) });
  const candidates = useQuery({ queryKey: ["candidates", item.id, submittedQuery, provider], queryFn: () => libraryApi.candidates(item.id, submittedQuery, provider), enabled: !!submittedQuery.trim(), retry: false });
  const metadataDetail = useQuery({
    queryKey: ["metadata-detail", item.id, provider, detailId],
    queryFn: () => libraryApi.metadataDetail(item.id, detailId!, provider),
    enabled: !!detailId,
    retry: false,
  });
  const metadataEpisodes = useQuery({
    queryKey: ["metadata-episodes", item.id, provider, effectiveExternalId, providerSeasonNumber],
    queryFn: () => libraryApi.metadataEpisodes(item.id, effectiveExternalId!, provider, providerSeasonNumber),
    enabled: openSection === "scrape" && !!effectiveExternalId,
    retry: false,
  });
  const scrapeInfo = useQuery({
    queryKey: ["scrape-info", item.id],
    queryFn: () => libraryApi.scrapeInfo(item.id),
    enabled: openSection === "scrape",
    retry: false,
  });
  const nfoPreview = useQuery({
    queryKey: ["nfo-preview", item.id, form.season_number, form.episode_offset, episodeMappingMode, localEpisodeNumber, providerEpisodeNumber, localEpisodeOffset, effectiveExternalId],
    queryFn: () => libraryApi.nfoPreview(item.id, form),
    enabled: openSection === "nfo",
    retry: false,
  });
  const save = useMutation({
    mutationFn: () => libraryApi.saveBinding(item.id, form),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["library"] }); void client.invalidateQueries({ queryKey: ["binding", item.id] }); },
  });
  const generateNfo = useMutation({
    mutationFn: async () => {
      await libraryApi.saveBinding(item.id, form);
      return libraryApi.generateNfo(item.id, form, provider, effectiveExternalId);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["scrape-info", item.id] });
      void client.invalidateQueries({ queryKey: ["nfo-preview", item.id] });
      void client.invalidateQueries({ queryKey: ["library"] });
    },
  });
  const scrapeMetadata = useMutation({
    mutationFn: () => libraryApi.metadataDetail(item.id, effectiveExternalId!, provider),
    onSuccess: (detail) => {
      setDetailId(detail.external_id);
      client.setQueryData(["metadata-detail", item.id, provider, detail.external_id], detail);
      setForm((current) => ({
        ...current,
        preferred_title: current.preferred_title || detail.title,
        year: current.year || detail.year,
        image_url: detail.image_url || current.image_url,
        metadata: {
          ...current.metadata,
          primary_provider: provider,
          [`${provider}_candidate_title`]: detail.title,
          [`${provider}_original_title`]: detail.original_title,
          [`${provider}_episode_count`]: detail.episode_count,
          [`${provider}_summary`]: detail.summary,
        },
      }));
    },
  });

  useEffect(() => {
    if (!binding.data) return;
    setForm(binding.data);
    const savedProvider: Provider = binding.data.metadata.primary_provider === "tmdb" || (!binding.data.bangumi_id && !!binding.data.tmdb_id) ? "tmdb" : "bangumi";
    setProvider(savedProvider);
    setDetailId(savedProvider === "tmdb" ? (binding.data.tmdb_id ?? nfoTmdbId) : (binding.data.bangumi_id ?? nfoBangumiId));
  }, [binding.data, nfoBangumiId, nfoTmdbId]);
  useEffect(() => {
    const detail = metadataDetail.data;
    if (!detail) return;
    setForm((current) => (provider === "tmdb" ? current.tmdb_id : current.bangumi_id) !== detail.external_id ? current : ({
      ...current,
      preferred_title: current.preferred_title || detail.title,
      year: current.year || detail.year,
      image_url: detail.image_url || current.image_url,
      metadata: {
        ...current.metadata,
        primary_provider: provider,
        [`${provider}_candidate_title`]: detail.title,
        [`${provider}_original_title`]: detail.original_title,
        [`${provider}_episode_count`]: detail.episode_count,
        [`${provider}_summary`]: detail.summary,
      },
    }));
  }, [form.bangumi_id, form.tmdb_id, metadataDetail.data, provider]);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const chooseCandidate = (candidate: MetadataCandidate) => {
    setDetailId(candidate.external_id);
    setForm((current) => ({
      ...current,
      [candidate.provider === "tmdb" ? "tmdb_id" : "bangumi_id"]: candidate.external_id,
      preferred_title: candidate.title,
      year: candidate.year,
      image_url: candidate.image_url,
      metadata: {
        ...current.metadata,
        primary_provider: candidate.provider,
        [`${candidate.provider}_episode_count`]: candidate.episode_count,
        [`${candidate.provider}_candidate_title`]: candidate.title,
        [`${candidate.provider}_original_title`]: candidate.original_title,
        [`${candidate.provider}_summary`]: candidate.summary,
      },
    }));
  };

  const changeProvider = (next: Provider) => {
    scrapeMetadata.reset();
    setProvider(next);
    setForm((current) => ({ ...current, metadata: { ...current.metadata, primary_provider: next } }));
    setDetailId(next === "tmdb" ? (form.tmdb_id || nfoTmdbId) : (form.bangumi_id || nfoBangumiId));
  };

  const cover = imageSource(form.image_url || item.poster_url);

  return <div className="drawer-layer" role="presentation" onMouseDown={onClose}>
    <aside className="scrape-drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" onMouseDown={(event) => event.stopPropagation()}>
      <header className="drawer-header">
        <div className="drawer-cover">{cover ? <img src={cover} alt="" /> : null}</div>
        <div><h2 id="drawer-title">{item.title}</h2><p title={item.path}>{item.path}</p></div>
        <button className="icon-button" type="button" onClick={onClose} aria-label="关闭"><X size={21} /></button>
      </header>
      <div className="drawer-scroll">
        <Accordion icon={<IdentificationBadge size={21} />} title="作品匹配" summary={effectiveExternalId ? `${provider === "tmdb" ? "TMDB" : "Bangumi"} #${effectiveExternalId}` : "尚未匹配"} open={openSection === "match"} onToggle={() => setOpenSection("match")}>
          <div className="provider-tabs" role="tablist" aria-label="元数据来源">
            <button type="button" className={provider === "bangumi" ? "active" : ""} onClick={() => changeProvider("bangumi")}>Bangumi</button>
            <button type="button" className={provider === "tmdb" ? "active" : ""} onClick={() => changeProvider("tmdb")}>TMDB</button>
          </div>
          <span className="field-caption">搜索{provider === "tmdb" ? " TMDB" : "番剧"}</span>
          <form className="candidate-search" onSubmit={(event) => { event.preventDefault(); setSubmittedQuery(query); }}>
            <MagnifyingGlass size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} aria-label={`搜索 ${provider}`} /><button type="submit">搜索</button>
          </form>
          <div className="candidate-list">
            {candidates.isLoading ? <p className="subtle">正在搜索 {provider === "tmdb" ? "TMDB" : "Bangumi"}…</p> : null}
            {candidates.isError ? <p className="notice">搜索失败，请检查该来源的 Token 与网络配置。</p> : null}
            {candidates.data?.slice(0, 3).map((candidate) => <button key={`${candidate.provider}-${candidate.external_id}`} className={`candidate ${(candidate.provider === "tmdb" ? form.tmdb_id : form.bangumi_id) === candidate.external_id ? "selected" : ""}`} type="button" onClick={() => chooseCandidate(candidate)}>
              {imageSource(candidate.image_url) ? <img src={imageSource(candidate.image_url)!} alt="" /> : <span />}
              <span><strong>{candidate.title}</strong><small>{candidate.original_title || candidate.title} · #{candidate.external_id}</small></span>
              {(candidate.provider === "tmdb" ? form.tmdb_id : form.bangumi_id) === candidate.external_id ? <CheckCircle size={28} weight="fill" /> : null}
            </button>)}
          </div>
          <div className="field-grid match-fields">
            <Field label="Bangumi ID"><input inputMode="numeric" value={form.bangumi_id ?? ""} onChange={(e) => setForm({ ...form, bangumi_id: e.target.value || null })} onBlur={() => provider === "bangumi" && setDetailId(form.bangumi_id)} /></Field>
            <Field label="TMDB ID"><input inputMode="numeric" value={form.tmdb_id ?? ""} onChange={(e) => setForm({ ...form, tmdb_id: e.target.value || null })} onBlur={() => provider === "tmdb" && setDetailId(form.tmdb_id)} /></Field>
            <Field label="首选标题"><input value={form.preferred_title ?? ""} onChange={(e) => setForm({ ...form, preferred_title: e.target.value || null })} /></Field>
          </div>
        </Accordion>
        <Accordion icon={<FilmSlate size={21} />} title="刮削信息" summary={scrapeSummary(scrapeInfo.data)} open={openSection === "scrape"} onToggle={() => setOpenSection("scrape")}>
          <ScrapeInfoPanel
            mediaId={item.id}
            provider={provider}
            localInfo={scrapeInfo.data}
            providerInfo={metadataDetail.data}
            providerEpisodes={metadataEpisodes.data}
            providerEpisodesLoading={metadataEpisodes.isFetching}
            providerEpisodesError={metadataEpisodes.isError}
            seasonNumber={form.season_number}
            episodeOffset={form.episode_offset}
            loading={scrapeInfo.isLoading || metadataDetail.isLoading}
            error={scrapeInfo.isError && metadataDetail.isError}
            onGenerate={() => generateNfo.mutate()}
            generating={generateNfo.isPending}
            generationError={generateNfo.isError}
            generationResult={generateNfo.data}
            canScrapeMetadata={!!effectiveExternalId}
            onScrapeMetadata={() => scrapeMetadata.mutate()}
            scrapingMetadata={scrapeMetadata.isPending}
            scrapeMetadataSuccess={scrapeMetadata.isSuccess}
            scrapeMetadataError={scrapeMetadata.isError}
            lockedFields={stringList(form.metadata.nfo_locked_fields)}
            manualValues={objectRecord(form.metadata.nfo_manual_values)}
            onFieldPolicyChange={(lockedFields, manualValues) => setForm((current) => ({
              ...current,
              metadata: { ...current.metadata, nfo_locked_fields: lockedFields, nfo_manual_values: manualValues },
            }))}
          />
        </Accordion>
        <Accordion icon={<ListNumbers size={21} />} title="季集映射" summary={mappingSummary(episodeMappingMode, form.season_number, form.episode_offset, localEpisodeNumber, localEpisodeOffset)} open={openSection === "season"} onToggle={() => setOpenSection("season")}>
          <div className="field-grid two-columns">
            <Field label="映射模式"><select value={episodeMappingMode} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_episode_mapping_mode: e.target.value } }))}><option value="auto">自动识别（原模式）</option><option value="manual">常规番剧手动映射</option><option value="single">单文件剧场版/特别篇</option></select></Field>
            <Field label="Emby 季号"><input type="number" min="0" value={form.season_number} onChange={(e) => setForm({ ...form, season_number: Number(e.target.value) })} /></Field>
            {provider === "tmdb" ? <Field label="TMDB 季号"><input type="number" min="0" value={providerSeasonNumber} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, tmdb_season_number: Number(e.target.value) } }))} /></Field> : null}
            {episodeMappingMode === "single" ? <>
              <Field label="Emby 集号"><input type="number" min="1" value={localEpisodeNumber} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_local_episode_number: Number(e.target.value) } }))} /></Field>
              <Field label={`${provider === "tmdb" ? "TMDB" : "Bangumi"} 元数据集号`}><input type="number" min="1" value={providerEpisodeNumber} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_provider_episode_number: Number(e.target.value) } }))} /></Field>
            </> : episodeMappingMode === "manual" ? <>
              <Field label="Emby 集数偏移"><input type="number" value={localEpisodeOffset} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_local_episode_offset: Number(e.target.value) } }))} /></Field>
              <Field label={`${provider === "tmdb" ? "TMDB" : "Bangumi"} 元数据偏移`}><input type="number" value={form.episode_offset} onChange={(e) => setForm({ ...form, episode_offset: Number(e.target.value) })} /></Field>
            </> : <Field label="集数偏移"><input type="number" value={form.episode_offset} onChange={(e) => setForm({ ...form, episode_offset: Number(e.target.value) })} /></Field>}
          </div>
          {episodeMappingMode === "single" ? <p className="notice">适用于目录中只有一个正片视频的剧场版或特别篇。Emby 通常把特别篇放在第 0 季；重新刮削会按这里的 S{pad(form.season_number)}E{pad(localEpisodeNumber)} 覆盖已有 NFO 的季集编号。</p> : null}
          {episodeMappingMode === "manual" ? <p className="notice">适用于需要修正季集编号的正常番剧。Emby 季号会直接写入 NFO；两个集数偏移分别调整 Emby 展示集号和元数据匹配集号。例如文件从 E13 开始但应显示为 E01，两项都填写 -12。</p> : null}
          {episodeMappingMode === "auto" ? <p className="notice">保留原有自动识别逻辑：从文件名识别集号，使用季号和集数偏移匹配远程元数据，不调整写入 NFO 的本地集号。</p> : null}
        </Accordion>
        <Accordion icon={<FileText size={21} />} title="NFO 文件" summary={nfoPreview.data ? `${nfoPreview.data.default_selected_count} 项待处理` : "媒体文件保持不变"} open={openSection === "nfo"} onToggle={() => setOpenSection("nfo")}>
          <p className="notice nfo-safety-notice">不会重命名、移动或覆盖视频；NFO 目标名始终跟随原视频文件名。</p>
          <NfoPreviewPanel
            preview={nfoPreview.data}
            loading={nfoPreview.isFetching}
            error={nfoPreview.isError}
            excludedPaths={stringList(form.metadata.nfo_excluded_paths)}
            includedPaths={stringList(form.metadata.nfo_included_paths)}
            onSelectionChange={(excludedPaths, includedPaths) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_excluded_paths: excludedPaths, nfo_included_paths: includedPaths } }))}
            onRefresh={() => void nfoPreview.refetch()}
          />
        </Accordion>
        <Accordion icon={<Cube size={21} />} title="Emby 刮削" summary={form.emby_enabled ? "已启用" : "已停用"} open={openSection === "emby"} onToggle={() => setOpenSection("emby")}>
          <div className="field-grid"><Field label="Emby 刮削"><button className="secondary-button" type="button" onClick={() => setForm({ ...form, emby_enabled: !form.emby_enabled })}>{form.emby_enabled ? "已启用，点击停用" : "已停用，点击启用"}</button></Field></div>
          <p className="notice">保存外部 ID 后，将用于后续生成最小 NFO 并触发 Emby 精准刷新。</p>
        </Accordion>
      </div>
      <footer className="drawer-footer"><span>{save.isSuccess ? "配置已保存" : save.isError ? "保存失败，请重试" : "更改仅写入应用配置"}</span><button className="secondary-button" type="button" onClick={() => setForm(binding.data ?? defaults)}>重置</button><button className="primary-button" type="button" onClick={() => save.mutate()} disabled={save.isPending}><FloppyDisk size={18} /> {save.isPending ? "保存中" : "保存配置"}</button></footer>
    </aside>
  </div>;
}

function Accordion({ icon, title, summary, open, onToggle, children }: { icon: ReactNode; title: string; summary: string; open: boolean; onToggle: () => void; children: ReactNode }) {
  return <section className={`accordion ${open ? "open" : ""}`}><button className="accordion-trigger" type="button" onClick={onToggle} aria-expanded={open}><span className="accordion-heading">{icon}<span><strong>{title}</strong><small>{summary}</small></span></span><CaretDown size={18} /></button>{open ? <div className="accordion-body">{children}</div> : null}</section>;
}
function Field({ label, wide = false, children }: { label: string; wide?: boolean; children: ReactNode }) { return <label className={wide ? "wide" : ""}><span>{label}</span>{children}</label>; }
function stringList(value: unknown) {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value as string[] : emptyPaths;
}
function objectRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function numberValue(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isInteger(value) ? value : fallback;
}
function pad(value: number) { return String(value).padStart(2, "0"); }
function signed(value: number) { return value > 0 ? `+${value}` : String(value); }
function mappingMode(value: unknown): "auto" | "manual" | "single" { return value === "manual" || value === "single" ? value : "auto"; }
function mappingSummary(mode: "auto" | "manual" | "single", season: number, providerOffset: number, localEpisode: number, localOffset: number) {
  if (mode === "single") return `特别篇 · S${pad(season)}E${pad(localEpisode)}`;
  if (mode === "manual") return `手动 · S${pad(season)} · Emby ${signed(localOffset)} · 元数据 ${signed(providerOffset)}`;
  return `自动 · 第 ${season} 季 · 偏移 ${providerOffset}`;
}
function scrapeSummary(info: LocalScrapeInfo | undefined) {
  if (!info) return "剧集 · 季度 · 单集";
  const episodes = info.seasons.reduce((total, season) => total + season.episodes.length, 0);
  return `${info.seasons.length} 季 · ${episodes} 集`;
}
