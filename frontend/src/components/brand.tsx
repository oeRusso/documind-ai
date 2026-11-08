/**
 * Brand pieces drawn in SVG by hand: no downloaded images, nothing loaded from outside.
 */
import { Cpu, Quote, ShieldCheck } from "lucide-react";
import { useId } from "react";

import { cn } from "@/lib/utils";

/** The mark: a page with a folded corner and a spark. */
export function LogoMark({ className }: { className?: string }) {
  // Unique per instance: a gradient defined inside a hidden copy would not paint the others.
  const gradient = useId();
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className={cn("size-8 shrink-0", className)}>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="oklch(0.62 0.2 285)" />
          <stop offset="1" stopColor="oklch(0.45 0.21 270)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${gradient})`} />
      <path d="M10 7.5h8l5 5V24a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 9 24V9a1.5 1.5 0 0 1 1-1.5Z" fill="white" fillOpacity="0.95" />
      <path d="M18 7.5V11a1.5 1.5 0 0 0 1.5 1.5H23" fill="none" stroke="oklch(0.45 0.21 270)" strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M16 15.2l.9 2.2 2.2.9-2.2.9-.9 2.2-.9-2.2-2.2-.9 2.2-.9z" fill="oklch(0.5 0.21 277)" />
    </svg>
  );
}

export function Logo({ className, inverted = false }: { className?: string; inverted?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className={cn("text-[15px] font-semibold tracking-tight", inverted && "text-white")}>
        DocuMind <span className={inverted ? "text-indigo-200" : "text-primary"}>AI</span>
      </span>
    </span>
  );
}

const DOC_TEXT = "#1e1b4b";
const HIGHLIGHT = "#fbbf24";

/** A document with a highlighted passage and the cited answer it supports. */
export function DocumentsIllustration({ className }: { className?: string }) {
  const lines = [112, 130, 148, 184, 202, 220, 238];
  const widths = [146, 128, 150, 120, 146, 96, 132];
  return (
    <svg viewBox="0 0 440 360" fill="none" aria-hidden="true" className={className}>
      <g transform="rotate(-9 150 170)">
        <rect x="56" y="44" width="170" height="226" rx="14" fill="white" fillOpacity="0.05" stroke="white" strokeOpacity="0.14" />
        {[80, 104, 122, 140, 158, 176, 194].map((y, i) => (
          <rect key={y} x="76" y={y} width={i === 0 ? 70 : 120 - (i % 3) * 18} height="7" rx="3.5" fill="white" fillOpacity={i === 0 ? 0.3 : 0.12} />
        ))}
      </g>

      <g>
        <rect x="140" y="56" width="196" height="250" rx="16" fill="oklch(0.3 0.13 278)" />
        <rect x="140" y="56" width="196" height="250" rx="16" fill="white" fillOpacity="0.06" stroke="white" strokeOpacity="0.24" />
        <rect x="162" y="80" width="92" height="10" rx="5" fill="white" fillOpacity="0.6" />
        {lines.map((y, i) => (
          <rect key={y} x="162" y={y} width={widths[i]} height="7" rx="3.5" fill="white" fillOpacity="0.2" />
        ))}
        <rect x="156" y="160" width="164" height="19" rx="6" fill={HIGHLIGHT} fillOpacity="0.18" />
        <rect x="162" y="166" width="140" height="7" rx="3.5" fill={HIGHLIGHT} fillOpacity="0.95" />
        <text x="314" y="89" textAnchor="end" fill="white" fillOpacity="0.5" fontSize="10" fontFamily="inherit">
          p. 4
        </text>
      </g>

      <path d="M320 170 C 360 170, 360 230, 330 246" stroke={HIGHLIGHT} strokeOpacity="0.8" strokeWidth="1.5" strokeDasharray="4 4" />

      <g transform="translate(206 236)">
        <rect width="214" height="104" rx="16" fill="white" />
        <circle cx="22" cy="24" r="9" fill="oklch(0.51 0.21 277)" />
        <path d="M22 19.2l.9 2.2 2.2.9-2.2.9-.9 2.2-.9-2.2-2.2-.9 2.2-.9z" fill="white" />
        <text x="38" y="28" fill={DOC_TEXT} fontSize="11.5" fontWeight="600" fontFamily="inherit">
          El plazo de pago es de 30 días
        </text>
        <rect x="14" y="44" width="186" height="6" rx="3" fill={DOC_TEXT} fillOpacity="0.1" />
        <rect x="14" y="56" width="140" height="6" rx="3" fill={DOC_TEXT} fillOpacity="0.1" />
        <rect x="14" y="74" width="132" height="20" rx="10" fill={HIGHLIGHT} fillOpacity="0.22" />
        <text x="26" y="88" fill="#92400e" fontSize="10" fontWeight="600" fontFamily="inherit">
          Contrato marco · p. 4
        </text>
      </g>
    </svg>
  );
}

const FEATURES = [
  { icon: Quote, text: "Cada respuesta cita el documento, la página y el fragmento." },
  { icon: Cpu, text: "IA 100 % local: tus archivos no salen del servidor." },
  { icon: ShieldCheck, text: "Cada empresa ve solo sus propios datos." },
];

/** The dark side of the sign-in pages. */
export function BrandPanel() {
  return (
    <div className="relative hidden overflow-hidden bg-gradient-to-br from-[var(--brand-from)] to-[var(--brand-to)] p-10 text-white lg:flex lg:flex-col">
      <svg aria-hidden="true" className="absolute inset-0 size-full">
        <defs>
          <pattern id="brand-dots" width="22" height="22" patternUnits="userSpaceOnUse">
            <circle cx="1.5" cy="1.5" r="1" fill="white" fillOpacity="0.1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#brand-dots)" />
      </svg>
      <div aria-hidden="true" className="absolute -top-32 -right-24 size-96 rounded-full bg-indigo-400/25 blur-3xl" />
      <div aria-hidden="true" className="absolute -bottom-40 -left-20 size-96 rounded-full bg-fuchsia-500/15 blur-3xl" />

      <Logo inverted className="relative" />
      <div className="relative my-auto grid gap-10 py-10">
        <DocumentsIllustration className="mx-auto w-full max-w-md drop-shadow-2xl" />
        <div className="grid max-w-md gap-5">
          <h2 className="text-3xl leading-tight font-semibold">Preguntale a los documentos de tu empresa.</h2>
          <ul className="grid gap-3 text-sm text-indigo-100/90">
            {FEATURES.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3">
                <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-md bg-white/10 ring-1 ring-white/15">
                  <Icon className="size-3.5" />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
      </div>
      <p className="relative text-xs text-indigo-200/70">Proyecto de portfolio · Software libre</p>
    </div>
  );
}

/** Small version of the brand panel for narrow screens. */
export function BrandBanner() {
  return (
    <div className="relative mb-10 overflow-hidden rounded-2xl bg-gradient-to-br from-[var(--brand-from)] to-[var(--brand-to)] px-5 pt-5 lg:hidden">
      <div aria-hidden="true" className="absolute -top-16 -right-10 size-48 rounded-full bg-indigo-400/30 blur-3xl" />
      <Logo inverted className="relative" />
      <DocumentsIllustration className="relative mx-auto mt-1 mb-3 w-full max-w-[260px]" />
    </div>
  );
}
