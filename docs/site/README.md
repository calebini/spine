# Spine field guide

An offline-capable HTML documentation site with an operator guide and ten custom
SVG architecture diagrams. It uses the Cortext1 theme specification 1.1.0, with
locally bundled Syne, Inter, and JetBrains Mono fonts and their OFL licenses.

## Open the guide

Open `index.html` directly in a modern browser. No installation, build, external
font service, or JavaScript CDN is required. Source links expect the surrounding
Spine repository to remain in place.

For a local browser preview, run this from the repository root:

```sh
python3 -m http.server 8765 --bind 127.0.0.1
```

Then visit [the field guide](http://127.0.0.1:8765/docs/site/).

Serve the repository root for the relative spec/runtime source links to resolve.
Publishing only this folder preserves the guide and diagrams, but source links
must then be rewritten to a selected repository revision or bundled references.

## Contents

- Product overview and guided entry points.
- Getting started, atomic scheduling, notification profiles, time and recurrence,
  locations and temporal bindings, work and delivery, operations and recovery.
- Command reference, glossary, source map, and implementation/design scope.
- Architecture atlas: authority, runtime, ontology, versions/lifecycles, atomic
  creation, mutation/reconciliation, notification/attempt lifecycle, temporal
  provenance, relationships/bindings, deployment/failure containment.

Features include search (Command/Ctrl K), deep links, five Cortext1 themes,
copyable commands, native fullscreen, expanded diagrams with zoom, optional path tracing, SVG
export, keyboard navigation, reduced-motion support, and a responsive layout.
Dense diagrams scroll horizontally on narrow screens; expanded mode offers
additional zoom and scrolling. Tracing illustrates direction, not live activity.

Use **Trace flow** inside an expanded diagram to animate its connections, including
in native fullscreen. The trace setting is shared with the inline view and
remembered separately for each diagram until the page is reloaded. Closing,
reopening, and zooming preserve it. With reduced motion enabled, the control
becomes **Highlight paths** and shows static highlights instead of animation.

The title picker in the expanded viewer switches between all ten diagrams without
closing the viewer or leaving fullscreen. Each selection resets zoom and scrolling
to fit the new diagram, restores its trace setting, and leaves the underlying
documentation page in place.

Use **Full screen** in the top bar to request native page fullscreen with browser
navigation hidden. The same control appears beside the expanded diagram's zoom
controls; expanded diagrams fill the display while native fullscreen is active.
Use **Exit full screen** or Escape to exit. Fullscreen requires a user click and
browser permission. Unsupported or blocked requests show an explanatory message;
the page remains usable. If an embedded preview blocks fullscreen, open the local
site URL in Chrome or Safari.

Use `?theme=cortex-dark`, `voltage-blue`, `cortex-purple`, `signal-live`, or
`inverted` to select a theme explicitly. The selector otherwise remembers the
last choice where browser storage is available.

## Public hosting

The public site is [calebini.github.io/spine](https://calebini.github.io/spine/).
The `Publish documentation` workflow deploys site changes pushed to `main`, and
can also be run manually from GitHub Actions. Repository Settings → Pages uses
**GitHub Actions** as its publishing source.

`build-pages.mjs` packages an explicit allowlist of HTML, CSS, JavaScript, fonts,
licenses, and the logo. It excludes browser screenshots, verification scripts,
and the rest of the repository. Published source links point to GitHub at the
deployment commit; local/offline links remain unchanged. No runtime service,
database, or credentials are deployed.

Verify packaging with `node --test docs/site/build-pages.test.mjs`. To preview an
artifact, run `node docs/site/build-pages.mjs /tmp/spine-pages-preview` with a new,
nonexistent destination directory, then serve that directory with an HTTP server.

## Authority and maintenance

The HTML is explanatory documentation. `specs/` remains normative; `contracts/`
owns public machine-readable agreements. Diagram descriptions explicitly identify
logical/grouped relationships, illustrative component roles, and future boundaries.

Content was checked against runtime 0.3.0, schema 12, and the audited Tickerd 0.2.0
contract on 2026-09-04. Runtime constants and the executing `system.info` response
take precedence over older narrative version references. Update the site's
baseline labels when those implementation facts change.

- `index.html`: accessible application shell and dialogs.
- `styles.css`: brand themes, typography, layouts, responsive and print styles.
- `content.js`: operator chapters, command reference, and source links.
- `diagrams.js`: all ten diagram definitions, text equivalents, and source notes.
- `app.js`: routing, search, themes, clipboard, tracing, expansion, and export.
- `assets/fonts/`: bundled fonts and licenses.

## Browser verification

`verify.mjs` checks all 17 non-home routes plus the homepage, desktop/mobile
overflow, SVG text bounds, source targets, tracing, expansion, zoom, export,
search, copy controls, themes, deep links, and direct file access. It writes
screenshots to ignored `qa-output/` and optionally runs axe accessibility checks.

Install verification-only dependencies outside the production site:

```sh
npm install --prefix /tmp/spine-docs-qa playwright-core axe-core --no-save
SPINE_PLAYWRIGHT_PATH=/tmp/spine-docs-qa/node_modules/playwright-core \
SPINE_AXE_PATH=/tmp/spine-docs-qa/node_modules/axe-core/axe.min.js \
node docs/site/verify.mjs
```

The local preview server must be running. The verifier defaults to installed
Chrome; set `SPINE_CHROME_PATH` for another Chromium executable, or
`SPINE_DOCS_URL` for a different local URL. These checks validate the documentation
interface; they do not replace Spine runtime or gateway qualification tests.

Run `verify-fullscreen.mjs` with the same `SPINE_PLAYWRIGHT_PATH` environment to
exercise real native enter/exit, navigation while fullscreen, expanded-diagram
top-layer visibility and fit, externally initiated exit, and unavailable/blocked
browser fallbacks.

Run `verify-flows.mjs` with the same environment to check actual animation in all
ten expanded diagrams, the diagram picker, shared trace state, zoom/reopen/navigation, native
fullscreen, reduced-motion changes, and narrow-screen controls. Set
`SPINE_AXE_PATH` to include expanded-view accessibility checks.
