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
- For episode artwork, preserve the priority order remote artwork, existing local sidecar, then an ffmpeg screenshot fallback. Generate screenshots only during a confirmed NFO operation, never overwrite existing artwork, skip non-regular media, and report per-file failures in the result.
