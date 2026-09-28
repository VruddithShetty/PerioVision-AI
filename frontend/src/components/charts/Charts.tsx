import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { STAGE_COLOR } from "@/lib/format";

const AXIS = { stroke: "#5b6f8c", fontSize: 11, tickLine: false, axisLine: false } as const;
const TIP = {
  contentStyle: { background: "#0a1628", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 12, fontSize: 12 },
  labelStyle: { color: "#a9bcd6" },
  itemStyle: { color: "#e6f1ff" },
  cursor: { fill: "rgba(34,211,238,0.06)" },
};
const PALETTE = ["#22d3ee", "#2dd4bf", "#fbbf24", "#fb923c", "#ef4444", "#a78bfa", "#60a5fa", "#f472b6"];

export function StageBars({ data }: { data: Record<string, number> }) {
  const rows = ["I", "II", "III", "IV"].map((s) => ({ stage: `Stage ${s}`, key: s, count: data[s] ?? 0 }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="stage" {...AXIS} />
        <YAxis allowDecimals={false} {...AXIS} />
        <Tooltip {...TIP} />
        <Bar dataKey="count" radius={[8, 8, 0, 0]} name="Analyses">
          {rows.map((r) => (
            <Cell key={r.key} fill={STAGE_COLOR[r.key]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function RiskDonut({ data }: { data: Record<string, number> }) {
  const colors: Record<string, string> = { low: "#2dd4bf", moderate: "#fbbf24", high: "#ef4444" };
  const rows = Object.entries(data).map(([k, v]) => ({ name: k, value: v }));
  const total = rows.reduce((a, r) => a + r.value, 0);
  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie data={rows} dataKey="value" nameKey="name" innerRadius={62} outerRadius={88} paddingAngle={3} stroke="none">
            {rows.map((r) => (
              <Cell key={r.name} fill={colors[r.name] ?? "#7f93b0"} />
            ))}
          </Pie>
          <Tooltip {...TIP} />
          <Legend iconType="circle" wrapperStyle={{ fontSize: 12, color: "#a9bcd6" }} />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-x-0 top-[74px] text-center">
        <p className="font-display text-3xl font-bold">{total}</p>
        <p className="text-[11px] text-mist-500">scored visits</p>
      </div>
    </div>
  );
}

export function ToothTrendChart({ series, highlight }: {
  series: Record<string, { date: string; bone_loss_pct: number }[]>;
  highlight?: string | null;
}) {
  const teeth = Object.keys(series);
  const dates = Array.from(new Set(teeth.flatMap((t) => series[t]!.map((p) => p.date)))).sort();
  const rows = dates.map((d) => {
    const row: Record<string, number | string> = { date: d };
    teeth.forEach((t) => {
      const p = series[t]!.find((x) => x.date === d);
      if (p) row[t] = p.bone_loss_pct;
    });
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={rows} margin={{ top: 10, right: 16, left: -10, bottom: 0 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.05)" />
        <XAxis dataKey="date" {...AXIS} />
        <YAxis unit="%" domain={[0, "dataMax + 10"]} {...AXIS} />
        <ReferenceLine y={15} stroke="#fbbf24" strokeDasharray="4 4" label={{ value: "Stage II", fill: "#fbbf24", fontSize: 10, position: "right" }} />
        <ReferenceLine y={33} stroke="#fb923c" strokeDasharray="4 4" label={{ value: "Stage III", fill: "#fb923c", fontSize: 10, position: "right" }} />
        <Tooltip {...TIP} />
        {teeth.map((t, i) => (
          <Line
            key={t}
            type="monotone"
            dataKey={t}
            name={`Tooth ${t}`}
            stroke={PALETTE[i % PALETTE.length]}
            strokeWidth={highlight === t ? 3.5 : highlight ? 1 : 2}
            strokeOpacity={highlight && highlight !== t ? 0.35 : 1}
            dot={{ r: 3 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function CalibrationPlot({ bins }: { bins: { mean_predicted: number; mean_reference: number; n: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ScatterChart margin={{ top: 10, right: 16, left: -10, bottom: 10 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.05)" />
        <XAxis type="number" dataKey="mean_predicted" name="Predicted" unit="%" domain={[0, 100]} {...AXIS} />
        <YAxis type="number" dataKey="mean_reference" name="Reference" unit="%" domain={[0, 100]} {...AXIS} />
        <ZAxis type="number" dataKey="n" range={[60, 400]} name="Teeth" />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 100, y: 100 }]} stroke="#5b6f8c" strokeDasharray="4 4" />
        <Tooltip {...TIP} />
        <Scatter data={bins} fill="#22d3ee" />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function ReasonBars({ data, labels }: { data: Record<string, number>; labels: Record<string, string> }) {
  const rows = Object.entries(data)
    .map(([k, v]) => ({ name: labels[k] ?? k, v }))
    .sort((a, b) => b.v - a.v);
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, rows.length * 36)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 16, left: 40, bottom: 0 }}>
        <XAxis type="number" allowDecimals={false} {...AXIS} />
        <YAxis type="category" dataKey="name" width={150} {...AXIS} />
        <Tooltip {...TIP} />
        <Bar dataKey="v" name="Cases" fill="#fbbf24" radius={[0, 8, 8, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Semicircular gauge for the risk score. */
export function RiskGauge({ value, category }: { value: number; category: string }) {
  const color = { low: "#2dd4bf", moderate: "#fbbf24", high: "#ef4444" }[category] ?? "#7f93b0";
  const angle = Math.PI * (1 - Math.min(Math.max(value, 0), 1));
  const x = 100 + 78 * Math.cos(angle);
  const y = 100 - 78 * Math.sin(angle);
  return (
    <svg viewBox="0 0 200 120" className="w-full max-w-[240px]" role="img" aria-label={`Risk ${category}, score ${value.toFixed(2)}`}>
      <defs>
        <linearGradient id="gauge-g" x1="0" x2="1">
          <stop offset="0" stopColor="#2dd4bf" />
          <stop offset="0.5" stopColor="#fbbf24" />
          <stop offset="1" stopColor="#ef4444" />
        </linearGradient>
      </defs>
      <path d="M22 100 A78 78 0 0 1 178 100" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="14" strokeLinecap="round" />
      <path d="M22 100 A78 78 0 0 1 178 100" fill="none" stroke="url(#gauge-g)" strokeWidth="14" strokeLinecap="round" opacity="0.85" />
      <line x1="100" y1="100" x2={x} y2={y} stroke="#e6f1ff" strokeWidth="3" strokeLinecap="round" />
      <circle cx="100" cy="100" r="6" fill="#e6f1ff" />
      <text x="100" y="82" textAnchor="middle" fontSize="20" fontWeight="700" fill={color} fontFamily="Syne, sans-serif">
        {category.toUpperCase()}
      </text>
    </svg>
  );
}
