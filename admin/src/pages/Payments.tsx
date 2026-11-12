import { useState } from "react";
import { api, fmtDate, fmtSum, post } from "../api";
import { AuthImage, Badge, Err, Loading, Modal, Page, useLoad } from "../ui";

interface Pay {
  id: number; code: string; amount: number; status: string; plan: string; receipt: number | null;
  reject_reason: string | null; created_at: string; reviewed_at: string | null;
  user: { id: number; name: string | null; phone: string | null; telegram_id: number };
}

const REASONS = [["amount", "Wrong amount"], ["unreadable", "Receipt unreadable"], ["notfound", "Payment not found"], ["other", "Other"]];

export default function Payments() {
  const [status, setStatus] = useState("pending");
  const { data, error, reload } = useLoad(() => api<Pay[]>(`/admin/payments?status=${status}`), [status]);
  const [open, setOpen] = useState<Pay | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setMsg("");
    try { await fn(); setOpen(null); reload(); } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <Page title="Payment requests" actions={
      <select value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="pending">Pending</option><option value="approved">Approved</option>
        <option value="rejected">Rejected</option><option value="all">All</option>
      </select>}>
      <Err msg={error} />
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">No {status === "all" ? "" : status} requests.</div> : (
        <table>
          <thead><tr><th>Code</th><th>User</th><th>Plan</th><th>Amount</th><th>Sent</th><th>Status</th><th /></tr></thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id} className="clickable" onClick={() => setOpen(p)}>
                <td><b>{p.code}</b></td>
                <td>{p.user.name ?? "—"}<div className="muted small">{p.user.phone ?? p.user.telegram_id}</div></td>
                <td>{p.plan}</td><td>{fmtSum(p.amount)}</td><td>{fmtDate(p.created_at)}</td>
                <td><Badge value={p.status} /></td>
                <td><button className="btn small">Open</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {open && (
        <Modal title={`Payment ${open.code}`} onClose={() => setOpen(null)} wide>
          <div className="split">
            <div>
              <dl className="kv">
                <dt>User</dt><dd>{open.user.name ?? "—"}</dd>
                <dt>Phone</dt><dd>{open.user.phone ?? "—"}</dd>
                <dt>Telegram ID</dt><dd>{open.user.telegram_id}</dd>
                <dt>Plan</dt><dd>{open.plan}</dd>
                <dt>Amount</dt><dd><b>{fmtSum(open.amount)} UZS</b></dd>
                <dt>Sent</dt><dd>{fmtDate(open.created_at)}</dd>
                <dt>Status</dt><dd><Badge value={open.status} />{open.reject_reason ? ` · ${open.reject_reason}` : ""}</dd>
              </dl>
              {open.status === "pending" && (
                <div className="stack">
                  <button className="btn good" disabled={busy} onClick={() => act(() => post(`/admin/payments/${open.id}/approve`))}>
                    ✓ Approve and open access
                  </button>
                  <div className="muted small">Reject with reason:</div>
                  <div className="row gap wrap">
                    {REASONS.map(([code, label]) => (
                      <button key={code} className="btn danger small" disabled={busy}
                        onClick={() => act(() => post(`/admin/payments/${open.id}/reject`, { reason: code }))}>{label}</button>
                    ))}
                  </div>
                  <Err msg={msg} />
                  <p className="muted small">The user gets a message in the bot either way.</p>
                </div>
              )}
            </div>
            <div>{open.receipt ? <AuthImage id={open.receipt} /> : <div className="muted">No receipt</div>}</div>
          </div>
        </Modal>
      )}
    </Page>
  );
}
