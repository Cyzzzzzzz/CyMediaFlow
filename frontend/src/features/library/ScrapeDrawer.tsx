import { CaretDown, CheckCircle, CrownSimple, Cube, FileText, FilmSlate, FloppyDisk, IdentificationBadge, ListNumbers, MagicWand, MagnifyingGlass, Plus, Trash, X } from "@phosphor-icons/react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { ApiError } from "../../api/client";
import { imageSource } from "../../api/images";
import type { EpisodeMappingSuggestion, EpisodeSourceRule, LocalScrapeInfo, MediaBinding, MediaItem, MetadataCandidate, ProviderSubjectBinding, ProviderSubjectRole } from "../../api/types";
import { libraryApi } from "./api";
import { NfoPreviewPanel } from "./NfoPreviewPanel";
import { ScrapeInfoPanel, type BangumiSeasonMetadataGroup } from "./ScrapeInfoPanel";

type Props = { item: MediaItem; onClose: () => void };
type Section = "match" | "scrape" | "season" | "nfo" | "emby";
type Provider = "bangumi" | "tmdb";
const defaults: MediaBinding = {
  bangumi_id: null, tmdb_id: null, preferred_title: null, content_kind: "series", year: null,
  season_number: 1, episode_offset: 0, folder_template: "{title} ({year})/Season {season:02}",
  filename_template: "{title} S{season:02}E{episode:02}", emby_enabled: true, image_url: null, metadata: {},
  provider_subjects: [], episode_source_rules: [],
};
const emptyPaths: string[] = [];

