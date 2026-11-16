"use client";

/**
 * Questions per day: one series, thin bars anchored to the baseline, a tooltip per bar (bigger
 * hit area than the bar) and the same numbers as a table for screen readers (stage 10).
 * Plain SVG: no chart library for one bar chart.
 */

import { useState } from "react";

export type DayPoint = { day: string; questions: number };

const HEIGHT = 160;
const LABEL_SPACE = 22;

export function formatDay(day: string): string {
  const [, month, date] = day.split("-");
  return `${Number(date)}/${Number(month)}`;
}

/** A round top for the axis: 1, 2, 5, 10, 20, 50... at or above the maximum. */
export function niceMax(max: number): number {
  if (max <= 1) return 1;
  const power = 10 ** Math.floor(Math.log10(max));
  for (const step of [1, 2, 5, 10]) if (step * power >= max) return step * power;
  return 10 * power;
}

export function QuestionsChart({ points }: { points: DayPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const top = niceMax(Math.max(0, ...points.map((p) => p.questions)));
  const slot = 100 / Math.max(points.length, 1); // percent of the width per day
  const labelEvery = Math.ceil(points.length / 8);
  const active = hover === null ? null : points[hover];

  return (
    <figure className="grid gap-2">
      <div className="relative" style={{ height: HEIGHT + LABEL_SPACE }} onMouseLeave={() => setHover(null)}>
        <svg
          className="absolute inset-0 h-full w-full overflow-visible"
          viewBox={`0 0 100 ${HEIGHT + LABEL_SPACE}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {[0, 0.5, 1].map((f) => (
            <line
              key={f}
              x1={0}
              x2={100}
              y1={HEIGHT - f * HEIGHT}
              y2={HEIGHT - f * HEIGHT}
              className="stroke-border"
              strokeWidth={f === 0 ? 1 : 0.5}
              vectorEffect="non-scaling-stroke"
              strokeDasharray={f === 0 ? undefined : "3 3"}
            />
          ))}
          {points.map((p, i) => {
            const h = (p.questions / top) * HEIGHT;
            const width = Math.min(slot * 0.6, 4);
            return (
              <rect
                key={p.day}
                x={i * slot + (slot - width) / 2}
                y={HEIGHT - h}
                width={width}
                height={h}
                rx={0.6}
                className={hover === i ? "fill-primary" : "fill-primary/70"}
              />
            );
          })}
        </svg>
        {/* Axis numbers and day labels in HTML: they keep their size whatever the width. */}
        <span className="absolute -top-2 left-0 text-[11px] text-muted-foreground">{top}</span>
        <div className="absolute inset-x-0 flex" style={{ top: HEIGHT + 4 }}>
          {points.map((p, i) => (
            <span key={p.day} className="text-center text-[11px] text-muted-foreground" style={{ width: `${slot}%` }}>
              {i % labelEvery === 0 ? formatDay(p.day) : ""}
            </span>
          ))}
        </div>
        {/* Hit areas: the whole column of each day, not just the thin bar. */}
        <div className="absolute inset-x-0 top-0 flex" style={{ height: HEIGHT }}>
          {points.map((p, i) => (
            <button
              key={p.day}
              type="button"
              className="h-full focus-visible:outline-2 focus-visible:outline-ring"
              style={{ width: `${slot}%` }}
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              aria-label={`${formatDay(p.day)}: ${p.questions} preguntas`}
            />
          ))}
        </div>
        {active && hover !== null && (
          <div
            role="tooltip"
            className="pointer-events-none absolute -translate-x-1/2 rounded-md border bg-popover px-2 py-1 text-xs shadow-sm"
            style={{ left: `${(hover + 0.5) * slot}%`, top: -8 }}
          >
            <span className="text-muted-foreground">{formatDay(active.day)}</span>{" "}
            <strong className="font-semibold">{active.questions}</strong> preguntas
          </div>
        )}
      </div>
      <figcaption className="sr-only">Preguntas por día</figcaption>
      <table className="sr-only">
        <thead>
          <tr>
            <th>Día</th>
            <th>Preguntas</th>
          </tr>
        </thead>
        <tbody>
          {points.map((p) => (
            <tr key={p.day}>
              <td>{p.day}</td>
              <td>{p.questions}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
