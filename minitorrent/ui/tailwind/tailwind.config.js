// Tailwind build config for the MiniTorrent UI (design tokens copied from "Minitorrent UIUX/.../DESIGN.md").
// Only needed if you change classes in ui/static/*.  Rebuild with:   ui/tailwind/build.sh   (or build.bat)
module.exports = {
  darkMode: "class",
  content: ["../static/index.html", "../static/app.js"],
  theme: {
    extend: {
      colors: {
        "secondary-fixed-dim": "#4edea3", "on-tertiary-fixed": "#2a1700", "primary-fixed-dim": "#00dce6",
        "inverse-on-surface": "#2b303d", "outline-variant": "#3a494b", "tertiary-container": "#ffd3a1",
        "surface-container-lowest": "#080e1a", "on-error-container": "#ffdad6", "surface-variant": "#2f3542",
        primary: "#e0fdff", "surface-dim": "#0e131f", "on-tertiary": "#472a00", "on-secondary-fixed-variant": "#005236",
        "surface-container-highest": "#2f3542", "surface-container-high": "#242a36", "on-primary-container": "#006a70",
        "on-tertiary-container": "#875400", "tertiary-fixed-dim": "#ffb95f", "primary-container": "#00f2fe",
        "on-tertiary-fixed-variant": "#653e00", "secondary-container": "#00a572", secondary: "#4edea3",
        "on-background": "#dde2f3", outline: "#849495", tertiary: "#fff5ee", "inverse-primary": "#00696f",
        "on-primary": "#00373a", "on-primary-fixed": "#002022", error: "#ffb4ab", "on-primary-fixed-variant": "#004f53",
        "on-surface-variant": "#b9cacb", "on-secondary-container": "#00311f", "surface-tint": "#00dce6",
        "surface-container-low": "#161c28", "secondary-fixed": "#6ffbbe", "surface-container": "#1a202c",
        "inverse-surface": "#dde2f3", "error-container": "#93000a", "primary-fixed": "#6ff6ff", "on-error": "#690005",
        "on-secondary": "#003824", "on-secondary-fixed": "#002113", "surface-bright": "#343946", background: "#0e131f",
        "on-surface": "#dde2f3", surface: "#0e131f", "tertiary-fixed": "#ffddb8",
      },
      borderRadius: { DEFAULT: "0.125rem", lg: "0.25rem", xl: "0.5rem", full: "0.75rem" },
      spacing: {
        "space-md": "0.75rem", gutter: "0.75rem", "space-sm": "0.5rem", margin: "1rem", "space-lg": "1rem",
        "gutter-dense": "0.375rem", "space-xl": "1.5rem", "space-xs": "0.25rem",
      },
      fontFamily: {
        "headline-md": ["Space Grotesk", "system-ui", "sans-serif"], "headline-lg": ["Space Grotesk", "system-ui", "sans-serif"],
        "headline-xl": ["Space Grotesk", "system-ui", "sans-serif"], "body-lg": ["Geist", "system-ui", "sans-serif"],
        "body-md": ["Geist", "system-ui", "sans-serif"], "body-sm": ["Geist", "system-ui", "sans-serif"],
        "label-sm": ["JetBrains Mono", "ui-monospace", "monospace"], "label-md": ["JetBrains Mono", "ui-monospace", "monospace"],
        "label-lg": ["JetBrains Mono", "ui-monospace", "monospace"], mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      fontSize: {
        "headline-md": ["18px", { lineHeight: "24px", letterSpacing: "-0.01em", fontWeight: "500" }],
        "headline-lg": ["24px", { lineHeight: "32px", letterSpacing: "-0.015em", fontWeight: "600" }],
        "headline-xl": ["32px", { lineHeight: "40px", letterSpacing: "-0.02em", fontWeight: "600" }],
        "body-lg": ["16px", { lineHeight: "24px", fontWeight: "400" }],
        "label-sm": ["10px", { lineHeight: "14px", letterSpacing: "0.05em", fontWeight: "400" }],
        "label-lg": ["13px", { lineHeight: "18px", letterSpacing: "0.02em", fontWeight: "500" }],
        "body-sm": ["12px", { lineHeight: "16px", fontWeight: "400" }],
        "label-md": ["11px", { lineHeight: "16px", letterSpacing: "0.04em", fontWeight: "500" }],
        "body-md": ["14px", { lineHeight: "20px", fontWeight: "400" }],
      },
    },
  },
};
