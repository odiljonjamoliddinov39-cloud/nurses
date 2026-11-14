import { useEffect, useState } from "react";
import { api, type Me, type Payment } from "../api";
import { fmtDate, fmtSum, type Lang, useT } from "../i18n";
import { Section } from "../ui";

const LANGS: { code: Lang; label: string }[] = [
  { code: "uz", label: "O'zbekcha" }, { code: "ru", label: "Русский" }, { code: "en", label: "English" },
];

export default function Profile({ me, onLang, onPaywall }: { me: Me; onLang: (l: Lang) => void; onPaywall: () => void }) {
  const t = useT();
  const [payments, setPayments] = useState<Payment[]>([]);
  useEffect(() => { api<Payment[]>("/payments").then(setPayments).catch(() => undefined); }, []);
  const reason = (r: string | null) => (r && ["amount", "unreadable", "notfound", "other"].includes(r) ? t(`r_${r}` as "r_other") : r ?? "");

  return (
    <div>
      <div className="card">
        <h2>{me.full_name}</h2>
        {me.phone && <p className="muted">{t("phone")}: {me.phone}</p>}
      </div>

      <Section title={t("subscription")}>
        <div className="card">
          <p><span className={`badge st-${me.status}`}>{t(`status_${me.status}` as "status_guest")}</span></p>
          {me.subscription
            ? <p>{me.subscription.plan ?? ""} · {t("until", { d: fmtDate(me.subscription.ends_at) })}</p>
            : <p className="muted">{t("no_subscription")}</p>}
          {me.status !== "pending" && me.status !== "blocked" && (
            <button className="btn" onClick={onPaywall}>{me.subscription ? t("renew") : t("subscribe")}</button>
          )}
          {me.status === "pending" && <p className="muted small">{t("pending_exists")}</p>}
        </div>
      </Section>

      <Section title={t("language")}>
        <div className="chips-row">
          {LANGS.map((l) => (
            <button key={l.code} className={`chip-btn ${me.ui_language === l.code ? "active" : ""}`} onClick={() => onLang(l.code)}>
              {l.label}
            </button>
          ))}
        </div>
      </Section>

      {payments.length > 0 && (
        <Section title={t("payments")}>
          <ul className="plain">
            {payments.map((p) => (
              <li key={p.id} className="card row">
                <div>
                  <b>{p.plan}</b> · {fmtSum(p.amount)} {t("sum")}
                  <div className="muted small">{fmtDate(p.created_at)} · {p.code}</div>
                  {p.status === "rejected" && <div className="error-text small">{reason(p.reject_reason)}</div>}
                </div>
                <span className={`badge pay-${p.status}`}>{t(`st_${p.status}` as "st_pending")}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {me.support_contact && (
        <Section title={t("support")}>
          <div className="card"><SupportLink contact={me.support_contact} /></div>
        </Section>
      )}
    </div>
  );
}

export function SupportLink({ contact }: { contact: string }) {
  const href = contact.startsWith("@") ? `https://t.me/${contact.slice(1)}` : contact.startsWith("http") ? contact : null;
  if (!href) return <span>{contact}</span>;
  return (
    <a href={href} onClick={(e) => {
      const w = window.Telegram?.WebApp;
      if (w?.openTelegramLink && href.startsWith("https://t.me/")) { e.preventDefault(); w.openTelegramLink(href); }
    }}>{contact}</a>
  );
}
