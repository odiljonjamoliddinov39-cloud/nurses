import { useEffect, useState } from "react";
import { api, type Stats } from "../api";
import { useT } from "../i18n";
import { ScoreChip, scoreClass, Section } from "../ui";

/** Progress overview: coverage, average, streak, 14-day trend, weakest topics. Hidden if it can't load. */
export default function StatsCard() {
  const t = useT();
  const [s, setS] = useState<Stats | null>(null);
  useEffect(() => { api<Stats>("/stats").then(setS).catch(() => setS(null)); }, []);
  if (!s) return null;
  if (s.answered === 0) return <div className="card muted center-text">{t("stats_empty")}</div>;
  const day = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
  return (
    <>
      <div className="card">
        <div className="stats">
          <div><b>{s.answered}/{s.total}</b><span>{t("answered")}</span></div>
          <div><b>{s.average ?? "—"}</b><span>{t("average")}</span></div>
          <div><b>{s.streak > 0 ? `🔥 ${s.streak}` : "—"}</b><span>{s.streak > 0 ? t("streak", { n: s.streak }) : t("streak", { n: 0 })}</span></div>
        </div>
        <div className="progress"><div style={{ width: `${s.total ? (s.answered / s.total) * 100 : 0}%` }} /></div>
      </div>
      <Section title={t("trend_title")}>
        <div className="card">
          <div className="trend">
            {s.trend.map((d) => (
              <div key={d.date} className="bar" title={`${day(d.date)}: ${d.avg ?? "—"}`}>
                <i className={`b-${scoreClass(d.avg)}`} style={{ height: d.avg == null ? "3px" : `${Math.max(6, (d.avg / 5) * 100)}%` }} />
              </div>
            ))}
          </div>
          <div className="trend-axis muted small"><span>{day(s.trend[0].date)}</span><span>{day(s.trend[s.trend.length - 1].date)}</span></div>
        </div>
      </Section>
      {s.weakest_topics.length > 0 && (
        <Section title={t("weakest_topics")}>
          <ul className="plain">
            {s.weakest_topics.map((w) => (
              <li key={w.topic} className="card row"><span>{w.topic}</span><ScoreChip score={w.avg} /></li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}
