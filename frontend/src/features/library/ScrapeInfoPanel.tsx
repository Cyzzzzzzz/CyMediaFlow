import { ArrowsClockwise, CalendarBlank, FilePlus, FilmSlate, Star } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { imageSource } from "../../api/images";
import type { EpisodeScrapeInfo, LocalScrapeInfo, MetadataCandidate, NfoGenerationResult, ProviderEpisode, SeasonScrapeInfo } from "../../api/types";
import { NfoFieldPolicyEditor } from "./NfoFieldPolicyEditor";

type Props = {
  mediaId?: string;
  provider?: "bangumi" | "tmdb";
  localInfo: LocalScrapeInfo | undefined;
  providerInfo: MetadataCandidate | undefined;
  providerEpisodes?: ProviderEpisode[];
  providerEpisodesLoading?: boolean;
  providerEpisodesError?: boolean;
  seasonNumber?: number;
  episodeOffset?: number;
  loading: boolean;
  error: boolean;
  onGenerate?: () => void;
  generating?: boolean;
  generationError?: boolean;
  generationResult?: NfoGenerationResult;
  canScrapeMetadata?: boolean;
  onScrapeMetadata?: () => void;
  scrapingMetadata?: boolean;
  scrapeMetadataSuccess?: boolean;
  scrapeMetadataError?: boolean;
  lockedFields?: string[];
  manualValues?: Record<string, unknown>;
  onFieldPolicyChange?: (lockedFields: string[], manualValues: Record<string, unknown>) => void;
};

