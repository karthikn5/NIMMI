"use client";

import { useEffect, useRef, useState } from "react";

type Point = { date: string; count: number };

const HEIGHT = 180;
const PAD = { top: 12, right: 4, bottom: 24, left: 28 };
const MAX_BAR = 24;
const RADIUS = 4;

function niceMax(max: number) {
    if (max <= 5) return 5;
    const step = max <= 20 ? 5 : max <= 50 ? 10 : Math.pow(10, Math.floor(Math.log10(max)));
    return Math.ceil(max / step) * step;
}

/** Column with a rounded data-end and a square baseline. */
function barPath(x: number, y: number, w: number, h: number) {
    const r = Math.min(RADIUS, h, w / 2);
    return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

export default function DailyChart({ data, unit = "call", partialLast = true }: {
    data: Point[];
    unit?: string;          // singular noun for tooltips, e.g. "conversation"
    partialLast?: boolean;  // the last bar is today, still counting
}) {
    const wrap = useRef<HTMLDivElement>(null);
    const [width, setWidth] = useState(0);
    const [active, setActive] = useState<number | null>(null);

    useEffect(() => {
        if (!wrap.current) return;
        const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
        ro.observe(wrap.current);
        return () => ro.disconnect();
    }, []);

    const max = niceMax(Math.max(...data.map((d) => d.count), 1));
    const ticks = [0, max / 2, max];
    const plotW = Math.max(width - PAD.left - PAD.right, 0);
    const plotH = HEIGHT - PAD.top - PAD.bottom;
    const slot = data.length ? plotW / data.length : 0;
    const barW = Math.min(MAX_BAR, Math.max(slot - 2, 2));
    const y = (v: number) => PAD.top + plotH - (v / max) * plotH;
    const lastIndex = data.length - 1;

    const label = (d: Point, i: number) => {
        const date = new Date(d.date).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
        return `${date}: ${d.count} ${unit}${d.count === 1 ? "" : "s"}${partialLast && i === lastIndex ? " so far" : ""}`;
    };

    return (
        <div ref={wrap} className="relative w-full" style={{ height: HEIGHT }}>
            {width > 0 && (
                <svg width={width} height={HEIGHT} role="img" aria-label={`${unit}s per day`} className="block">
                    {ticks.map((t) => (
                        <g key={t}>
                            <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} stroke="#ece9e4" strokeWidth={1} />
                            <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-stone-400 text-[11px] tabular-nums">{t}</text>
                        </g>
                    ))}

                    {data.map((d, i) => {
                        const cx = PAD.left + slot * i + slot / 2;
                        const h = Math.max((d.count / max) * plotH, d.count > 0 ? 2 : 0);
                        const isToday = partialLast && i === lastIndex;
                        const dim = active !== null && active !== i;
                        return (
                            <g key={d.date}>
                                {h > 0 && (
                                    <path
                                        d={barPath(cx - barW / 2, y(d.count), barW, h)}
                                        className="fill-plum-data transition-opacity"
                                        opacity={isToday ? 0.45 : dim ? 0.55 : 1}
                                    />
                                )}
                                {(data.length <= 31 || i % Math.ceil(data.length / 15) === 0) && (
                                    <text x={cx} y={HEIGHT - 6} textAnchor="middle" className="fill-stone-400 text-[11px] tabular-nums">
                                        {new Date(d.date).getDate()}
                                    </text>
                                )}
                                {/* Hit target spans the whole slot, larger than the bar. */}
                                <rect
                                    x={PAD.left + slot * i}
                                    y={PAD.top}
                                    width={slot}
                                    height={plotH}
                                    fill="transparent"
                                    tabIndex={0}
                                    aria-label={label(d, i)}
                                    onMouseEnter={() => setActive(i)}
                                    onMouseLeave={() => setActive(null)}
                                    onFocus={() => setActive(i)}
                                    onBlur={() => setActive(null)}
                                    className="outline-none cursor-default"
                                />
                            </g>
                        );
                    })}
                </svg>
            )}

            {active !== null && width > 0 && (
                <div
                    className="absolute pointer-events-none -translate-x-1/2 -translate-y-full px-2.5 py-1.5 rounded-md bg-ink text-white text-xs whitespace-nowrap shadow-md"
                    style={{
                        left: Math.min(Math.max(PAD.left + slot * active + slot / 2, 70), width - 70),
                        top: y(data[active].count) - 8,
                    }}
                >
                    {label(data[active], active)}
                </div>
            )}

            <table className="sr-only">
                <caption>{unit}s per day</caption>
                <thead><tr><th>Date</th><th>Count</th></tr></thead>
                <tbody>
                    {data.map((d) => (
                        <tr key={d.date}><td>{new Date(d.date).toDateString()}</td><td>{d.count}</td></tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