export function ScrapeDrawer({ item, onClose }: Props) {
  const client = useQueryClient();
  const nfoBangumiId = item.external_ids.find((identity) => identity.provider === "bangumi")?.external_id ?? null;
  const nfoTmdbId = item.external_ids.find((identity) => identity.provider === "tmdb")?.external_id ?? null;
  const initialProvider = primaryProvider(item.binding ?? defaults);
  const initialPrimary = primarySubject(item.binding ?? defaults);
  const [openSection, setOpenSection] = useState<Section>("match");
  const [provider, setProvider] = useState<Provider>(initialProvider);
  const [query, setQuery] = useState(item.title);
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [candidateLimit, setCandidateLimit] = useState(10);
  const [directId, setDirectId] = useState("");
  const [artworkRevision, setArtworkRevision] = useState(0);
  const [form, setForm] = useState<MediaBinding>(item.binding ?? defaults);
  const [detailId, setDetailId] = useState<string | null>(initialPrimary?.external_id ?? (initialProvider === "tmdb" ? nfoTmdbId : nfoBangumiId));
  const effectiveExternalId = detailId ?? (provider === "tmdb" ? (form.tmdb_id || nfoTmdbId) : (form.bangumi_id || nfoBangumiId));
  const nfoSubject = primarySubject(form);
  const nfoProvider = nfoSubject?.provider ?? primaryProvider(form);
  const nfoExternalId = nfoSubject?.external_id ?? (nfoProvider === "tmdb" ? (form.tmdb_id || nfoTmdbId) : (form.bangumi_id || nfoBangumiId));
  const providerSeasonNumber = provider === "tmdb" ? numberValue(form.metadata.tmdb_season_number, form.season_number) : form.season_number;
  const episodeMappingMode = mappingMode(form.metadata.nfo_episode_mapping_mode);
  const localEpisodeNumber = numberValue(form.metadata.nfo_local_episode_number, 1);
  const providerEpisodeNumber = numberValue(form.metadata.nfo_provider_episode_number, 1);
  const localEpisodeOffset = numberValue(form.metadata.nfo_local_episode_offset, 0);
  const metadataDetailKey = ["metadata-detail", item.id, provider, detailId] as const;
  const metadataEpisodesKey = ["metadata-episodes", item.id, provider, effectiveExternalId, providerSeasonNumber] as const;
  const scrapeInfoKey = ["scrape-info", item.id] as const;
  const nfoPreviewKey = ["nfo-preview", item.id, form.season_number, form.episode_offset, episodeMappingMode, localEpisodeNumber, providerEpisodeNumber, localEpisodeOffset, nfoExternalId, form.episode_source_rules] as const;
  const binding = useQuery({ queryKey: ["binding", item.id], queryFn: () => libraryApi.binding(item.id) });
  const cachedCandidateSearch = useQuery({
    queryKey: ["candidate-cache", item.id, provider],
    queryFn: () => libraryApi.cachedCandidates(item.id, provider),
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const candidates = useQuery({
    queryKey: ["candidates", item.id, submittedQuery, provider, candidateLimit],
    queryFn: () => libraryApi.candidates(item.id, submittedQuery, provider, candidateLimit, true),
    enabled: !!submittedQuery.trim(),
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const cachedSearch = cachedCandidateSearch.data;
  const visibleCandidates = submittedQuery ? candidates.data : cachedSearch?.candidates;
  const visibleCandidateLimit = submittedQuery ? candidateLimit : (cachedSearch?.limit ?? 0);
  const showingCachedSearch = !submittedQuery && !!cachedSearch;
  const metadataDetail = useQuery({
    queryKey: metadataDetailKey,
    queryFn: () => libraryApi.metadataDetail(item.id, detailId!, provider, false),
    enabled: openSection === "scrape" && !!detailId,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const metadataEpisodes = useQuery({
    queryKey: metadataEpisodesKey,
    queryFn: () => libraryApi.metadataEpisodes(item.id, effectiveExternalId!, provider, providerSeasonNumber, false),
    enabled: openSection === "scrape" && !!effectiveExternalId,
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const bangumiSeasonReferences = seasonalBangumiReferences(form);
  const bangumiSeasonDetailQueries = useQueries({
    queries: bangumiSeasonReferences.map((reference) => ({
      queryKey: ["metadata-detail", item.id, "bangumi", reference.externalId],
      queryFn: () => libraryApi.metadataDetail(item.id, reference.externalId, "bangumi", false),
      enabled: openSection === "scrape",
      retry: false,
      staleTime: Infinity,
      gcTime: Infinity,
    })),
  });
  const bangumiSeasonGroups = buildBangumiSeasonGroups(
    bangumiSeasonReferences,
    bangumiSeasonDetailQueries.map((queryResult) => ({
      data: queryResult.data,
      loading: queryResult.isFetching,
      error: queryResult.isError,
    })),
  );
  const scrapeInfo = useQuery({
    queryKey: scrapeInfoKey,
    queryFn: () => libraryApi.scrapeInfo(item.id, false),
    enabled: openSection === "scrape",
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const nfoPreview = useQuery({
    queryKey: nfoPreviewKey,
    queryFn: () => libraryApi.nfoPreview(item.id, form, false),
    enabled: openSection === "nfo",
    retry: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const save = useMutation({
    mutationFn: () => libraryApi.saveBinding(item.id, form),
    onSuccess: (savedBinding) => {
      setForm(savedBinding);
      void client.invalidateQueries({ queryKey: ["library"] });
      void client.invalidateQueries({ queryKey: ["binding", item.id] });
    },
  });
  const generateNfo = useMutation({
    mutationFn: async () => {
      const savedBinding = await libraryApi.saveBinding(item.id, form);
      setForm(savedBinding);
      const savedSubject = primarySubject(savedBinding);
      const savedProvider = savedSubject?.provider ?? primaryProvider(savedBinding);
      const savedExternalId = savedSubject?.external_id ?? (
        savedProvider === "tmdb" ? (savedBinding.tmdb_id || nfoTmdbId) : (savedBinding.bangumi_id || nfoBangumiId)
      );
      return libraryApi.generateNfo(item.id, savedBinding, savedProvider, savedExternalId);
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["scrape-info", item.id] });
      void client.invalidateQueries({ queryKey: ["nfo-preview", item.id] });
      void client.invalidateQueries({ queryKey: ["library"] });
    },
  });
  const scrapeMetadata = useMutation({
    mutationFn: async () => {
      const activeProvider = provider;
      const activeExternalId = effectiveExternalId!;
      const activeSeason = providerSeasonNumber;
      const otherBangumiReferences = bangumiSeasonReferences.filter(
        (reference) => activeProvider !== "bangumi" || reference.externalId !== activeExternalId,
      );
      const [detail, episodes, localInfo, otherBangumiDetails] = await Promise.all([
        libraryApi.metadataDetail(item.id, activeExternalId, activeProvider, true),
        libraryApi.metadataEpisodes(item.id, activeExternalId, activeProvider, activeSeason, true),
        libraryApi.scrapeInfo(item.id, true),
        Promise.all(otherBangumiReferences.map(async (reference) => ({
          reference,
          detail: await libraryApi.metadataDetail(item.id, reference.externalId, "bangumi", true),
        }))),
      ]);
      return { activeProvider, activeExternalId, activeSeason, detail, episodes, localInfo, otherBangumiDetails };
    },
    onSuccess: ({ activeProvider, activeExternalId, activeSeason, detail, episodes, localInfo, otherBangumiDetails }) => {
      setDetailId(detail.external_id);
      client.setQueryData(["metadata-detail", item.id, activeProvider, activeExternalId], detail);
      client.setQueryData(["metadata-episodes", item.id, activeProvider, activeExternalId, activeSeason], episodes);
      client.setQueryData(scrapeInfoKey, localInfo);
      otherBangumiDetails.forEach(({ reference, detail: seasonDetail }) => {
        client.setQueryData(["metadata-detail", item.id, "bangumi", reference.externalId], seasonDetail);
      });
      setForm((current) => isSubject(primarySubject(current), activeProvider, detail.external_id) ? ({
          ...current,
          preferred_title: current.preferred_title || detail.title,
          year: current.year || detail.year,
          image_url: detail.image_url || current.image_url,
          metadata: {
            ...current.metadata,
            [`${activeProvider}_candidate_title`]: detail.title,
            [`${activeProvider}_original_title`]: detail.original_title,
            [`${activeProvider}_episode_count`]: detail.episode_count,
            [`${activeProvider}_summary`]: detail.summary,
          },
        }) : current);
    },
  });
  const extractSeasonArtwork = useMutation({
    mutationFn: (seasonNumber: number) => libraryApi.extractSeasonArtwork(
      item.id, seasonNumber,
    ),
    onSuccess: () => {
      setArtworkRevision(Date.now());
      void client.invalidateQueries({ queryKey: scrapeInfoKey });
    },
  });
  const addById = useMutation({
    mutationFn: () => libraryApi.metadataDetail(item.id, directId.trim(), provider, true),
    onSuccess: (detail) => {
      addCandidate(detail);
      setDirectId("");
    },
  });
  const mappingSuggestion = useMutation({
    mutationFn: () => libraryApi.suggestEpisodeMapping(
      item.id,
      form.provider_subjects,
      item.seasons[0] ?? form.season_number,
    ),
    onSuccess: (suggestion) => setForm((current) => ({
      ...current,
      episode_source_rules: suggestion.rules,
    })),
  });
  const refreshNfoPreview = useMutation({
    mutationFn: () => libraryApi.nfoPreview(item.id, form, true),
    onSuccess: (preview) => client.setQueryData(nfoPreviewKey, preview),
  });

  useEffect(() => {
    if (!binding.data) return;
    setForm(binding.data);
    const savedProvider = primaryProvider(binding.data);
    const savedPrimary = primarySubject(binding.data);
    setProvider(savedProvider);
    setDetailId(savedPrimary?.external_id ?? (savedProvider === "tmdb" ? nfoTmdbId : nfoBangumiId));
  }, [binding.data, nfoBangumiId, nfoTmdbId]);
  useEffect(() => {
    const cached = cachedCandidateSearch.data;
    if (!cached?.query.trim()) return;
    setQuery(cached.query);
    setCandidateLimit(cached.limit);
  }, [cachedCandidateSearch.data]);
  useEffect(() => {
    if (!submittedQuery || !candidates.data || candidates.isFetching) return;
    client.setQueryData(
      ["candidate-cache", item.id, provider],
      { query: submittedQuery, limit: candidateLimit, candidates: candidates.data },
    );
  }, [candidateLimit, candidates.data, candidates.isFetching, client, item.id, provider, submittedQuery]);
  useEffect(() => {
    const detail = metadataDetail.data;
    if (!detail) return;
    setForm((current) => !isSubject(primarySubject(current), provider, detail.external_id) ? current : ({
      ...current,
      preferred_title: current.preferred_title || detail.title,
      year: current.year || detail.year,
      image_url: detail.image_url || current.image_url,
      metadata: {
        ...current.metadata,
        [`${provider}_candidate_title`]: detail.title,
        [`${provider}_original_title`]: detail.original_title,
        [`${provider}_episode_count`]: detail.episode_count,
        [`${provider}_summary`]: detail.summary,
      },
    }));
  }, [metadataDetail.data, provider]);
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const addCandidate = (candidate: MetadataCandidate) => {
    setDetailId(candidate.external_id);
    setForm((current) => {
      const key = subjectKey(candidate.provider, candidate.external_id);
      if (current.provider_subjects.some((subject) => subjectKey(subject.provider, subject.external_id) === key)) return current;
      const hasPrimary = !!current.bangumi_id || !!current.tmdb_id || current.provider_subjects.some((value) => value.role === "primary");
      const subject: ProviderSubjectBinding = {
        provider: candidate.provider,
        external_id: candidate.external_id,
        title: candidate.title,
        original_title: candidate.original_title,
        image_url: candidate.image_url,
        role: hasPrimary ? "season_part" : "primary",
      };
      const next = { ...current, provider_subjects: [...current.provider_subjects, subject] };
      return hasPrimary ? next : makePrimary(next, subject, candidate);
    });
  };

  const setPrimarySubject = (subject: ProviderSubjectBinding) => {
    generateNfo.reset();
    setProvider(subject.provider);
    setDetailId(subject.external_id);
    setForm((current) => makePrimary(current, subject));
  };

  const removeSubject = (subject: ProviderSubjectBinding) => {
    setForm((current) => {
      const idField = subject.provider === "tmdb" ? "tmdb_id" : "bangumi_id";
      const isPrimary = isPrimarySubject(current, subject);
      const remainingSubjects = current.provider_subjects.filter((value) => subjectKey(value.provider, value.external_id) !== subjectKey(subject.provider, subject.external_id));
      const metadata = { ...current.metadata };
      if (isPrimary) delete metadata.primary_provider;
      const next: MediaBinding = {
        ...current,
        [idField]: current[idField] === subject.external_id ? null : current[idField],
        metadata,
        provider_subjects: remainingSubjects,
        episode_source_rules: current.episode_source_rules.filter((rule) => subjectKey(rule.provider, rule.external_id) !== subjectKey(subject.provider, subject.external_id)),
      };
      return isPrimary && remainingSubjects[0] ? makePrimary(next, remainingSubjects[0]) : next;
    });
  };

  const updateSubjectRole = (subject: ProviderSubjectBinding, role: ProviderSubjectRole) => {
    if (role === "primary") {
      setPrimarySubject(subject);
      return;
    }
    setForm((current) => {
      if (isPrimarySubject(current, subject)) return current;
      return { ...current, provider_subjects: current.provider_subjects.map((value) => subjectKey(value.provider, value.external_id) === subjectKey(subject.provider, subject.external_id) ? { ...value, role } : value) };
    });
  };

  const changeProvider = (next: Provider) => {
    scrapeMetadata.reset();
    setSubmittedQuery("");
    setCandidateLimit(10);
    setQuery(item.title);
    setProvider(next);
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
        <Accordion icon={<IdentificationBadge size={21} />} title="作品匹配" summary={workMatchSummary(form)} open={openSection === "match"} onToggle={() => setOpenSection("match")}>
          <div className="work-primary">
            <span>主作品</span>
            {form.provider_subjects.length ? <select className="primary-subject-select" aria-label="选择主作品" value={primarySubject(form) ? subjectKey(primarySubject(form)!.provider, primarySubject(form)!.external_id) : ""} onChange={(event) => {
              const subject = form.provider_subjects.find((value) => subjectKey(value.provider, value.external_id) === event.target.value);
              if (subject) setPrimarySubject(subject);
            }}>
              {form.provider_subjects.map((subject) => <option key={subjectKey(subject.provider, subject.external_id)} value={subjectKey(subject.provider, subject.external_id)}>[{providerLabel(subject.provider)}] {subject.title}</option>)}
            </select> : <strong>尚未设置主作品</strong>}
            <small>{primarySubject(form) ? `${primarySubject(form)!.provider.toUpperCase()} #${primarySubject(form)!.external_id}` : "主作品控制系列标题、海报与 tvshow.nfo"}</small>
          </div>
          {form.provider_subjects.length ? <div className="work-subject-list">
            {form.provider_subjects.map((subject) => {
              const primary = isPrimarySubject(form, subject);
              return <div className={`work-subject ${primary ? "primary" : ""}`} key={subjectKey(subject.provider, subject.external_id)}>
                <div className="work-subject-cover">{imageSource(subject.image_url) ? <img src={imageSource(subject.image_url)!} alt="" /> : null}</div>
                <div className="work-subject-main"><strong>{subject.title}</strong><small>{subject.provider.toUpperCase()} #{subject.external_id}</small></div>
                <select aria-label={`${subject.title} 的用途`} value={primary ? "primary" : subject.role} onChange={(event) => updateSubjectRole(subject, event.target.value as ProviderSubjectRole)}>
                  {subjectRoleOptions.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
                </select>
                <div className="work-subject-actions">
                  <button type="button" className={primary ? "active" : ""} onClick={() => setPrimarySubject(subject)} title="设为主作品" aria-label={`将 ${subject.title} 设为主作品`}><CrownSimple size={16} weight={primary ? "fill" : "regular"} /></button>
                  <button type="button" onClick={() => removeSubject(subject)} title="移除关联" aria-label={`移除 ${subject.title}`}><Trash size={16} /></button>
                </div>
              </div>;
            })}
          </div> : null}
          {provider === "bangumi" && metadataDetail.data?.related_subjects?.some((subject) => !hasSubject(form, "bangumi", subject.external_id)) ? <details className="related-suggestions">
            <summary>从 Bangumi 关联条目添加</summary>
            <div>{metadataDetail.data.related_subjects.filter((subject) => subject.subject_type === 2 && !hasSubject(form, "bangumi", subject.external_id)).map((subject) => <button type="button" key={subject.external_id} onClick={() => addCandidate({ provider: "bangumi", external_id: subject.external_id, title: subject.title || subject.name, original_title: subject.name, year: null, episode_count: null, image_url: subject.image_url, summary: null })}><Plus size={15} /><span><strong>{subject.title || subject.name}</strong><small>{subject.relation} · #{subject.external_id}</small></span></button>)}</div>
          </details> : null}
          <div className="provider-tabs" role="tablist" aria-label="元数据来源">
            <button type="button" className={provider === "bangumi" ? "active" : ""} onClick={() => changeProvider("bangumi")}>Bangumi</button>
            <button type="button" className={provider === "tmdb" ? "active" : ""} onClick={() => changeProvider("tmdb")}>TMDB</button>
          </div>
          <span className="field-caption">搜索{provider === "tmdb" ? " TMDB" : "番剧"}</span>
          <form className="candidate-search" onSubmit={(event) => { event.preventDefault(); const nextQuery = query.trim(); if (nextQuery === submittedQuery && candidateLimit === 10) void candidates.refetch(); else { setCandidateLimit(10); setSubmittedQuery(nextQuery); } }}>
            <MagnifyingGlass size={19} /><input value={query} onChange={(event) => setQuery(event.target.value)} aria-label={`搜索 ${provider}`} /><button type="submit">搜索</button>
          </form>
          <div className="candidate-list">
            {!submittedQuery && cachedCandidateSearch.isLoading ? <p className="subtle">正在读取上一次搜索结果…</p> : null}
            {showingCachedSearch ? <p className="subtle">上一次搜索“{cachedSearch.query}” · 已缓存 {cachedSearch.candidates.length} 个结果；点击“搜索”才重新联网。</p> : null}
            {!submittedQuery && !cachedCandidateSearch.isLoading && !cachedSearch ? <p className="subtle">尚无搜索缓存；输入关键词后点击“搜索”。</p> : null}
            {candidates.isLoading ? <p className="subtle">正在搜索 {provider === "tmdb" ? "TMDB" : "Bangumi"}…</p> : null}
            {candidates.isError ? <p className="notice">搜索失败，请检查该来源的 Token 与网络配置。</p> : null}
            {visibleCandidates?.map((candidate) => <button key={`${candidate.provider}-${candidate.external_id}`} className={`candidate ${hasSubject(form, candidate.provider, candidate.external_id) ? "selected" : ""}`} type="button" onClick={() => addCandidate(candidate)}>
              {imageSource(candidate.image_url) ? <img src={imageSource(candidate.image_url)!} alt="" /> : <span />}
              <span><strong>{candidate.title}</strong><small>{candidate.original_title || candidate.title} · #{candidate.external_id}</small></span>
              {hasSubject(form, candidate.provider, candidate.external_id) ? <CheckCircle size={25} weight="fill" /> : <Plus size={22} />}
            </button>)}
          </div>
          {visibleCandidateLimit < 20 && (visibleCandidates?.length ?? 0) >= visibleCandidateLimit && visibleCandidateLimit > 0 ? <button className="candidate-more" type="button" onClick={() => {
            setCandidateLimit(20);
            if (!submittedQuery) setSubmittedQuery(cachedSearch?.query ?? query.trim());
          }}>加载更多结果</button> : null}
          <form className="direct-id-add" onSubmit={(event) => { event.preventDefault(); if (directId.trim()) addById.mutate(); }}>
            <input inputMode="numeric" value={directId} onChange={(event) => setDirectId(event.target.value)} placeholder={`输入 ${provider === "bangumi" ? "Bangumi Subject" : "TMDB"} ID`} aria-label="按 ID 添加作品" />
            <button type="submit" disabled={!directId.trim() || addById.isPending}>{addById.isPending ? "读取中" : "按 ID 添加"}</button>
          </form>
          {addById.isError ? <p className="notice">无法读取该 ID，请检查编号、Token 与网络配置。</p> : null}
          <div className="field-grid match-fields">
            <Field label="主 Bangumi ID"><input value={form.bangumi_id ?? ""} readOnly /></Field>
            <Field label="主 TMDB ID"><input value={form.tmdb_id ?? ""} readOnly /></Field>
            <Field label="首选标题"><input value={form.preferred_title ?? ""} onChange={(e) => setForm({ ...form, preferred_title: e.target.value || null })} /></Field>
          </div>
        </Accordion>
        <Accordion icon={<FileText size={21} />} title="NFO 文件" summary={nfoPreview.data ? `${nfoPreview.data.default_selected_count} 项待处理` : "媒体文件保持不变"} open={openSection === "nfo"} onToggle={() => setOpenSection("nfo")}>
          <p className="notice nfo-safety-notice">不会重命名、移动或覆盖视频；NFO 目标名始终跟随原视频文件名。</p>
          <NfoPreviewPanel
            preview={nfoPreview.data}
            loading={nfoPreview.isFetching || refreshNfoPreview.isPending}
            error={nfoPreview.isError}
            excludedPaths={stringList(form.metadata.nfo_excluded_paths)}
            excludedFolders={stringList(form.metadata.nfo_excluded_folders)}
            includedPaths={stringList(form.metadata.nfo_included_paths)}
            onSelectionChange={(excludedPaths, includedPaths, excludedFolders) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_excluded_paths: excludedPaths, nfo_included_paths: includedPaths, nfo_excluded_folders: excludedFolders } }))}
            onRefresh={() => refreshNfoPreview.mutate()}
          />
        </Accordion>
        <Accordion icon={<ListNumbers size={21} />} title="季集映射" summary={mappingSummary(episodeMappingMode, form.season_number, form.episode_offset, localEpisodeNumber, localEpisodeOffset)} open={openSection === "season"} onToggle={() => setOpenSection("season")}>
          <div className="field-grid two-columns">
            <Field label="映射模式"><select value={episodeMappingMode} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_episode_mapping_mode: e.target.value } }))}><option value="auto">自动识别（原模式）</option><option value="segments">多条目分段映射</option><option value="manual">单条目手动偏移</option><option value="single">单文件剧场版/特别篇</option></select></Field>
            {episodeMappingMode !== "segments" ? <Field label="Emby 季号"><input type="number" min="0" value={form.season_number} onChange={(e) => setForm({ ...form, season_number: Number(e.target.value) })} /></Field> : null}
            {episodeMappingMode !== "segments" && provider === "tmdb" ? <Field label="TMDB 季号"><input type="number" min="0" value={providerSeasonNumber} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, tmdb_season_number: Number(e.target.value) } }))} /></Field> : null}
            {episodeMappingMode === "single" ? <>
              <Field label="Emby 集号"><input type="number" min="1" value={localEpisodeNumber} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_local_episode_number: Number(e.target.value) } }))} /></Field>
              <Field label={`${provider === "tmdb" ? "TMDB" : "Bangumi"} 元数据集号`}><input type="number" min="1" value={providerEpisodeNumber} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_provider_episode_number: Number(e.target.value) } }))} /></Field>
            </> : episodeMappingMode === "manual" ? <>
              <Field label="Emby 集数偏移"><input type="number" value={localEpisodeOffset} onChange={(e) => setForm((current) => ({ ...current, metadata: { ...current.metadata, nfo_local_episode_offset: Number(e.target.value) } }))} /></Field>
              <Field label={`${provider === "tmdb" ? "TMDB" : "Bangumi"} 元数据偏移`}><input type="number" value={form.episode_offset} onChange={(e) => setForm({ ...form, episode_offset: Number(e.target.value) })} /></Field>
            </> : episodeMappingMode === "auto" ? <Field label="集数偏移"><input type="number" value={form.episode_offset} onChange={(e) => setForm({ ...form, episode_offset: Number(e.target.value) })} /></Field> : null}
          </div>
          {episodeMappingMode === "segments" ? <EpisodeSourceRulesEditor
            subjects={form.provider_subjects}
            rules={form.episode_source_rules}
            defaultSeason={item.seasons[0] ?? form.season_number}
            onChange={(rules) => setForm((current) => ({ ...current, episode_source_rules: rules }))}
            onSuggest={() => mappingSuggestion.mutate()}
            suggesting={mappingSuggestion.isPending}
            suggestion={mappingSuggestion.data}
            suggestionError={mappingSuggestion.isError}
          /> : null}
          {episodeMappingMode === "single" ? <p className="notice">适用于目录中只有一个正片视频的剧场版或特别篇。Emby 通常把特别篇放在第 0 季；重新刮削会按这里的 S{pad(form.season_number)}E{pad(localEpisodeNumber)} 覆盖已有 NFO 的季集编号。</p> : null}
          {episodeMappingMode === "manual" ? <p className="notice">适用于需要修正季集编号的正常番剧。Emby 季号会直接写入 NFO；两个集数偏移分别调整 Emby 展示集号和元数据匹配集号。例如文件从 E13 开始但应显示为 E01，两项都填写 -12。</p> : null}
          {episodeMappingMode === "auto" ? <p className="notice">保留原有自动识别逻辑：从文件名识别集号，使用季号和集数偏移匹配远程元数据，不调整写入 NFO 的本地集号。</p> : null}
          {episodeMappingMode === "segments" ? <p className="notice">分段规则本身已经包含 Emby 季号与本地集范围，因此不再使用顶层季号或集数偏移。规则允许第 0 集，但同一季度的范围不能重叠。</p> : null}
        </Accordion>
        <Accordion icon={<FilmSlate size={21} />} title="刮削信息" summary={scrapeSummary(scrapeInfo.data)} open={openSection === "scrape"} onToggle={() => setOpenSection("scrape")}>
          <ScrapeInfoPanel
            mediaId={item.id}
            localSeasonNumbers={item.seasons}
            provider={provider}
            generationProvider={nfoProvider}
            localInfo={scrapeInfo.data}
            providerInfo={metadataDetail.data}
            bangumiSeasonGroups={bangumiSeasonGroups}
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
            generationErrorMessage={apiErrorMessage(generateNfo.error)}
            generationResult={generateNfo.data}
            canGenerateNfo={!!nfoExternalId}
            canScrapeMetadata={!!effectiveExternalId}
            onScrapeMetadata={() => { generateNfo.reset(); scrapeMetadata.mutate(); }}
            scrapingMetadata={scrapeMetadata.isPending}
            scrapeMetadataSuccess={scrapeMetadata.isSuccess}
            scrapeMetadataError={scrapeMetadata.isError}
            lockedFields={stringList(form.metadata.nfo_locked_fields)}
            manualValues={objectRecord(form.metadata.nfo_manual_values)}
            onFieldPolicyChange={(lockedFields, manualValues) => setForm((current) => ({
              ...current,
              metadata: { ...current.metadata, nfo_locked_fields: lockedFields, nfo_manual_values: manualValues },
            }))}
            onExtractSeasonArtwork={(season) => extractSeasonArtwork.mutate(season)}
            extractingArtworkSeason={extractSeasonArtwork.isPending ? extractSeasonArtwork.variables : null}
            artworkExtractionResult={extractSeasonArtwork.data}
            artworkExtractionErrorSeason={extractSeasonArtwork.isError ? extractSeasonArtwork.variables : null}
            artworkRevision={artworkRevision}
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