export function ScrapeInfoPanel({ mediaId, provider, localInfo, providerInfo, providerEpisodes = [], providerEpisodesLoading = false, providerEpisodesError = false, seasonNumber = 1, episodeOffset = 0, loading, error, onGenerate, generating = false, generationError = false, generationResult, canScrapeMetadata = false, onScrapeMetadata, scrapingMetadata = false, scrapeMetadataSuccess = false, scrapeMetadataError = false, lockedFields = [], manualValues = {}, onFieldPolicyChange }: Props) {
  const [generationArmed, setGenerationArmed] = useState(false);
  const [expandedEpisode, setExpandedEpisode] = useState<string | null>(null);
  const localSeries = localInfo?.series;
  const title = localSeries?.title ?? providerInfo?.title;
  const originalTitle = localSeries?.original_title ?? providerInfo?.original_title;
  const plot = localSeries?.plot ?? providerInfo?.summary;
  const posterUrl = localSeries?.poster_url ?? providerInfo?.image_url ?? null;
  const episodeTotal = localInfo?.seasons.reduce((total, season) => total + season.episodes.length, 0) ?? 0;
  const hasExistingNfo = !!localSeries || episodeTotal > 0;
  const canGenerateNfo = canScrapeMetadata || !!providerInfo;
  const activeProvider = provider ?? providerInfo?.provider ?? generationResult?.provider ?? "bangumi";
  const providerName = activeProvider === "tmdb" ? "TMDB" : "Bangumi";
  const displaySeasons = mergeEpisodeMetadata(
    localInfo?.seasons ?? [], providerEpisodes, seasonNumber, episodeOffset, activeProvider,
  );

  useEffect(() => {
    if (generationResult) setGenerationArmed(false);
  }, [generationResult]);

  if (loading && !title) return <p className="preview-state">正在读取 NFO 与海报…</p>;
  if (error && !title) return <p className="preview-state error">刮削信息读取失败</p>;
  if (!title) return <p className="preview-state">尚未发现本地 NFO，也没有已绑定的 Provider 信息。</p>;

  return <div className="scrape-info-panel">
    <section className="metadata-scrape-action">
      <div><strong>{providerName} 元数据</strong><small>{canScrapeMetadata ? "即使已有本地 NFO，也可以重新拉取最新数据。" : `请先在作品匹配中绑定 ${providerName} 条目。`}</small></div>
      <button className="preview-refresh" type="button" onClick={onScrapeMetadata} disabled={!canScrapeMetadata || !onScrapeMetadata || scrapingMetadata}><ArrowsClockwise size={15} className={scrapingMetadata ? "spin" : ""} />{scrapingMetadata ? "刮削中…" : "刮削元数据"}</button>
      {scrapeMetadataSuccess ? <span className="metadata-scrape-status success">已重新获取 {providerName} 元数据</span> : null}
      {scrapeMetadataError ? <span className="metadata-scrape-status error">刮削失败，请检查 {providerName} 连接</span> : null}
    </section>
    <section className="scrape-series-card">
      <Artwork className="series-artwork" url={posterUrl} alt={`${title} 剧集海报`} />
      <div className="scrape-series-main">
        <div className="scrape-level"><span>剧集</span><small>{localSeries ? "本地 tvshow.nfo" : `${providerInfo?.provider === "tmdb" ? "TMDB" : "Bangumi"} #${providerInfo?.external_id}`}</small></div>
        <h3>{title}</h3>
        {originalTitle && originalTitle !== title ? <p className="scrape-original">{originalTitle}</p> : null}
        <div className="scrape-facts">
          {(localSeries?.year ?? providerInfo?.year) ? <span><CalendarBlank size={13} />{localSeries?.year ?? providerInfo?.year}</span> : null}
          {localSeries?.rating !== null && localSeries?.rating !== undefined ? <span><Star size={13} weight="fill" />{localSeries.rating}</span> : null}
          {(localSeries?.runtime ?? null) ? <span>{localSeries?.runtime} 分钟</span> : null}
          {localInfo?.seasons.length ? <span>{localInfo.seasons.length} 季</span> : null}
          {episodeTotal ? <span>{episodeTotal} 集</span> : providerInfo?.episode_count ? <span>{providerInfo.episode_count} 集</span> : null}
        </div>
        {plot ? <p className="scrape-plot">{plot}</p> : null}
      </div>
    </section>

    {localSeries ? <div className="scrape-details">
      <InfoLine label="类型" values={localSeries.genres} />
      <InfoLine label="制作" values={localSeries.studios} />
      <InfoLine label="导演" values={localSeries.directors} />
      <InfoLine label="编剧" values={localSeries.writers} />
      <InfoLine label="声优" values={localSeries.cast.slice(0, 6)} />
      <InfoLine label="标签" values={localSeries.tags.slice(0, 8)} />
      <InfoLine label="外部 ID" values={localSeries.external_ids.map((identity) => `${identity.provider} #${identity.external_id}`)} />
    </div> : null}

    {activeProvider === "bangumi" ? <BangumiMetadataDetails mediaId={mediaId ?? localInfo?.media_id} metadata={providerInfo} loading={loading} /> : null}

    <NfoFieldPolicyEditor localInfo={localInfo} provider={providerInfo} providerName={providerName} lockedFields={lockedFields} manualValues={manualValues} onChange={onFieldPolicyChange ?? (() => undefined)} />

    {generationResult ? <GenerationDiagnostics result={generationResult} /> : null}
    <section className="nfo-generation-card">
      <div><span className="scrape-level-label">{providerName} 自动补全</span><strong>{hasExistingNfo ? "更新现有 NFO" : "生成本地 NFO"}</strong><small>{hasExistingNfo ? "更新未锁字段；缺少远程分集图时使用本地视频截图。" : "创建同名分集 NFO；缺少远程分集图时使用本地视频截图。"}</small></div>
      {!canGenerateNfo ? <p>请先在“作品匹配”中绑定 {providerName} 条目。</p> : generationArmed ? <div className="nfo-generation-confirm"><span>{hasExistingNfo ? "确认覆盖未锁定的 NFO 字段？" : "确认写入 NFO？"}</span><button type="button" onClick={() => setGenerationArmed(false)} disabled={generating}>取消</button><button type="button" className="primary-button" onClick={onGenerate} disabled={generating}>{generating ? "处理中…" : hasExistingNfo ? "确认更新" : "确认生成"}</button></div> : <button className="preview-refresh" type="button" onClick={() => setGenerationArmed(true)} disabled={!onGenerate}><FilePlus size={15} />{hasExistingNfo ? "更新 NFO" : "生成 NFO"}</button>}
      {generationError ? <p className="nfo-generation-error">生成失败，请检查 {providerName} 连接与媒体目录写入权限。</p> : null}
    </section>

    {displaySeasons.length ? <div className="scrape-season-list">
      {displaySeasons.map((season) => {
        const selected = season.episodes.find((episode) => episode.key === expandedEpisode);
        return <section className="scrape-season-card" key={season.season_number}>
        <div className="season-summary">
          <Artwork className="season-artwork" url={season.poster_url ?? posterUrl} alt={`第 ${season.season_number} 季海报`} />
          <div><span className="scrape-level-label">季度</span><h4>第 {season.season_number} 季</h4><p>{season.episodes.length} 集{season.year ? ` · ${season.year}` : ""}</p><small>{season.remoteOnly ? `${providerName} 分集数据` : posterSourceText(season.poster_source, !!posterUrl)}</small></div>
        </div>
        {season.plot ? <p className="season-plot">{season.plot}</p> : null}
        {season.episodes.length ? <div className="episode-strip" aria-label={`第 ${season.season_number} 季剧集`}>
          {season.episodes.map((episode) => <button className={`episode-card ${expandedEpisode === episode.key ? "expanded" : ""}`} key={episode.key} type="button" aria-expanded={expandedEpisode === episode.key} onClick={() => setExpandedEpisode((current) => current === episode.key ? null : episode.key)} title={episode.plot ?? undefined}>
            <Artwork className="episode-artwork" url={episode.poster_url} alt={`第 ${episode.episode_number} 集海报`} />
            <div><span>S{pad(episode.season_number)}E{pad(episode.episode_number)}</span><strong>{episode.title}</strong><small>{episode.aired || (episode.runtime ? `${episode.runtime} 分钟` : "本地 NFO")}</small></div>
          </button>)}
        </div> : <p className="subtle">该季度尚未发现分集 NFO。</p>}
        {selected ? <EpisodeMetadataDetail episode={selected} providerName={providerName} /> : null}
      </section>})}
      {providerEpisodesLoading ? <p className="subtle">正在读取 {providerName} 分集数据与剧照…</p> : null}
      {providerEpisodesError ? <p className="notice">{providerName} 分集数据读取失败；仍显示可用的本地 NFO 和图片。</p> : null}
    </div> : null}
  </div>;
}

