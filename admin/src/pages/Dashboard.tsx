import { api, fmtSum } from "../api";
import { Err, Loading, Page, useLoad } from "../ui";

interface Dash {
  users: number; new_users_today: number; active_subscribers: number; pending_payments: number;
  answers_today: number; answers_total: number; revenue_month: number; questions: number; ai_tokens_today: number;
}

export default function Dashboard({ go }: { go: (p: string) => void }) {
  const { data, error } = useLoad(() => api<Dash>("/admin/dashboard"));
  if (error) return <Err msg={error} />;
  if (!data) return <Loading />;
  const tiles: [string, string | number, string?][] = [
    ["Pending payments", data.pending_payments, "payments"],
    ["Active subscribers", data.active_subscribers, "users"],
    ["Revenue this month", `${fmtSum(data.revenue_month)} UZS`],
    ["Users", `${data.users} (+${data.new_users_today} today)`, "users"],
    ["Answers today", data.answers_today, "attempts"],
    ["Answers total", data.answers_total, "attempts"],
    ["Active questions", data.questions, "content"],
    ["AI tokens today", data.ai_tokens_today],
  ];
  return (
    <Page title="Dashboard">
      <div className="tiles">
        {tiles.map(([label, value, link]) => (
          <button key={label} className={`tile ${link ? "link" : ""} ${label === "Pending payments" && data.pending_payments ? "hot" : ""}`}
            onClick={() => link && go(link)}>
            <div className="tile-value">{value}</div>
            <div className="tile-label">{label}</div>
          </button>
        ))}
      </div>
    </Page>
  );
}
