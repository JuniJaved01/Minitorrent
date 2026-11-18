---
name: Cybernetic Torrential
colors:
  surface: '#0e131f'
  surface-dim: '#0e131f'
  surface-bright: '#343946'
  surface-container-lowest: '#080e1a'
  surface-container-low: '#161c28'
  surface-container: '#1a202c'
  surface-container-high: '#242a36'
  surface-container-highest: '#2f3542'
  on-surface: '#dde2f3'
  on-surface-variant: '#b9cacb'
  inverse-surface: '#dde2f3'
  inverse-on-surface: '#2b303d'
  outline: '#849495'
  outline-variant: '#3a494b'
  surface-tint: '#00dce6'
  primary: '#e0fdff'
  on-primary: '#00373a'
  primary-container: '#00f2fe'
  on-primary-container: '#006a70'
  inverse-primary: '#00696f'
  secondary: '#4edea3'
  on-secondary: '#003824'
  secondary-container: '#00a572'
  on-secondary-container: '#00311f'
  tertiary: '#fff5ee'
  on-tertiary: '#472a00'
  tertiary-container: '#ffd3a1'
  on-tertiary-container: '#875400'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#6ff6ff'
  primary-fixed-dim: '#00dce6'
  on-primary-fixed: '#002022'
  on-primary-fixed-variant: '#004f53'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#0e131f'
  on-background: '#dde2f3'
  surface-variant: '#2f3542'
typography:
  headline-xl:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 18px
    fontWeight: '500'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Geist
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.04em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '400'
    lineHeight: 14px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.75rem
  gutter-dense: 0.375rem
  margin: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system establishes a high-performance, dark-mode desktop terminal aesthetic tailored for decentralized peer-to-peer networking. The visual signature bridges raw telemetry utilities with modern, precision-engineered user software.

### Tone & Personality
- **Surgical & Precise:** Instant readouts, zero-latency visual feedback, micro-metric visibility.
- **Architectural & Technical:** Inspired by dark-room network operations centers (NOC) and high-density telemetry dashboards.
- **Trustworthy & Resilient:** Communicates stable, uninterrupted background execution and cryptographic integrity.

### Target Audience & Emotional Goal
Geared toward advanced technical users, network engineers, storage archivists, and digital minimalists who expect low-overhead interfaces, immediate data density, and granular system controls without artificial decorative clutter. The UI evokes focused control, transparency, and computational speed.

### Design Movement: Dark Precision Glass & Technical Utility
A hybrid of deep obsidian surfaces, low-glare frosted glass panels, hairline neon dividers, and ultra-sharp data readouts. It strips out unnecessary ornamentation in favor of crisp status markers, dense data tables, and ambient illumination reflecting active network traffic.

## Colors

The palette is engineered specifically for deep-dark displays to maximize legibility of dense real-time figures while reducing ocular strain.

### Palette Strategy
- **Primary (`#00f2fe` - Cyber Cyan):** Represents high-frequency ingestion, downstream bandwidth, active peer connections, and focused interactive states.
- **Secondary (`#10b981` - Emerald Signal):** Signals completed transfers, verified SHA-256 hash checks, seeding health, and optimal peer swarms.
- **Tertiary (`#f59e0b` - Amber Alert):** Applied strictly to throttled peers, incoming DHT queries, buffer pressure, and non-fatal network reconnects.
- **Neutral (`#030712` - Pitch Abyss):** The canvas background anchors on ultra-deep slate/zinc tones, rising through layered surfaces (`#090d16`, `#111827`, `#1f2937`) to establish visual elevation without white-light emission.

### Accent Rules
Use high-chroma primary and secondary tones sparingly (1-3% of surface area) reserved for progress bars, metric sparks, active toggles, and status badges. Inactive or passive metrics remain rendered in mid-tone cool grays to keep visual noise minimal.

## Typography

The typographic hierarchy implements a tripartite division based on cognitive function:

1. **Space Grotesk (Structural Headings):** Geometric, modern, and sharp. Gives structural anchor to window titles, panel headers, and modal overviews.
2. **Geist (Body & System Controls):** Utilitarian, highly readable sans-serif for UI interactions, configurations, nested menus, and system alerts.
3. **JetBrains Mono (Telemetry & Data):** Non-negotiable for all numeric variables, download/upload rates, swarm health ratios, file chunk allocations, IP addresses, port binds, and cryptographic info-hashes. Ensures numeric columns align into clean vertical axes without jitter when figures update at 60fps.

## Layout & Spacing

Designed for compact, dense desktop viewports where maximizing information density per pixel is paramount.