const subjectRoleOptions: [ProviderSubjectRole, string][] = [
  ["primary", "主条目"], ["season", "季度"], ["season_part", "分割放送"],
  ["movie", "剧场版"], ["special", "特别篇/OVA"], ["related", "关联作品"],
  ["metadata_only", "仅补充元数据"],
];

function EpisodeSourceRulesEditor({ subjects, rules, defaultSeason, onChange, onSuggest, suggesting, suggestion, suggestionError }: { subjects: ProviderSubjectBinding[]; rules: EpisodeSourceRule[]; defaultSeason: number; onChange: (rules: EpisodeSourceRule[]) => void; onSuggest: () => void; suggesting: boolean; suggestion: EpisodeMappingSuggestion | undefined; suggestionError: boolean }) {
  const [selectedSubject, setSelectedSubject] = useState(subjects[0] ? subjectKey(subjects[0].provider, subjects[0].external_id) : "");
  const errors = sourceRuleErrors(rules);
  const addRule = () => {
    const subject = subjects.find((value) => subjectKey(value.provider, value.external_id) === selectedSubject) ?? subjects[0];
    if (!subject) return;
    onChange([...rules, {
      provider: subject.provider,
      external_id: subject.external_id,
      local_season: defaultSeason,
      local_episode_start: 1,
      local_episode_end: null,
      provider_episode_start: 1,
      provider_season: subject.provider === "tmdb" ? defaultSeason : 1,
      number_mode: subject.provider === "bangumi" ? "sort" : "episode",
    }]);
  };
  const updateRule = (index: number, patch: Partial<EpisodeSourceRule>) => onChange(rules.map((rule, ruleIndex) => ruleIndex === index ? { ...rule, ...patch } : rule));
  const suggestRules = () => {
    if (rules.length && !window.confirm("智能生成会替换当前尚未保存的分段规则，是否继续？")) return;
    onSuggest();
  };
  return <div className="source-rules-editor">
    <div className="source-rules-head"><div><strong>分段来源</strong><small>按本地季集范围选择远程作品</small></div><div><button className="suggest-rules-button" type="button" onClick={suggestRules} disabled={!subjects.length || suggesting}><MagicWand size={15} />{suggesting ? "识别中" : "智能生成"}</button><select value={selectedSubject} onChange={(event) => setSelectedSubject(event.target.value)} disabled={!subjects.length}>{subjects.map((subject) => <option key={subjectKey(subject.provider, subject.external_id)} value={subjectKey(subject.provider, subject.external_id)}>[{providerLabel(subject.provider)}] {subject.title}</option>)}</select><button type="button" onClick={addRule} disabled={!subjects.length}><Plus size={15} />添加规则</button></div></div>
    {!subjects.length ? <p className="notice">请先在“作品匹配”中添加需要使用的 Bangumi/TMDB 条目。</p> : null}
    {suggestion ? <div className="mapping-suggestion-result"><span>已识别 {suggestion.detected_ranges.map((range) => `S${pad(range.season_number)} E${pad(range.episode_start)}–E${pad(range.episode_end)}`).join("、")}，生成 {suggestion.rules.length} 条规则。</span>{suggestion.warnings.map((warning) => <small key={warning}>{warning}</small>)}</div> : null}
    {suggestionError ? <p className="notice source-rule-error">智能识别失败，请检查文件命名、来源配置与网络连接。</p> : null}
    {rules.length ? <div className="source-rule-list">{rules.map((rule, index) => {
      const subject = subjects.find((value) => subjectKey(value.provider, value.external_id) === subjectKey(rule.provider, rule.external_id));
      return <div className="source-rule" key={`${subjectKey(rule.provider, rule.external_id)}-${index}`}>
        <div className="source-rule-title"><span><span className={`provider-tag ${rule.provider}`}>{providerLabel(rule.provider)}</span><strong>{subject?.title ?? `${rule.provider.toUpperCase()} #${rule.external_id}`}</strong><small>#{rule.external_id}</small></span><button type="button" onClick={() => onChange(rules.filter((_, ruleIndex) => ruleIndex !== index))} aria-label="删除映射规则"><Trash size={16} /></button></div>
        <div className="source-rule-fields">
          <Field label="本地季（Emby）"><input type="number" min="0" max="99" value={rule.local_season} onChange={(event) => updateRule(index, { local_season: Number(event.target.value) })} /></Field>
          <Field label="本地起始集"><input type="number" min="0" value={rule.local_episode_start} onChange={(event) => updateRule(index, { local_episode_start: Number(event.target.value) })} /></Field>
          <Field label="本地结束集"><input type="number" min="0" placeholder="持续更新" value={rule.local_episode_end ?? ""} onChange={(event) => updateRule(index, { local_episode_end: event.target.value === "" ? null : Number(event.target.value) })} /></Field>
          <Field label="远程起始编号"><input type="number" min="0" value={rule.provider_episode_start} onChange={(event) => updateRule(index, { provider_episode_start: Number(event.target.value) })} /></Field>
          {rule.provider === "tmdb" ? <Field label="TMDB 远程季"><input type="number" min="0" max="99" value={rule.provider_season} onChange={(event) => updateRule(index, { provider_season: Number(event.target.value) })} /></Field> : null}
          {rule.provider === "bangumi" ? <Field label="Bangumi 编号字段"><select value={rule.number_mode} onChange={(event) => updateRule(index, { number_mode: event.target.value as "episode" | "sort" })}><option value="sort">sort（推荐分割放送）</option><option value="episode">ep / 集号</option></select></Field> : null}
        </div>
      </div>;
    })}</div> : null}
    {errors.map((error) => <p className="notice source-rule-error" key={error}>{error}</p>)}
    <details className="mapping-field-help"><summary>字段说明与自动识别规则</summary><dl><div><dt>来源</dt><dd>选择该分段从 Bangumi 或 TMDB 的哪个作品条目读取元数据。</dd></div><div><dt>本地季（Emby）</dt><dd>文件在本地被识别到的季度，也是写入 episode NFO 的 season 值。</dd></div><div><dt>本地起始/结束集</dt><dd>这条规则覆盖的本地文件集号范围；留空结束集表示后续集数也使用该来源。</dd></div><div><dt>远程起始编号</dt><dd>本地起始集对应的远程分集编号，之后按 1 递增映射。</dd></div><div><dt>TMDB 远程季</dt><dd>TMDB 把分集放在具体季下，因此必须保留；通常与本地季相同，但可手动修正。</dd></div><div><dt>Bangumi 编号字段</dt><dd>分割放送优先用连续的 sort；仅当条目按自身集号从 1 开始时改用 ep。</dd></div></dl><p>智能生成会从目录名/文件名识别本地季集范围，再读取各来源的远程分集数量和编号进行切段。结果只进入当前表单，保存前仍可修改。</p></details>
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
function mappingMode(value: unknown): "auto" | "manual" | "single" | "segments" { return value === "manual" || value === "single" || value === "segments" ? value : "auto"; }
function mappingSummary(mode: "auto" | "manual" | "single" | "segments", season: number, providerOffset: number, localEpisode: number, localOffset: number) {
  if (mode === "single") return `特别篇 · S${pad(season)}E${pad(localEpisode)}`;
  if (mode === "manual") return `手动 · S${pad(season)} · Emby ${signed(localOffset)} · 元数据 ${signed(providerOffset)}`;
  if (mode === "segments") return "多条目分段映射";
  return `自动 · 第 ${season} 季 · 偏移 ${providerOffset}`;
}
function subjectKey(provider: string, externalId: string) { return `${provider}:${externalId}`; }
function providerLabel(provider: string) { return provider === "tmdb" ? "TMDB" : "Bangumi"; }
function hasSubject(binding: MediaBinding, provider: string, externalId: string) { return binding.provider_subjects.some((subject) => subjectKey(subject.provider, subject.external_id) === subjectKey(provider, externalId)); }
function primarySubject(binding: MediaBinding) {
  const explicit = binding.provider_subjects.find((subject) => subject.role === "primary");
  if (explicit) return explicit;
  const configuredProvider = binding.metadata.primary_provider;
  if (configuredProvider === "bangumi" || configuredProvider === "tmdb") {
    const configuredId = configuredProvider === "tmdb" ? binding.tmdb_id : binding.bangumi_id;
    if (configuredId) {
      const configured = binding.provider_subjects.find((subject) => isSubject(subject, configuredProvider, configuredId));
      if (configured) return configured;
    }
  }
  const byBangumiId = binding.bangumi_id ? binding.provider_subjects.find((subject) => isSubject(subject, "bangumi", binding.bangumi_id!)) : undefined;
  if (byBangumiId) return byBangumiId;
  const byTmdbId = binding.tmdb_id ? binding.provider_subjects.find((subject) => isSubject(subject, "tmdb", binding.tmdb_id!)) : undefined;
  return byTmdbId ?? binding.provider_subjects[0];
}
function primaryProvider(binding: MediaBinding): Provider {
  const subject = primarySubject(binding);
  if (subject) return subject.provider;
  if (binding.metadata.primary_provider === "tmdb" && binding.tmdb_id) return "tmdb";
  if (binding.metadata.primary_provider === "bangumi" && binding.bangumi_id) return "bangumi";
  return binding.bangumi_id || !binding.tmdb_id ? "bangumi" : "tmdb";
}
function isSubject(subject: ProviderSubjectBinding | undefined, provider: string, externalId: string) { return !!subject && subjectKey(subject.provider, subject.external_id) === subjectKey(provider, externalId); }
function isPrimarySubject(binding: MediaBinding, subject: ProviderSubjectBinding) { return primarySubject(binding) ? subjectKey(primarySubject(binding)!.provider, primarySubject(binding)!.external_id) === subjectKey(subject.provider, subject.external_id) : false; }
function workMatchSummary(binding: MediaBinding) { const primary = primarySubject(binding); return primary ? `${primary.title} · ${binding.provider_subjects.length} 个条目` : "尚未匹配"; }
function makePrimary(binding: MediaBinding, subject: ProviderSubjectBinding, candidate?: MetadataCandidate): MediaBinding {
  const idField = subject.provider === "tmdb" ? "tmdb_id" : "bangumi_id";
  return {
    ...binding,
    [idField]: subject.external_id,
    preferred_title: candidate?.title ?? subject.title ?? binding.preferred_title,
    year: candidate?.year ?? binding.year,
    image_url: candidate?.image_url ?? subject.image_url ?? binding.image_url,
    provider_subjects: binding.provider_subjects.map((value) => ({ ...value, role: subjectKey(value.provider, value.external_id) === subjectKey(subject.provider, subject.external_id) ? "primary" : value.role === "primary" ? "season_part" : value.role })),
    metadata: {
      ...binding.metadata,
      primary_provider: subject.provider,
      [`${subject.provider}_episode_count`]: candidate?.episode_count ?? binding.metadata[`${subject.provider}_episode_count`],
      [`${subject.provider}_candidate_title`]: candidate?.title ?? subject.title,
      [`${subject.provider}_original_title`]: candidate?.original_title ?? subject.original_title,
      [`${subject.provider}_summary`]: candidate?.summary ?? binding.metadata[`${subject.provider}_summary`],
    },
  };
}
type BangumiSeasonReference = {
  seasonNumber: number;
  externalId: string;
  title: string;
  imageUrl: string | null;
  ranges: string[];
};
function seasonalBangumiReferences(binding: MediaBinding): BangumiSeasonReference[] {
  const subjects = new Map(
    binding.provider_subjects
      .filter((subject) => subject.provider === "bangumi")
      .map((subject) => [subject.external_id, subject]),
  );
  const references = new Map<string, BangumiSeasonReference>();
  for (const rule of binding.episode_source_rules.filter((value) => value.provider === "bangumi")) {
    const subject = subjects.get(rule.external_id);
    const key = `${rule.local_season}:${rule.external_id}`;
    const range = `E${pad(rule.local_episode_start)}–${rule.local_episode_end === null ? "持续更新" : `E${pad(rule.local_episode_end)}`}`;
    const existing = references.get(key);
    if (existing) {
      existing.ranges.push(range);
    } else {
      references.set(key, {
        seasonNumber: rule.local_season,
        externalId: rule.external_id,
        title: subject?.title ?? `Bangumi #${rule.external_id}`,
        imageUrl: subject?.image_url ?? null,
        ranges: [range],
      });
    }
  }
  if (!references.size) {
    const primary = primarySubject(binding);
    if (primary?.provider === "bangumi") {
      references.set(`${binding.season_number}:${primary.external_id}`, {
        seasonNumber: binding.season_number,
        externalId: primary.external_id,
        title: primary.title,
        imageUrl: primary.image_url,
        ranges: [],
      });
    }
  }
  return [...references.values()].sort((left, right) => left.seasonNumber - right.seasonNumber || left.externalId.localeCompare(right.externalId));
}
function buildBangumiSeasonGroups(
  references: BangumiSeasonReference[],
  results: { data: MetadataCandidate | undefined; loading: boolean; error: boolean }[],
): BangumiSeasonMetadataGroup[] {
  const groups = new Map<number, BangumiSeasonMetadataGroup>();
  references.forEach((reference, index) => {
    const group = groups.get(reference.seasonNumber) ?? { seasonNumber: reference.seasonNumber, subjects: [] };
    group.subjects.push({
      externalId: reference.externalId,
      title: reference.title,
      imageUrl: reference.imageUrl,
      ranges: reference.ranges,
      metadata: results[index]?.data,
      loading: results[index]?.loading ?? false,
      error: results[index]?.error ?? false,
    });
    groups.set(reference.seasonNumber, group);
  });
  return [...groups.values()].sort((left, right) => left.seasonNumber - right.seasonNumber);
}
function apiErrorMessage(error: unknown) {
  return error instanceof ApiError ? error.message : undefined;
}
function sourceRuleErrors(rules: EpisodeSourceRule[]) {
  const errors: string[] = [];
  rules.forEach((rule, index) => {
    if (rule.local_episode_end !== null && rule.local_episode_end < rule.local_episode_start) errors.push(`第 ${index + 1} 条规则的结束集不能小于起始集。`);
    rules.slice(index + 1).forEach((other, otherIndex) => {
      if (rule.local_season !== other.local_season) return;
      const ruleEnd = rule.local_episode_end ?? Number.MAX_SAFE_INTEGER;
      const otherEnd = other.local_episode_end ?? Number.MAX_SAFE_INTEGER;
      if (rule.local_episode_start <= otherEnd && other.local_episode_start <= ruleEnd) errors.push(`第 ${index + 1} 与第 ${index + otherIndex + 2} 条规则范围重叠。`);
    });
  });
  return errors;
}
function scrapeSummary(info: LocalScrapeInfo | undefined) {
  if (!info) return "剧集 · 季度 · 单集";
  const episodes = info.seasons.reduce((total, season) => total + season.episodes.length, 0);
  return `${info.seasons.length} 季 · ${episodes} 集`;
}
