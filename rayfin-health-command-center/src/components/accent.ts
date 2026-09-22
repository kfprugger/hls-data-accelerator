//-----------------------------------------------------------------------
// Per-lens accent palette. Kept out of the component module so fast refresh
// stays component-only.
//-----------------------------------------------------------------------

export type Accent = "payer" | "provider" | "medtech";

interface AccentTokens {
    /** Gradient start, paired with `to` on every gradient surface. */
    from: string;
    to: string;
    /** Foreground tint for captions and active icons. */
    text: string;
    ring: string;
    glow: string;
    /** Literal hex for SVG strokes, which cannot resolve Tailwind classes. */
    stroke: string;
}

export const ACCENT: Record<Accent, AccentTokens> = {
    payer: {
        from: "from-sky-400",
        to: "to-indigo-500",
        text: "text-sky-300",
        ring: "ring-sky-400/30",
        glow: "shadow-[0_0_45px_-12px_rgba(56,189,248,0.65)]",
        stroke: "#38bdf8",
    },
    provider: {
        from: "from-emerald-400",
        to: "to-teal-500",
        text: "text-emerald-300",
        ring: "ring-emerald-400/30",
        glow: "shadow-[0_0_45px_-12px_rgba(52,211,153,0.65)]",
        stroke: "#34d399",
    },
    medtech: {
        from: "from-fuchsia-400",
        to: "to-violet-500",
        text: "text-fuchsia-300",
        ring: "ring-fuchsia-400/30",
        glow: "shadow-[0_0_45px_-12px_rgba(232,121,249,0.65)]",
        stroke: "#e879f9",
    },
};
