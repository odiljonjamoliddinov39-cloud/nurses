import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Me, type Plan } from "../api";
import { fmtSum, pick, useLang, useT } from "../i18n";
import { ErrorBox, haptic, Section, Spinner } from "../ui";

interface PayInfo { card_number: string; card_holder: string; note: string }

function CopyRow({ label, value }: { label: string; value: string }) {
  const t = useT();
  const [done, setDone] = useState(false);
  const copy = async () => {
    try { await navigator.clipboard.writeText(value.replace(/\s/g, "")); } catch {
      const ta = document.createElement("textarea");
      ta.value = value; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
    }
    setDone(true); haptic("light");
    window.setTimeout(() => setDone(false), 1500);
  };
  return (
    <div className="copy-row">
      <div><div className="muted small">{label}</div><b className="mono">{value}</b></div>
      <button className="btn small secondary" onClick={copy}>{done ? t("copied") : t("copy")}</button>
    </div>
  );
}

export default function Paywall({ me, onDone }: { me: Me; onDone: () => void }) {
  const t = useT();
  const lang = useLang();
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [info, setInfo] = useState<PayInfo | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = () => {
    setError("");
    Promise.all([api<Plan[]>("/plans"), api<PayInfo>("/payment-info")])
      .then(([p, i]) => { setPlans(p); setInfo(i); if (p.length === 1) setPlan(p[0]); })
      .catch((e) => setError(e.message));
  };
  useEffect(load, []);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const pickFile = (f: File | null) => {
    setFile(f);
    setPreview(f && f.type.startsWith("image/") ? URL.createObjectURL(f) : null);
  };

  const send = async () => {
    if (!plan || !file) return;
    setSending(true); setError("");
    const fd = new FormData();
    fd.append("plan_id", String(plan.id));
    fd.append("receipt", file);
    try {
      const r = await api<{ code: string }>("/payments", { method: "POST", body: fd });
      haptic("success");
      setSent(r.code);
    } catch (e) {
      haptic("error");
      setError(e instanceof ApiError && e.status === 409 ? t("pending_exists") : `${t("error")}: ${(e as Error).message}`);
    } finally {
      setSending(false);
    }
  };

  if (sent) {
    return (
      <div className="card center-text">
        <div className="big-emoji">✅</div>
        <p>{t("request_sent", { code: sent })}</p>
        <button className="btn" onClick={onDone}>{t("to_list")}</button>
      </div>
    );
  }
  if (me.status === "pending") return <div className="card">{t("pending_exists")}</div>;
  if (error && !plans) return <ErrorBox error={error} onRetry={load} />;
  if (!plans || !info) return <Spinner />;

  const rejected = me.last_payment?.status === "rejected" ? me.last_payment.reject_reason : null;

  return (
    <div>
      {rejected && <div className="card warn">{t("pay_rejected", { r: t(`r_${rejected}` as "r_other") })}</div>}
      <Section title={t("choose_plan")}>
        {plans.length === 0 && <div className="card muted">{t("no_plans")}</div>}
        <ul className="plain">
          {plans.map((p) => (
            <li key={p.id}>
              <button className={`plan ${plan?.id === p.id ? "active" : ""}`} onClick={() => setPlan(p)}>
                <div>
                  <b>{p.name}</b>
                  <div className="muted small">{p.days} {t("days")}{p.courses.length ? ` · ${p.courses.map((c) => pick(c, lang)).join(", ")}` : ""}</div>
                </div>
                <b>{fmtSum(p.price_uzs)} {t("sum")}</b>
              </button>
            </li>
          ))}
        </ul>
      </Section>

      {plan && (
        <>
          <div className="card">
            <p className="pre small">{t("pay_steps")}</p>
            {info.card_number ? (
              <>
                <CopyRow label={t("card")} value={info.card_number} />
                {info.card_holder && <p className="muted small">{t("holder")}: <b>{info.card_holder}</b></p>}
                <CopyRow label={t("amount")} value={String(plan.price_uzs)} />
                {info.note && <p className="pre small muted">{info.note}</p>}
              </>
            ) : <p className="error-text">{t("card_missing")}</p>}
          </div>
          <div className="card">
            <input ref={input} type="file" accept="image/*,application/pdf" hidden
              onChange={(e) => pickFile(e.target.files?.[0] ?? null)} />
            {preview && <img className="receipt" src={preview} alt="" />}
            {file && !preview && <p className="small">{file.name}</p>}
            <button className="btn secondary block" onClick={() => input.current?.click()}>
              📎 {file ? t("change_file") : t("upload_receipt")}
            </button>
          </div>
          {error && <p className="error-text center-text">{error}</p>}
          <div className="sticky-bottom">
            <button className="btn block" disabled={!file || sending || !info.card_number} onClick={send}>
              {sending ? t("sending") : t("i_paid")}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
