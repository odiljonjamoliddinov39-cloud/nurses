import { useState } from "react";
import { api, fmtDate, fmtDay, post } from "../api";
import { Badge, Err, Loading, Modal, Page, Score, useLoad } from "../ui";

interface Row { id: number; telegram_id: number; name: string | null; phone: string | null; status: string;
  ends_at: string | null; created_at: string; last_seen: string | null }
interface Detail {
  id: number; telegram_id: number; name: string | null; phone: string | null; status: string; blocked: boolean;
  created_at: string; last_seen: string | null; ui_language: string;
  subscriptions: { id: number; plan: string | null; starts_at: string; ends_at: string; source: string; status: string }[];
  attempts: { id: number; number: number; score: number | null; state: string; created_at: string }[];
}
interface PlanLite { id: number; name: string; days: number }

export default function Users() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState({ q: "", status: "" });
  const { data, error, reload } = useLoad(
    () => api<Row[]>(`/admin/users?q=${encodeURIComponent(query.q)}&status=${query.status}`), [query]);
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <Page title="Users" actions={
      <form className="row gap" onSubmit={(e) => { e.preventDefault(); setQuery({ q, status }); }}>
        <input placeholder="Name, phone or Telegram ID" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setQuery({ q, status: e.target.value }); }}>
          <option value="">All</option><option value="subscriber">Subscribers</option><option value="pending">Pending</option>
          <option value="guest">Guests</option><option value="expired">Expired</option><option value="blocked">Blocked</option>
        </select>
        <button className="btn">Search</button>
      </form>}>
      <Err msg={error} />
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">No users.</div> : (
        <table>
          <thead><tr><th>Name</th><th>Phone</th><th>Telegram ID</th><th>Status</th><th>Access until</th><th>Joined</th><th>Last seen</th></tr></thead>
          <tbody>
            {data.map((u) => (
              <tr key={u.id} className="clickable" onClick={() => setOpenId(u.id)}>
                <td>{u.name ?? "—"}</td><td>{u.phone ?? "—"}</td><td>{u.telegram_id}</td>
                <td><Badge value={u.status} /></td><td>{fmtDay(u.ends_at)}</td>
                <td>{fmtDay(u.created_at)}</td><td>{fmtDate(u.last_seen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {openId && <UserModal id={openId} onClose={() => { setOpenId(null); reload(); }} />}
    </Page>
  );
}

function UserModal({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, error, reload } = useLoad(() => api<Detail>(`/admin/users/${id}`), [id]);
  const plans = useLoad(() => api<PlanLite[]>("/admin/plans"));
  const [days, setDays] = useState(30);
  const [planId, setPlanId] = useState("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  const act = async (fn: () => Promise<unknown>) => {
    setMsg("");
    try { await fn(); reload(); } catch (e) { setMsg((e as Error).message); }
  };
  return (
    <Modal title={data?.name ?? "User"} onClose={onClose} wide>
      <Err msg={error} />
      {!data ? <Loading /> : (
        <div className="split">
          <div>
            <dl className="kv">
              <dt>Status</dt><dd><Badge value={data.status} /></dd>
              <dt>Phone</dt><dd>{data.phone ?? "—"}</dd>
              <dt>Telegram ID</dt><dd>{data.telegram_id}</dd>
              <dt>Language</dt><dd>{data.ui_language}</dd>
              <dt>Joined</dt><dd>{fmtDate(data.created_at)}</dd>
              <dt>Last seen</dt><dd>{fmtDate(data.last_seen)}</dd>
            </dl>
            <h3>Give or extend access</h3>
            <div className="row gap wrap">
              <label>Days <input type="number" min={1} value={days} onChange={(e) => setDays(+e.target.value)} style={{ width: 80 }} /></label>
              <select value={planId} onChange={(e) => setPlanId(e.target.value)}>
                <option value="">All courses</option>
                {plans.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <input placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
              <button className="btn good" onClick={() => act(() => post(`/admin/users/${id}/grant`,
                { days, plan_id: planId ? +planId : null, reason }))}>Grant</button>
            </div>
            <div className="row gap" style={{ marginTop: 16 }}>
              {data.blocked
                ? <button className="btn" onClick={() => act(() => post(`/admin/users/${id}/block`, { blocked: false }))}>Unblock</button>
                : <button className="btn danger" onClick={() => confirm("Block this user?") && act(() => post(`/admin/users/${id}/block`, { blocked: true }))}>Block</button>}
            </div>
            <Err msg={msg} />
          </div>
          <div>
            <h3>Subscriptions</h3>
            {data.subscriptions.length === 0 ? <div className="muted">None</div> : (
              <table className="compact"><tbody>
                {data.subscriptions.map((s) => (
                  <tr key={s.id}>
                    <td>{s.plan ?? "Gift"}<div className="muted small">{s.source}</div></td>
                    <td>{fmtDay(s.starts_at)} – {fmtDay(s.ends_at)}</td>
                    <td><Badge value={s.status} /></td>
                    <td>{s.status === "active" && <button className="btn small danger"
                      onClick={() => confirm("Cancel this subscription?") && act(() => post(`/admin/subscriptions/${s.id}/cancel`))}>Cancel</button>}</td>
                  </tr>
                ))}
              </tbody></table>
            )}
            <h3>Recent answers</h3>
            {data.attempts.length === 0 ? <div className="muted">None</div> : (
              <table className="compact"><tbody>
                {data.attempts.map((a) => (
                  <tr key={a.id}><td>Q{a.number}</td><td><Score v={a.score} /></td><td className="muted small">{fmtDate(a.created_at)}</td></tr>
                ))}
              </tbody></table>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