function BangumiMetadataDetails({ mediaId, metadata, loading }: { mediaId: string | undefined; metadata: MetadataCandidate | undefined; loading: boolean }) {
  const infobox = metadata?.infobox ?? [];
  const persons = metadata?.persons ?? [];
  const characters = metadata?.characters ?? [];
  const related = metadata?.related_subjects ?? [];
  const tags = metadata?.tags ?? [];
  const hasCompleteData = !!(infobox.length || persons.length || characters.length || related.length);

  return <details className="bangumi-metadata-fold">
    <summary>
      <span>Bangumi 完整条目信息</span>
      <small>{hasCompleteData ? `${infobox.length} 项资料 · ${persons.length} 条制作记录 · ${characters.length} 个角色 · ${related.length} 个关联条目` : loading ? "正在读取完整信息…" : "尚未加载完整信息"}</small>
    </summary>
    <div className="bangumi-metadata-body">
      {!hasCompleteData ? <p className="bangumi-metadata-empty">{loading ? "正在从 Bangumi 读取条目、制作人员、角色和关联条目。" : "点击上方“刮削元数据”重新获取完整 Bangumi 信息。"}</p> : null}
      {hasCompleteData ? <>
      <details className="bangumi-metadata-section">
        <summary>条目资料 <small>{infobox.length} 项</small></summary>
        <div className="bangumi-infobox-list">
          {metadata?.rating ? <div><dt>评分</dt><dd>{metadata.rating.score ?? "—"} / 10 · 排名 #{metadata.rating.rank ?? "—"} · {metadata.rating.total} 人评分</dd></div> : null}
          {metadata?.premiere_date ? <div><dt>首播</dt><dd>{metadata.premiere_date}</dd></div> : null}
          {metadata?.platform ? <div><dt>平台</dt><dd>{metadata.platform}</dd></div> : null}
          {infobox.map((item) => <div key={item.key}><dt>{item.key}</dt><dd>{item.values.map((value) => value.label ? `${value.label}: ${value.value}` : value.value).join("、")}</dd></div>)}
          {(metadata?.meta_tags?.length || tags.length) ? <div><dt>标签</dt><dd>{[...(metadata?.meta_tags ?? []), ...tags.map((tag) => `${tag.name}${tag.count ? ` (${tag.count})` : ""}`)].join("、")}</dd></div> : null}
        </div>
      </details>

      <details className="bangumi-metadata-section">
        <summary>制作人员 <small>{persons.length} 条</small></summary>
        <div className="bangumi-person-grid">
          {persons.map((person, index) => <article className="bangumi-person" key={`${person.external_id}-${person.relation}-${index}`}>
            <MetadataPortrait mediaId={mediaId} category="persons" externalId={person.external_id} remoteUrl={person.image_url} alt={person.name} />
            <div><strong>{person.name}</strong><span>{person.relation || "制作人员"}</span>{person.career.length ? <small>{person.career.join(" · ")}</small> : null}{person.episode_scope ? <small>参与：{person.episode_scope}</small> : null}<a href={`https://bangumi.tv/person/${person.external_id}`} target="_blank" rel="noreferrer">Bangumi #{person.external_id}</a></div>
          </article>)}
        </div>
      </details>

      <details className="bangumi-metadata-section">
        <summary>角色与声优 <small>{characters.length} 个角色</small></summary>
        <div className="bangumi-character-list">
          {characters.map((character) => <article className="bangumi-character" key={character.external_id}>
            <MetadataPortrait mediaId={mediaId} category="characters" externalId={character.external_id} remoteUrl={character.image_url} alt={character.name} />
            <div className="bangumi-character-main">
              <div className="bangumi-character-title"><strong>{character.name}</strong><span>{character.relation}</span><a href={`https://bangumi.tv/character/${character.external_id}`} target="_blank" rel="noreferrer">#{character.external_id}</a></div>
              {character.summary ? <p>{character.summary}</p> : null}
              <div className="bangumi-character-facts">
                {character.gender ? <small>性别：{character.gender}</small> : null}
                {character.blood_type ? <small>血型：{character.blood_type}</small> : null}
                {character.birth_month && character.birth_day ? <small>生日：{character.birth_year ? `${character.birth_year}年` : ""}{character.birth_month}月{character.birth_day}日</small> : null}
                {character.infobox.map((item) => <small key={item.key}>{item.key}：{item.values.map((value) => value.value).join("、")}</small>)}
              </div>
              {character.actors.length ? <div className="bangumi-voice-list">{character.actors.map((actor) => <div key={actor.external_id}><MetadataPortrait mediaId={mediaId} category="voice-actors" externalId={actor.external_id} remoteUrl={actor.image_url} alt={actor.name} /><span><strong>{actor.name}</strong><small>{[actor.relation, ...actor.career, actor.episode_scope].filter(Boolean).join(" · ") || "声优"}</small></span></div>)}</div> : null}
            </div>
          </article>)}
        </div>
      </details>

      <details className="bangumi-metadata-section">
        <summary>关联条目 <small>{related.length} 个</small></summary>
        <div className="bangumi-related-grid">
          {related.map((item) => <a href={`https://bangumi.tv/subject/${item.external_id}`} target="_blank" rel="noreferrer" key={`${item.external_id}-${item.relation}`}>
            <MetadataPortrait mediaId={mediaId} category="related" externalId={item.external_id} remoteUrl={item.image_url} alt={item.title || item.name} />
            <span><small>{item.relation}</small><strong>{item.title || item.name}</strong>{item.title && item.title !== item.name ? <em>{item.name}</em> : null}</span>
          </a>)}
        </div>
      </details>
      </> : null}
    </div>
  </details>;
}

function MetadataPortrait({ mediaId, category, externalId, remoteUrl, alt }: { mediaId: string | undefined; category: "persons" | "characters" | "voice-actors" | "related"; externalId: string; remoteUrl: string | null; alt: string }) {
  const source = mediaId
    ? providerArtworkSource(mediaId, category, externalId, remoteUrl)
    : imageSource(remoteUrl);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [source]);
  return <span className="bangumi-portrait">{source && !failed ? <img src={source} alt={alt} loading="lazy" onError={() => setFailed(true)} /> : <FilmSlate size={18} />}</span>;
}

