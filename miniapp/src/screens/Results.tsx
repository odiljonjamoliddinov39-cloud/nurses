import { useEffect, useState } from "react";
import { api } from "../api";
import { fmtDate, useT } from "../i18n";
import { ErrorBox, ScoreChip, Spinner } from "../ui";
import StatsCard from "./Stats";

interface Res {
  stats: { answered_questions: number; average: number | null; attempts: number };
  items: { id: number; state: string; created_at: string; number: number; text: string; score: number | null }[];
}

export default function Results({ onOpen }: { onOpen: (attemptId: number) => void }) {
  const t = useT();
  const [data, setData] = useState<Res | null>(null);
  const [error, setError] = useState("");
  const load = () => { setError(""); api<Res>("/attempts?limit=100").then(setData).catch((e) => setError(e.message)); };
  useEffect(load, []);
  if (error) return <ErrorBox error={error} onRetry={load} />;
  if (!data) return <Spinner />;
  return (
    <div>
      <StatsCard />
      {data.items.length > 0 && <div className="section-title"><span>{t("attempts")}</span><span>{data.stats.attempts}</span></div>}
      {data.items.length === 0 && <div className="card muted">{t("results_empty")}</div>}
      <ul className="qlist">
        {data.items.map((it) => (
          <li key={it.id}>
            <button className="qitem" onClick={() => onOpen(it.id)}>
              <span className="qnum">{it.number}</span>
              <span className="qtext">{it.text}<span className="muted small block">{fmtDate(it.created_at)}{it.state !== "graded" ? ` · ${t("not_graded")}` : ""}</span></span>
              <ScoreChip score={it.score} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
