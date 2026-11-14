import { t } from "../i18n";
import { useState } from "react";
import { api, download, fmtSum } from "../api";
import { Err, Loading, Page, Score, useLoad } from "../ui";

interface Report {
  days: number;
  totals: { revenue: number; payments: number; average_payment: number; answers: number };
  revenue_by_day: { date: string; amount: number; count: number }[];
  by_plan: { plan: string; amount: number; count: number }[];
  new_vs_renewed: { new: { count: number; amount: number }; renewed: { count: number; amount: number } };
  conversion: { new_users: number; paying: number; rate: number };
  hardest_questions: { number: number; text: string; average: number; attempts: number }[];
}

const PERIODS = [7, 30, 90, 365];

export default function Reports() {
  const [days, setDays] = useState(30);
  const { data, error } = useLoad(() => api<Report>(`/admin/reports?days=${days}`), [days]);
  const [msg, setMsg] = useState("");

  const exportXlsx = async () => {
    setMsg("");
    try { await download(`/admin/reports/export?days=${days}`, `report-${days}d.xlsx`); } catch (e) { setMsg((e as Error).message); }
  };

  const max = Math.max(1, ...(data?.revenue_by_day.map((d) => d.amount) ?? [0]));
  return (
    <Page title={t("Reports")} actions={
      <>
        <select value={days} onChange={(e) => setDays(+e.target.value)}>
          {PERIODS.map((p) => <option key={p} value={p}>{t("Last {n} days", { n: p })}</option>)}
        </select>
        <button className="btn secondary" onClick={exportXlsx}>{t("Export Excel")}</button>
      </>
    }>
      <Err msg={error || msg} />
      {!data ? <Loading /> : (
        <>
          <div className="tiles">
            <div className="tile"><div className="tile-value">{fmtSum(data.totals.revenue)}</div><div className="tile-label">{t("Revenue, UZS")}</div></div>
            <div className="tile"><div className="tile-value">{data.totals.payments}</div><div className="tile-label">{t("Approved payments")}</div></div>
            <div className="tile"><div className="tile-value">{fmtSum(data.totals.average_payment)}</div><div className="tile-label">{t("Average payment, UZS")}</div></div>
            <div className="tile"><div className="tile-value">{data.totals.answers}</div><div className="tile-label">{t("Answers recorded")}</div></div>
            <div className="tile"><div className="tile-value">{data.new_vs_renewed.new.count} / {data.new_vs_renewed.renewed.count}</div><div className="tile-label">{t("New / renewed")}</div></div>
            <div className="tile"><div className="tile-value">{t("{a} of {b}", { a: data.conversion.paying, b: data.conversion.new_users })}</div>
              <div className="tile-label">{t("New users who paid")} ({Math.round(data.conversion.rate * 100)}%)</div></div>
          </div>

          <h3>{t("Revenue by day")}</h3>
          <div className="card">
            <div className="bars" data-testid="revenue-bars">
              {data.revenue_by_day.map((d) => (
                <div key={d.date} className="bar-col" title={`${d.date}: ${fmtSum(d.amount)} UZS, ${d.count} ${t("payments")}`}>
                  <i style={{ height: d.amount ? `${Math.max(4, (d.amount / max) * 100)}%` : "2px" }} className={d.amount ? "" : "zero"} />
                </div>
              ))}
            </div>
            <div className="row between muted small"><span>{data.revenue_by_day[0]?.date}</span><span>{data.revenue_by_day[data.revenue_by_day.length - 1]?.date}</span></div>
          </div>

          <div className="row gap wrap top">
            <div style={{ flex: 1, minWidth: 320 }}>
              <h3>{t("By plan")}</h3>
              {data.by_plan.length === 0 ? <div className="empty">{t("No payments in this period.")}</div> : (
                <table>
                  <thead><tr><th>{t("Plan")}</th><th>{t("Payments")}</th><th>{t("Revenue, UZS")}</th></tr></thead>
                  <tbody>{data.by_plan.map((p) => <tr key={p.plan}><td>{p.plan}</td><td>{p.count}</td><td>{fmtSum(p.amount)}</td></tr>)}</tbody>
                </table>
              )}
            </div>
            <div style={{ flex: 1, minWidth: 320 }}>
              <h3>{t("Hardest questions")}</h3>
              {data.hardest_questions.length === 0 ? <div className="empty">{t("Needs at least 3 graded answers per question.")}</div> : (
                <table>
                  <thead><tr><th>#</th><th>{t("Question")}</th><th>{t("Avg")}</th><th>{t("Answers")}</th></tr></thead>
                  <tbody>{data.hardest_questions.map((q) => (
                    <tr key={q.number}><td>{q.number}</td><td className="clip">{q.text}</td><td><Score v={q.average} /></td><td>{q.attempts}</td></tr>
                  ))}</tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
    </Page>
  );
}
