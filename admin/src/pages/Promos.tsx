import { t } from "../i18n";
import { useState } from "react";
import { api, del, fmtDay, fmtSum, post, put } from "../api";
import { Badge, Err, Loading, Modal, Page, useLoad } from "../ui";

interface Promo {
  id: number; code: string; kind: "percent" | "fixed"; value: number; max_uses: number | null; used_count: number;
  expires_at: string | null; is_active: boolean; expired: boolean;
}

const describe = (p: Promo) => (p.kind === "percent" ? `${p.value}%` : `${fmtSum(p.value)} UZS`);
const state = (p: Promo) => (!p.is_active ? "off" : p.expired ? "expired" : p.max_uses != null && p.used_count >= p.max_uses ? "used up" : "active");

export default function Promos() {
  const { data, error, reload } = useLoad(() => api<Promo[]>("/admin/promos"));
  const [edit, setEdit] = useState<Partial<Promo> | null>(null);
  const [msg, setMsg] = useState("");

  const remove = async (p: Promo) => {
    if (!confirm(t("Delete promo code {code}?", { code: p.code }))) return;
    try { await del(`/admin/promos/${p.id}`); reload(); } catch (e) { setMsg((e as Error).message); }
  };
  const toggle = async (p: Promo) => {
    try {
      await put(`/admin/promos/${p.id}`, { code: p.code, kind: p.kind, value: p.value, max_uses: p.max_uses, expires_at: p.expires_at, is_active: !p.is_active });
      reload();
    } catch (e) { setMsg((e as Error).message); }
  };

  return (
    <Page title={t("Promo codes")} actions={<button className="btn" onClick={() => setEdit({ kind: "percent", value: 10, is_active: true, used_count: 0 })}>{t("+ New promo code")}</button>}>
      <Err msg={error || msg} />
      <p className="muted small">{t("Users enter a code on the payment screen. The discount is taken off the plan price, so the payment request shows the reduced amount. A use is returned if the payment is rejected.")}</p>
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">{t("No promo codes yet.")}</div> : (
        <table>
          <thead><tr><th>{t("Code")}</th><th>{t("Discount")}</th><th>{t("Used")}</th><th>{t("Expires")}</th><th>{t("Status")}</th><th /></tr></thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id}>
                <td><b className="mono">{p.code}</b></td>
                <td>{describe(p)}</td>
                <td>{p.used_count}{p.max_uses != null ? ` / ${p.max_uses}` : " " + t("(no limit)")}</td>
                <td>{p.expires_at ? fmtDay(p.expires_at) : t("never")}</td>
                <td><Badge value={state(p)} /></td>
                <td className="row gap">
                  <button className="btn small secondary" onClick={() => setEdit(p)}>{t("Edit")}</button>
                  <button className="btn small secondary" onClick={() => toggle(p)}>{p.is_active ? t("Switch off") : t("Switch on")}</button>
                  {!p.used_count && <button className="btn small danger" onClick={() => remove(p)}>{t("Delete")}</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {edit && <PromoModal p={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </Page>
  );
}

function PromoModal({ p, onClose, onSaved }: { p: Partial<Promo>; onClose: () => void; onSaved: () => void }) {
  const used = (p.used_count ?? 0) > 0;
  const [code, setCode] = useState(p.code ?? "");
  const [kind, setKind] = useState<"percent" | "fixed">(p.kind ?? "percent");
  const [value, setValue] = useState(p.value ?? 10);
  const [max, setMax] = useState(p.max_uses != null ? String(p.max_uses) : "");
  const [expires, setExpires] = useState(p.expires_at ? p.expires_at.slice(0, 10) : "");
  const [active, setActive] = useState(p.is_active ?? true);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true); setMsg("");
    const body = {
      code: code.trim(), kind, value, is_active: active,
      max_uses: max.trim() ? parseInt(max, 10) : null,
      expires_at: expires ? new Date(`${expires}T23:59:59`).toISOString() : null,  // valid through the end of that day
    };
    try {
      if (p.id) await put(`/admin/promos/${p.id}`, body); else await post("/admin/promos", body);
      onSaved();
    } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <Modal title={p.id ? t("Promo code {code}", { code: p.code ?? "" }) : t("New promo code")} onClose={onClose}>
      <div className="form">
        <label>{t("Code *")}<input value={code} disabled={used} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="YOZ-20" maxLength={32} /></label>
        <div className="row gap">
          <label style={{ flex: 1 }}>{t("Type")}
            <select value={kind} disabled={used} onChange={(e) => setKind(e.target.value as "percent" | "fixed")}>
              <option value="percent">{t("Percent off")}</option><option value="fixed">{t("Fixed amount off (UZS)")}</option>
            </select>
          </label>
          <label style={{ flex: 1 }}>{kind === "percent" ? t("Percent (1–99)") : t("Amount, UZS")}
            <input type="number" min={1} max={kind === "percent" ? 99 : undefined} value={value} disabled={used} onChange={(e) => setValue(+e.target.value)} />
          </label>
        </div>
        {used && <p className="muted small">{t("Already used {n}×: the code, type and amount are locked. You can still change the limit, expiry and on/off.", { n: p.used_count ?? 0 })}</p>}
        <div className="row gap">
          <label style={{ flex: 1 }}>{t("Usage limit (empty = unlimited)")}<input type="number" min={Math.max(1, p.used_count ?? 1)} value={max} onChange={(e) => setMax(e.target.value)} /></label>
          <label style={{ flex: 1 }}>{t("Valid until (empty = no end)")}<input type="date" value={expires} onChange={(e) => setExpires(e.target.value)} /></label>
        </div>
        <label className="check"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> {t("Active")}</label>
        <Err msg={msg} />
        <div className="row gap"><button className="btn" onClick={save} disabled={busy || !code.trim() || !value}>{t("Save")}</button></div>
      </div>
    </Modal>
  );
}
