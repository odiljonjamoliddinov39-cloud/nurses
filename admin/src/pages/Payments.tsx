import { t } from "../i18n";
import { useState } from "react";
import { api, fmtDate, fmtSum, post } from "../api";
import { AuthImage, Badge, Err, Loading, Modal, Page, useLoad } from "../ui";

interface Pay {
  id: number; code: string; amount: number; status: string; plan: string; receipt: number | null;
  reject_reason: string | null; created_at: string; reviewed_at: string | null; promo: string | null; discount: number;
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
    <Page title={t("Payment requests")} actions={
      <select value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="pending">{t("Pending")}</option><option value="approved">{t("Approved")}</option>
        <option value="rejected">{t("Rejected")}</option><option value="all">{t("All")}</option>
      </select>}>
      <Err msg={error} />
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">{status === "all" ? t("No requests.") : t("No {status} requests.", { status: t(status) })}</div> : (
        <table>
          <thead><tr><th>{t("Code")}</th><th>{t("User")}</th><th>{t("Plan")}</th><th>{t("Amount")}</th><th>{t("Sent")}</th><th>{t("Status")}</th><th /></tr></thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id} className="clickable" onClick={() => setOpen(p)}>
                <td><b>{p.code}</b></td>
                <td>{p.user.name ?? "—"}<div className="muted small">{p.user.phone ?? p.user.telegram_id}</div></td>
                <td>{p.plan}</td><td>{fmtSum(p.amount)}{p.promo && <div className="muted small">🏷 {p.promo} −{fmtSum(p.discount)}</div>}</td><td>{fmtDate(p.created_at)}</td>
                <td><Badge value={p.status} /></td>
                <td><button className="btn small">{t("Open")}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {open && (
        <Modal title={t("Payment {code}", { code: open.code })} onClose={() => setOpen(null)} wide>
          <div className="split">
            <div>
              <dl className="kv">
                <dt>{t("User")}</dt><dd>{open.user.name ?? "—"}</dd>
                <dt>{t("Phone")}</dt><dd>{open.user.phone ?? "—"}</dd>
                <dt>{t("Telegram ID")}</dt><dd>{open.user.telegram_id}</dd>
                <dt>{t("Plan")}</dt><dd>{open.plan}</dd>
                <dt>{t("Amount")}</dt><dd><b>{fmtSum(open.amount)} UZS</b>{open.promo && <div className="muted small">{t("Promo {code}: −{amount} UZS taken off the plan price. Check the receipt against this amount.", { code: open.promo, amount: fmtSum(open.discount) })}</div>}</dd>
                <dt>{t("Sent")}</dt><dd>{fmtDate(open.created_at)}</dd>
                <dt>{t("Status")}</dt><dd><Badge value={open.status} />{open.reject_reason ? ` · ${t(open.reject_reason)}` : ""}</dd>
              </dl>
              {open.status === "pending" && (
                <div className="stack">
                  <button className="btn good" disabled={busy} onClick={() => act(() => post(`/admin/payments/${open.id}/approve`))}>
                    ✓ Approve and open access
                  </button>
                  <div className="muted small">{t("Reject with reason:")}</div>
                  <div className="row gap wrap">
                    {REASONS.map(([code, label]) => (
                      <button key={code} className="btn danger small" disabled={busy}
                        onClick={() => act(() => post(`/admin/payments/${open.id}/reject`, { reason: code }))}>{t(label)}</button>
                    ))}
                  </div>
                  <Err msg={msg} />
                  <p className="muted small">{t("The user gets a message in the bot either way.")}</p>
                </div>
              )}
            </div>
            <div>{open.receipt ? <AuthImage id={open.receipt} /> : <div className="muted">{t("No receipt")}</div>}</div>
          </div>
        </Modal>
      )}
    </Page>
  );
}
