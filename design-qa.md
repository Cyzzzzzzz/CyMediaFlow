# Design QA

## Target and evidence

- Selected reference: `docs/design/selected-home-drawer.png` (1751 × 898, 1× density)
- Final desktop capture: `.data/design-qa/implementation-07.png` (1751 × 898, 1× density)
- Full comparison: `.data/design-qa/comparison-07-full.png`
- Focused drawer comparison: `.data/design-qa/comparison-07-drawer.png`
- Settings capture: `.data/design-qa/implementation-07-settings.png` (1751 × 898, 1× density)
- Tablet capture: `.data/design-qa/implementation-06-tablet.png` (1024 × 768, 1× density)
- Mobile capture: `.data/design-qa/implementation-07-mobile.png` (390 × 844, 1× density)
- Required state: home page with the first real media item selected, Bangumi match section expanded, one candidate selected, and the fixed footer visible.

## Comparison history

### Iteration 1

Evidence: `implementation-03.png`, `implementation-04.png`.

- P1: remote Bangumi covers did not load. Fixed by adding the allowlisted backend image proxy and cache.
- P1: drawer header was materially shorter than the reference. Fixed by increasing the cover, title, and header height.
- P2: three candidates made the match panel too dense. Fixed by presenting the strongest candidate only.
- P2: search and brand treatments did not match the selected direction. Fixed with the compact search control and Phosphor FilmSlate brand icon.

### Iteration 2

Evidence: `implementation-06.png`, `comparison-06-full.png`, `comparison-06-drawer.png`.

- P2: collapsed accordions showed unnecessary summaries. Fixed by hiding secondary text in the collapsed state.
- P2: selection feedback was visually weak. Fixed with a green filled check and selected poster outline.
- P2: mobile header actions could create horizontal overflow. Fixed by allowing the search flex item to shrink.

### Final iteration

Evidence: `implementation-07.png`, `comparison-07-full.png`, `comparison-07-drawer.png`, `implementation-07-settings.png`, and `implementation-07-mobile.png`.

- No P0, P1, or P2 visual defects remain.
- The implementation drawer is 1040 px wide at the reference viewport, honoring the product requirement that it occupy roughly two-thirds of the page; the selected concept image used a slightly narrower 962 px drawer.
- The real test library contains five works, so poster count and titles intentionally differ from the concept image.

## Final surface review

- Typography: Noto Sans SC and Inter render consistently; title, label, and helper-text hierarchy matches the compact reference direction.
- Layout and spacing: poster wall, two-item rail, rounded drawer, accordion rhythm, and fixed footer are stable. No horizontal overflow at desktop, settings, tablet, or 390 px mobile widths.
- Color and tokens: white/light-gray surfaces, restrained purple accent, soft borders, and green success states are consistent.
- Imagery: all five real media posters plus drawer and candidate covers loaded successfully. Remote Bangumi images use the local allowlisted proxy endpoint.
- Interactions: home/settings navigation, search, refresh, poster selection, candidate selection, all four accordions, proxy save, and Escape-to-close were verified.
- Accessibility: dialog semantics, accessible labels, keyboard Escape handling, button states, and visible focus-capable native controls are present.
- Browser health: zero console errors during the final desktop/settings/mobile run.

## Engineering verification

- Backend tests: 8 passed.
- Backend Ruff lint and format checks: passed.
- Frontend TypeScript check: passed.
- Frontend component test: 1 passed.
- Frontend production build: passed.
- Sites packaging tests: 4 passed.
- Real test directory: 5 media folders returned without media-file mutation.
- Live Bangumi proxy check: metadata and cover requests succeeded through `http://192.168.5.124:20181`.

## Naming preview extension — 2026-08-23

- Desktop evidence: `.data/design-qa/naming-preview-03.png` and `.data/design-qa/naming-preview-03-collapsed.png` at 1751 × 898, 1× density.
- Mobile evidence: `.data/design-qa/naming-preview-03-mobile.png` at 390 × 844, 1× density.
- The naming accordion renders all 73 entries grouped into eight folders, with 12 regular episodes selected and 61 extra files skipped by default.
- Each folder can be collapsed independently. Collapsing the first 12-file folder reduced visible rows from 73 to 61 while the selected summary stayed at 12; reopening restored all rows.
- Individual checkboxes and folder-level select/cancel actions were exercised successfully.
- Desktop and mobile have no horizontal overflow; the fixed drawer footer remains visible.
- Refresh interaction succeeds and the browser console reports zero errors.

## NFO sidecar and scraped metadata — 2026-08-23

- Scraped metadata evidence: `.data/design-qa/metadata-detail-01.png` at 1751 × 898, 1× density.
- NFO evidence: `.data/design-qa/nfo-preview-01.png` and `.data/design-qa/nfo-preview-01-collapsed.png` at 1751 × 898; `.data/design-qa/nfo-preview-01-mobile.png` at 390 × 844.
- The matching detail shows Bangumi ID, localized and original titles, year, episode count, and a compact three-line summary.
- The previous video naming controls are absent. The NFO section explicitly states that video files are not renamed, moved, or overwritten.
- The 73-video sample renders all eight folders with 12 NFO actions selected and 61 extras skipped by default.
- Folder collapse, individual selection, folder batch selection, refresh, desktop layout, and mobile layout passed with zero console errors and no horizontal overflow.

Final result: passed

## Persistent metadata scrape action — 2026-08-23

- Desktop evidence: `frontend/.data/design-qa/scrape-info-01.png` at 1751 × 898, 1× density.
- The tested work already has a local `tvshow.nfo`; the “刮削元数据” action remains visible and enabled in the scrape-information accordion.
- Clicking the action made a fresh Bangumi detail request and rendered the inline success state “已重新获取 Bangumi 元数据”.
- Provider refresh remains visually and behaviorally separate from NFO generation; no NFO write request was made.
- The action and status fit the compact rounded layout without page-level horizontal overflow.

Final result: passed

## Bangumi NFO generation — 2026-08-23

- Desktop confirmation evidence: `.data/design-qa/nfo-generation-confirm-01.png` at 1751 × 898, 1× density.
- A series without local NFO data shows a compact “Bangumi 自动补全” card inside the scrape-information accordion.
- The first click only reveals the inline confirmation; no generation request is made until “确认生成” is clicked.
- The card states the write boundary: create `tvshow.nfo`, `season.nfo`, and same-basename episode NFO files; never overwrite existing files.
- The confirmation state has no page-level horizontal overflow and the browser console reports zero errors.

Final result: passed

## Separate scrape-information hierarchy — 2026-08-23

- Desktop evidence: `.data/design-qa/scrape-info-01.png` at 1751 × 898, 1× density.
- Mobile evidence: `.data/design-qa/scrape-info-01-mobile.png` at 390 × 844, 1× density.
- Scrape information now has its own accordion; provider search and binding remain in the matching accordion.
- The real sample renders one series poster, one explicitly labeled series-poster fallback for Season 1, and 12 episode thumbnails.
- All 12 episode cards are present. Their strip intentionally scrolls horizontally to keep the drawer compact.
- Desktop and mobile have no page-level horizontal overflow; all 14 artwork images loaded and the browser console reported zero errors.

Final result: passed
