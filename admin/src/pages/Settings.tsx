import { useEffect, useState } from "react";
import { api, put } from "../api";
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
  { key: "support_contact", label: "Support contact", help: "e.g. @your_username. Shown in Profile and to blocked users." },
  { key: "miniapp_url", label: "Mini App URL", help: "https URL of the user app. The bot's menu button and \"Open app\" use it." },
  { key: "welcome_text", label: "Bot welcome text", type: "textarea", help: "Optional. Replaces the default /start message." },
];

export default function Settings() {
  const [s, setS] = useState<S | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  useEffect(() => { api<S>("/admin/settings").then(setS).catch((e) => setError(e.message)); }, []);
  const save = async () => {
    setError(""); setSaved("");
    try { await put("/admin/settings", s); setSaved("Saved."); } catch (e) { setError((e as Error).message); }
  };
  if (!s) return error ? <Err msg={error} /> : <Loading />;
  return (
    <Page title="Settings">
      <div className="form panel" style={{ maxWidth: 640 }}>
        {FIELDS.map((f) => {
          if (f.key.startsWith("gemini") || f.key === "ai_rules") if (s.grading_mode !== "ai") return null;
          const v = s[f.key] ?? "";
          const set = (val: string | number) => setS({ ...s, [f.key]: val });
          return (
            <label key={f.key}>{f.label}
              {f.type === "textarea" ? <textarea rows={3} value={v} onChange={(e) => set(e.target.value)} />
                : f.type === "select" ? <select value={v} onChange={(e) => set(e.target.value)}>
                  {f.options!.map(([o, l]) => <option key={o} value={o}>{l}</option>)}</select>
                : <input type={f.type === "number" ? "number" : f.type === "password" ? "password" : "text"} value={v}
                    onChange={(e) => set(f.type === "number" ? +e.target.value : e.target.value)} autoComplete="off" />}
              {f.help && <span className="muted small">{f.help}</span>}
            </label>
          );
        })}
        <Err msg={error} />
        {saved && <div className="alert ok">{saved}</div>}
        <button className="btn" onClick={save}>Save settings</button>
      </div>
    </Page>
  );
}
