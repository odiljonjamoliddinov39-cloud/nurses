import { t, tx } from "../i18n";
import { useEffect, useState } from "react";
import { api, post, put } from "../api";
import { Err, Loading, Page } from "../ui";

type S = Record<string, string | number>;

const FIELDS: { key: string; label: string; help?: string; type?: "number" | "textarea" | "select" | "password"; options?: [string, string][] }[] = [
  { key: "card_number", label: "Card number", help: "Shown to users on the payment screen." },
  { key: "card_holder", label: "Card holder name" },
  { key: "payment_note", label: "Payment instructions", type: "textarea", help: "Optional extra text under the card, e.g. which apps to pay with." },
  { key: "free_questions", label: "Free questions per course", type: "number", help: "Guests can answer this many questions before paying." },
  { key: "daily_cap", label: "Answers per user per day", type: "number" },
  { key: "max_answer_seconds", label: "Max answer length, seconds", type: "number" },
  { key: "grading_mode", label: "Grading", type: "select", options: [["self", "Self-check (no AI, free)"], ["ai", "AI grading with Google Gemini"]],
    help: "Self-check: after recording, the user sees the model answer and ticks the key points they covered. AI needs a Gemini API key below." },
  { key: "gemini_api_key", label: "Gemini API key", type: "password", help: "From aistudio.google.com → Get API key. Stored on the server only." },
  { key: "gemini_model", label: "Gemini model" },
  { key: "ai_rules", label: "Extra AI grading rules", type: "textarea" },
  { key: "azure_tts_key", label: "AI voice: Azure Speech key", type: "password",
    help: "Generates question and model-answer audio with one click (Courses and questions). portal.azure.com → create a Speech resource → Keys and Endpoint. Stored on the server only." },
  { key: "azure_tts_region", label: "AI voice: Azure region", help: "From the same page, e.g. westeurope or eastus." },
  { key: "tts_voice_uz", label: "Uzbek voice", help: "Default uz-UZ-MadinaNeural (female); uz-UZ-SardorNeural is the male voice." },
  { key: "tts_voice_ru", label: "Russian voice", help: "Default ru-RU-SvetlanaNeural; ru-RU-DmitryNeural is the male voice." },
  { key: "support_contact", label: "Support contact", help: "e.g. @your_username. Shown in Profile and to blocked users." },
  { key: "miniapp_url", label: "Mini App URL", help: "https URL of the user app. The bot's menu button and \"Open app\" use it." },
  { key: "welcome_text", label: "Bot welcome text", type: "textarea", help: "Optional. Replaces the default /start message." },
];

function PasswordCard() {
  const [isSet, setIsSet] = useState<boolean | null>(null);
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [msg, setMsg] = useState("");
  const [ok, setOk] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<{ set: boolean }>("/admin/password-status").then((r) => setIsSet(r.set)).catch(() => setIsSet(null)); }, []);

  const mismatch = again.length > 0 && next !== again;
  const save = async () => {
    setBusy(true); setMsg(""); setOk("");
    try {
      await post("/admin/password", { current, new: next });
      setOk(t("Password changed. Use the new one next time you sign in.")); setCurrent(""); setNext(""); setAgain(""); setIsSet(true);
    } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="form panel" style={{ maxWidth: 640, marginBottom: 20 }}>
      <h3 style={{ margin: 0 }}>{t("Admin password")}</h3>
      <p className="muted small">{isSet === false ? t("No password is set yet. Choose one (at least 10 characters).") : t("Change the password you use to sign in to this panel. At least 10 characters.")}</p>
      {isSet && <label>{t("Current password")}<input type="password" value={current} autoComplete="current-password" onChange={(e) => setCurrent(e.target.value)} /></label>}
      <label>{t("New password")}<input type="password" value={next} autoComplete="new-password" onChange={(e) => setNext(e.target.value)} /></label>
      <label>{t("New password again")}<input type="password" value={again} autoComplete="new-password" onChange={(e) => setAgain(e.target.value)} />
        {mismatch && <span className="error-text small">{t("The two passwords are different.")}</span>}</label>
      <Err msg={msg} />
      {ok && <div className="alert ok">{ok}</div>}
      <button className="btn" disabled={busy || next.length < 10 || next !== again || (isSet === true && !current)} onClick={save}>{t("Change password")}</button>
      <p className="muted small">{tx("Forgot it? Send {cmd} to your bot for a new random one.", { cmd: <code>/password</code> })}</p>
    </div>
  );
}

export default function Settings() {
  const [s, setS] = useState<S | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  useEffect(() => { api<S>("/admin/settings").then(setS).catch((e) => setError(e.message)); }, []);
  const save = async () => {
    setError(""); setSaved("");
    try { await put("/admin/settings", s); setSaved(t("Saved.")); } catch (e) { setError((e as Error).message); }
  };
  if (!s) return error ? <Err msg={error} /> : <Loading />;
  return (
    <Page title={t("Settings")}>
      <PasswordCard />
      <div className="form panel" style={{ maxWidth: 640 }}>
        {FIELDS.map((f) => {
          if (f.key.startsWith("gemini") || f.key === "ai_rules") if (s.grading_mode !== "ai") return null;
          const v = s[f.key] ?? "";
          const set = (val: string | number) => setS({ ...s, [f.key]: val });
          return (
            <label key={f.key}>{t(f.label)}
              {f.type === "textarea" ? <textarea rows={3} value={v} onChange={(e) => set(e.target.value)} />
                : f.type === "select" ? <select value={v} onChange={(e) => set(e.target.value)}>
                  {f.options!.map(([o, l]) => <option key={o} value={o}>{t(l)}</option>)}</select>
                : <input type={f.type === "number" ? "number" : f.type === "password" ? "password" : "text"} value={v}
                    onChange={(e) => set(f.type === "number" ? +e.target.value : e.target.value)} autoComplete="off" />}
              {f.help && <span className="muted small">{t(f.help)}</span>}
            </label>
          );
        })}
        <Err msg={error} />
        {saved && <div className="alert ok">{saved}</div>}
        <button className="btn" onClick={save}>{t("Save settings")}</button>
      </div>
    </Page>
  );
}