### Layout Architecture
- **Master-Detail Desktop Grid:** Composed of a persistent utility sidebar (64px collapsed, 240px expanded), an adaptable telemetry top-shelf (bandwidth graphs, global limits, DHT nodes), and a fluid multi-column data table occupying the central canvas.
- **Rhythm & Grid:** Built upon an unyielding 4px baseline sub-grid (`space-xs` = 4px, `space-sm` = 8px, `space-md` = 12px, `space-lg` = 16px). Table rows maintain a strict height of 36px (compact) or 48px (detailed).
- **Responsive Adaptations:**
  - *Standard Desktop (>1440px):* Full 6-pane view (Sidebar, Top Graph, Swarm List, Inspector Drawer, Peer Map, Piece-Availability Map).
  - *Compact Desktop (1024px - 1439px):* Inspector Drawer docks to the bottom; Peer Map shifts into a sub-tab.
  - *Minimal Mode (<1024px):* Sidebar collapses into iconic tool rail (64px); bandwidth sparklines reduce to numerical mini-badges.

## Elevation & Depth

Visual hierarchy does not rely on diffuse, spread-out daylight shadows. Instead, it utilizes surface luminescence, controlled translucency, and hairline boundaries.

### Layering Philosophy
- **Base Canvas (Level 0):** `#030712` (Solid, near-pitch black).
- **Recessed Containers (Level 1):** `#090d16` with a `1px solid rgba(255, 255, 255, 0.05)` rim. Used for graph wells, log outputs, and data tables.
- **Floating Panels & Modals (Level 2):** Translucent `#0e1526` backed by `backdrop-filter: blur(16px)` and illuminated borders: `1px solid rgba(0, 242, 254, 0.18)`.
- **Telemetry Popovers (Level 3):** High-opacity frosted surface with an inward micro-glow (`box-shadow: inset 0 1px 0 0 rgba(255, 255, 255, 0.1), 0 8px 32px rgba(0, 0, 0, 0.6)`).

### Active Borders
Selected torrent items or focused inputs emit an ambient hairline glow using `#00f2fe` at 30% alpha, maintaining distinct edge sharpness without blurring into adjacent cells.

## Shapes

The shape system adopts a **Soft (Level 1)** geometric form language. 

- Base UI components, cards, tables, and inputs leverage `0.25rem` (4px) corner radii.
- Modals, overlays, and elevated dialogs scale to `0.5rem` (8px).
- Status dots, piece progress blocks, and micro telemetry flags preserve crisp orthogonal geometries, intentionally avoiding pill shapes or extreme roundness to maintain a rigorous instrumentation feel.

## Components

### Buttons & Action Bars
- **Primary Action (Start/Resume):** Solid `#00f2fe` text on an ultra-dark cyan glass base (`rgba(0, 242, 254, 0.08)`), framed by a `1px solid rgba(0, 242, 254, 0.4)` border. On hover, background shifts to `rgba(0, 242, 254, 0.2)` with a sharp `box-shadow: 0 0 12px rgba(0, 242, 254, 0.3)`.
- **Secondary Action (Pause/Config):** Ghost container with neutral border (`rgba(255, 255, 255, 0.1)`), transitioning to `rgba(255, 255, 255, 0.05)` on hover.
- **Destructive (Purge Torrent + Data):** Hairline crimson boundary (`#ef4444` at 40%), text `#ef4444`, transitioning into a solid muted-red outline when primed.

### Data Tables (Torrent & Peer Inspector)
- **Header:** Sticky, 28px height, `label-sm` uppercase JetBrains Mono, `#64748b` text, separated by a distinct hairline divider.
- **Rows:** Alternating subtle row backgrounds (`#030712` and `#060b17`) to enhance tracking across 12+ columns. Hover state introduces a full-width cyan gradient tint at 4% opacity.
- **Cell Padding:** `0.375rem` vertical, `0.75rem` horizontal.
- **Active Selection:** Marked by a `2px solid #00f2fe` indicator bar pinned to the left edge of the selected row.

### Bandwidth Sparklines & Telemetry Bars
- **Download/Upload Progress:** Segmented progress strip showing downloaded pieces (emerald), in-flight verification (cyan), and missing blocks (dark zinc `#1e293b`).
- **Telemetry Indicators:** Miniature line charts updating dynamically without anti-aliasing artifacts; down-rate rendered in crisp cyan (`#00f2fe`), up-rate rendered in neon violet/emerald (`#10b981`).

### Form Inputs & Network Fields
- **IP / Port / Directory Fields:** Monospace body, dark background (`#070d18`), border `1px solid rgba(255, 255, 255, 0.12)`.
- **Focus State:** Border color shifts instantly to `#00f2fe` with an internal glow (`0 0 0 1px #00f2fe`).
- **Inline Validation:** Instant cryptographic checksum feedback displayed with miniature mono tags (`[VALID: SHA-256]` in emerald, `[MISMATCH]` in amber).

### Status Badges & Chips
- **States (Downloading, Seeding, Paused, Error):** Strict capsule-box (4px radius), 20px total height, containing an illuminated 6px status beacon (pulsing for active connections) accompanied by compact mono text (`DL: 48.2 MB/s`, `SEED: 1.4 MB/s`).