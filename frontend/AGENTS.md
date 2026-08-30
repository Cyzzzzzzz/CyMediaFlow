# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Durable prototype design feedback

- The chosen direction is “Compact Media Shelf”: a poster-first library with a restrained white/soft-gray palette, violet accents, generous rounding, and minimal shadows.
- Keep the left rail limited to exactly two destinations: 首页 and 设置. Do not evolve the home screen into a dashboard or add operational widgets.
- Each poster represents one anime. Keep card metadata to one title and one compact status line.
- Clicking a poster opens a right-side drawer occupying roughly two-thirds of the viewport. Configure matching, season/episode mapping, naming, and Emby scraping in rounded accordion sections inside the drawer.
- Preserve the selected mockup at `../docs/design/selected-home-drawer.png` as visual source of truth for future iterations.
- Treat original video filenames as immutable. File-management UI should operate on same-basename NFO sidecars instead of presenting video rename actions.
- Show the metadata fetched from the selected provider inside the anime detail drawer, while keeping it compact and contained in the matching section.
- Keep scraped metadata in its own drawer accordion, separate from provider matching. Present local `tvshow.nfo`, `season.nfo`, and episode NFO data as a series/season/episode hierarchy with corresponding artwork; when a season poster is absent, visibly label the series-poster fallback.
- Offer Bangumi-based NFO creation and managed updates inside the scrape-information accordion. Require inline confirmation. Keep field editing and locks in a compact, collapsed-by-default section; locked fields preserve the existing or manually edited value while unlocked fields refresh. Never modify video files.
- Keep a metadata scrape/refresh action permanently visible in the scrape-information accordion, including for works that already have complete local NFO data. Resolve its Bangumi ID from the saved binding first and local NFO identity second; keep provider refresh separate from every NFO write operation.
- For automatic episode artwork, preserve the priority order remote artwork, existing local sidecar/NFO reference, season or series preview fallback, then an ffmpeg screenshot fallback. A known remote preview must not trigger video capture merely because its local download failed. Automatic NFO screenshot fallback must not overwrite existing artwork, must skip non-regular media, and must report per-file failures in the result.
- Treat one local work as a primary provider subject plus any number of related Bangumi/TMDB subjects. Keep subject management compact in the matching accordion, and place range-based cour/season rules in the existing season/episode mapping accordion rather than adding a new dashboard page.
- Keep the primary work explicit and independent from the provider currently being browsed or refreshed. In multi-subject mappings, group “Bangumi 完整条目信息” by local season and list every Bangumi subject used by that season's range rules.
- In the NFO preview, provide a persistent per-work folder exclusion control. An excluded folder and all descendants must remain visible but disabled, and must not participate in segmented-source validation or NFO generation.
- In scraped season and episode views, treat the freshly read local NFO as the source of truth. Merge browsed-provider episode data only when its provider episode ID matches the local NFO identity; never overlay one subject's episode numbers onto another local season or cour.
- Persist expensive work-search, provider-detail, provider-episode, local scrape-info, and NFO-preview results. Opening a drawer should reuse the last result without automatically searching, scraping, or reanalyzing; explicit search, metadata scrape, and preview refresh buttons are the only refresh triggers.
- Show a manual episode-artwork extraction action on every local season. It must process only the selected season, atomically replace existing episode sidecar artwork after a new screenshot succeeds, respect non-regular media and folder exclusions, and never run automatically when the drawer opens.
- Preserve range mapping for normal episodes and add exact relative-path mapping for unnumbered nested movies or specials. Default detected feature films to Emby Season 0, keep the season/episode editable, never rename or move the video, and exclude Menu, Preview, Trailer, stage-greeting, and similar extras from automatic main-feature mapping.
- When a folder is manually excluded from NFO handling, create a persistent `.ignore` inside it after configuration is saved. Do not silently delete an existing marker when the UI exclusion is later cancelled.
- Keep per-work daily refresh controls compact inside the scrape-information accordion. Reuse the saved provider, mapping, exclusion, lock, and manual-field configuration; show the persisted last result and Bangumi broadcast progress, and automatically disable the schedule after the final episode receives one safe post-air refresh.
- In scraped episode previews, apply the same dual-offset mapping as NFO generation: provider episode = Emby episode + provider metadata offset - Emby local offset. Merge local and remote episodes on that mapped identity so absolute-numbered files do not produce duplicate unshifted remote cards.
- Keep NFO standard naming opt-in and folder-scoped. The selected folder uses `{preferred title} SxxExx.nfo`; other folders keep video-basename sidecars. Never rename the video, and preserve locked fields while migrating an existing NFO to the new name.
- Keep subtitle matching in a compact, separately opened accordion. Match only same-folder episode files, preserve simplified/traditional and bilingual variants as distinct suffixes (`sc`, `tc`, `scjp`, `tcjp`), require inline confirmation, and never overwrite an existing subtitle target or modify a video.
