import type { SubscriptionDraft, SubscriptionMatch } from "./types";

export function emptySubscription(defaultExcludes: string[] = []): SubscriptionDraft {
  return {
    title: "", folder_name: "", aliases: [], season: 1, season_offset: 0, episode_offset: 0,
    preferred_group: null, preferred_resolution: null, preferred_subtitle: null,
    exclude_keywords: [...defaultExcludes], enabled: true, archived: false, poster_url: null, year: null,
    source_title: "", source: null, subtitle: null, resolution: null, release_group: null,
    air_weekday: null, provider: null, provider_id: null,
  };
}

export function applyMetadata(form: SubscriptionDraft, match: SubscriptionMatch): SubscriptionDraft {
  return { ...form, title: match.title, year: match.year ?? form.year, poster_url: match.image_url,
    provider: match.provider, provider_id: match.external_id,
    aliases: [...new Set([...form.aliases, form.source_title || form.title, match.original_title ?? ""].filter(Boolean))],
  };
}

export function validSubscription(form: SubscriptionDraft): boolean {
  return Boolean(form.title.trim()) && Number.isInteger(form.season) && form.season >= 0 && form.season <= 99
    && Number.isInteger(form.season_offset) && form.season + form.season_offset >= 0 && form.season + form.season_offset <= 99
    && Number.isInteger(form.episode_offset) && Math.abs(form.episode_offset) <= 999
    && (form.year === null || (form.year >= 1900 && form.year <= 2100));
}