function providerArtworkSource(mediaId: string, category: string, externalId: string, remoteUrl: string | null) {
  const base = `/api/v1/media/${encodeURIComponent(mediaId)}/artwork/provider/${encodeURIComponent(category)}/${encodeURIComponent(externalId)}`;
  return remoteUrl ? `${base}?url=${encodeURIComponent(remoteUrl)}` : base;
}

function GenerationDiagnostics({ result }: { result: NfoGenerationResult }) {
  const warnings = [...result.probe_warnings, ...result.artwork_warnings];
  const counts = warnings.reduce<Record<string, number>>((current, warning) => {
    current[warning.reason] = (current[warning.reason] ?? 0) + 1;
    return current;
  }, {});
  const unavailable = "FFPROBE_UNAVAILABLE" in counts || "FFMPEG_UNAVAILABLE" in counts;

  return <>
    <p className="nfo-generation-result"><FilePlus size={16} />已创建 {result.created_files.length} 个、更新 {result.updated_files.length} 个 NFO，并保存 {result.created_artwork_files.length} 张本地图片{result.probe_warnings.length ? `；${result.probe_warnings.length} 个媒体文件未取得流信息` : ""}{result.artwork_warnings.length ? `；${result.artwork_warnings.length} 张图片处理失败` : ""}。</p>
    {warnings.length ? <div className="nfo-generation-diagnostic">
      {Object.entries(counts).map(([reason, count]) => <span key={reason}>{count} 项：{generationWarningText(reason)}</span>)}
      {unavailable ? <a href="/settings">到设置页配置媒体工具路径</a> : null}
    </div> : null}
  </>;
}

function generationWarningText(reason: string) {
  const messages: Record<string, string> = {
    FFPROBE_UNAVAILABLE: "当前服务未找到 ffprobe",
    FFPROBE_START_FAILED: "ffprobe 无法启动，请检查路径和执行权限",
    FFPROBE_TIMEOUT: "ffprobe 读取媒体超时",
    FFPROBE_FAILED: "ffprobe 无法解析该媒体文件",
    FFPROBE_INVALID_OUTPUT: "ffprobe 返回了无效结果",
    FFPROBE_MEDIA_NOT_FOUND: "执行探测时媒体文件不存在",
    FFMPEG_UNAVAILABLE: "当前服务未找到 ffmpeg",
    FFMPEG_START_FAILED: "ffmpeg 无法启动，请检查路径和执行权限",
    FFMPEG_TIMEOUT: "ffmpeg 截图超时",
    FFMPEG_CAPTURE_FAILED: "ffmpeg 无法从该媒体生成截图",
    FFMPEG_MEDIA_NOT_FOUND: "执行截图时媒体文件不存在",
    ARTWORK_WRITE_FAILED: "图片文件无法写入媒体目录",
    REMOTE_ARTWORK_URL_REJECTED: "远程图片地址不属于允许的元数据来源",
    REMOTE_ARTWORK_DOWNLOAD_FAILED: "远程图片下载失败",
    REMOTE_ARTWORK_INVALID: "远程图片格式或内容无效",
  };
  return messages[reason] ?? reason;
}

type DisplayEpisode = {
  key: string;
  season_number: number;
  episode_number: number;
  title: string;
  original_title: string | null;
  plot: string | null;
  aired: string | null;
  runtime: number | null;
  external_ids: EpisodeScrapeInfo["external_ids"];
  nfo_relative_path: string | null;
  poster_url: string | null;
  poster_source: string;
  providerEpisode?: ProviderEpisode;
};

type DisplaySeason = Omit<SeasonScrapeInfo, "episodes"> & {
  episodes: DisplayEpisode[];
  remoteOnly: boolean;
};

function mergeEpisodeMetadata(
  localSeasons: SeasonScrapeInfo[],
  remoteEpisodes: ProviderEpisode[],
  configuredSeason: number,
  episodeOffset: number,
  provider: "bangumi" | "tmdb",
): DisplaySeason[] {
  const remoteByNumber = new Map(remoteEpisodes.map((episode) => [episode.episode_number, episode]));
  const mergeEpisode = (episode: EpisodeScrapeInfo): DisplayEpisode => {
    const remote = remoteByNumber.get(episode.episode_number + episodeOffset);
    const localArtwork = episode.poster_source === "local";
    return {
      ...episode,
      key: `${episode.season_number}-${episode.episode_number}`,
      title: remote?.title || episode.title,
      original_title: remote?.original_title || episode.original_title,
      plot: remote?.summary || episode.plot,
      aired: remote?.air_date || episode.aired,
      runtime: remote?.runtime_minutes || episode.runtime,
      poster_url: localArtwork ? episode.poster_url : (remote?.image_url || episode.poster_url),
      poster_source: localArtwork ? "local" : (remote?.image_url ? provider : episode.poster_source),
      providerEpisode: remote,
    };
  };

  const seasons = localSeasons.map((season) => ({
    ...season,
    episodes: season.episodes.map(mergeEpisode),
    remoteOnly: false,
  }));
  const selectedSeason = seasons.find((season) => season.season_number === configuredSeason);
  if (selectedSeason) {
    const mappedRemote = new Set(
      selectedSeason.episodes.map((episode) => episode.episode_number + episodeOffset),
    );
    for (const remote of remoteEpisodes) {
      const localNumber = remote.episode_number - episodeOffset;
      if (mappedRemote.has(remote.episode_number) || localNumber < 1) continue;
      selectedSeason.episodes.push(remoteDisplayEpisode(remote, configuredSeason, localNumber));
    }
    selectedSeason.episodes.sort((left, right) => left.episode_number - right.episode_number);
    return seasons;
  }
  if (!remoteEpisodes.length) return seasons;
  seasons.push({
    season_number: configuredSeason,
    title: null,
    original_title: null,
    plot: null,
    year: null,
    premiered: null,
    cast: [],
    external_ids: [],
    artwork: [],
    provider_data: null,
    nfo_relative_path: null,
    poster_url: null,
    poster_source: "missing",
    episodes: remoteEpisodes
      .map((episode) => remoteDisplayEpisode(
        episode, configuredSeason, episode.episode_number - episodeOffset,
      ))
      .filter((episode) => episode.episode_number > 0),
    remoteOnly: true,
  });
  return seasons;
}

function remoteDisplayEpisode(
  episode: ProviderEpisode,
  seasonNumber: number,
  localEpisodeNumber: number,
): DisplayEpisode {
  return {
    key: `${seasonNumber}-${localEpisodeNumber}`,
    season_number: seasonNumber,
    episode_number: localEpisodeNumber,
    title: episode.title,
    original_title: episode.original_title,
    plot: episode.summary,
    aired: episode.air_date,
    runtime: episode.runtime_minutes,
    external_ids: [],
    nfo_relative_path: null,
    poster_url: episode.image_url,
    poster_source: episode.image_url ? episode.provider : "missing",
    providerEpisode: episode,
  };
}

function EpisodeMetadataDetail({ episode, providerName }: { episode: DisplayEpisode; providerName: string }) {
  const remote = episode.providerEpisode;
  const identityMap = new Map(
    episode.external_ids.map((identity) => [
      `${identity.provider.toLocaleLowerCase()}:${identity.external_id}`,
      `${identity.provider} #${identity.external_id}`,
    ]),
  );
  if (remote?.external_id) {
    identityMap.set(
      `${remote.provider}:${remote.external_id}`,
      `${providerName} #${remote.external_id}`,
    );
  }
  const identities = [...identityMap.values()];
  const imageLabel = episode.poster_source === "local"
    ? "本地分集图片"
    : episode.poster_source === "tmdb" || episode.poster_source === "bangumi"
      ? `${providerName} 远程分集剧照`
      : episode.poster_source === "series_fallback"
        ? "沿用剧集海报"
        : "暂无剧照；更新 NFO 时可使用视频截图兜底";
  return <div className="episode-metadata-detail">
    <Artwork className="episode-detail-artwork" url={episode.poster_url} alt={`第 ${episode.episode_number} 集刮削图片`} />
    <div className="episode-detail-content">
      <span className="scrape-level-label">{providerName} 分集刮削数据</span>
      <h5>{episode.title}</h5>
      {episode.original_title && episode.original_title !== episode.title ? <p className="scrape-original">{episode.original_title}</p> : null}
      <div className="scrape-facts">
        <span>S{pad(episode.season_number)}E{pad(episode.episode_number)}</span>
        {remote && remote.episode_number !== episode.episode_number ? <span>来源集号 {remote.episode_number}</span> : null}
        {episode.aired ? <span>{episode.aired}</span> : null}
        {episode.runtime ? <span>{episode.runtime} 分钟</span> : null}
      </div>
      {episode.plot ? <p className="episode-detail-plot">{episode.plot}</p> : <p className="subtle">暂无分集简介。</p>}
      <InfoLine label="外部 ID" values={[...new Set(identities)]} />
      <small className="episode-image-source">{imageLabel}</small>
    </div>
  </div>;
}

function Artwork({ className, url, alt }: { className: string; url: string | null; alt: string }) {
  const source = imageSource(url);
  return <div className={className}>{source ? <img src={source} alt={alt} /> : <FilmSlate size={24} />}</div>;
}

function InfoLine({ label, values }: { label: string; values: string[] }) {
  if (!values.length) return null;
  return <div className="scrape-info-line"><span>{label}</span><div>{values.map((value) => <small key={value}>{value}</small>)}</div></div>;
}

function posterSourceText(source: string, hasSeriesPoster = false) {
  if (source === "local") return "季度海报";
  if (source === "series_fallback" || hasSeriesPoster) return "沿用剧集海报";
  return "暂无季度海报";
}

function pad(value: number) { return String(value).padStart(2, "0"); }
