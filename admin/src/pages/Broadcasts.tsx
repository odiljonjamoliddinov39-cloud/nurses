import { t } from "../i18n";
import { useEffect, useState } from "react";
import { api, del, fmtDate, nameOf, post, put, type I18n } from "../api";
import { Badge, Err, Loading, Modal, Page, useLoad } from "../ui";

interface B {
  id: number; text: string; segment: string; button: { text: string; url: string } | null; image: number | null;
  status: string; scheduled_at: string | null; sent_at: string | null; created_at: string;
  total: number; sent: number; failed: number;
}
interface CourseLite { id: number; name: I18n }

const SEGMENTS: [string, string][] = [
  ["all", "Everyone"], ["subscribers", "Active subscribers"], ["expired", "Expired subscribers"], ["guests", "Guests (never subscribed)"],
];
const segmentLabel = (s: string, courses: CourseLite[]) =>
  SEGMENTS.map(([k, l]) => [k, t(l)]).find(([k]) => k === s)?.[1] ?? (s.startsWith("course:") ? `${t("Course")}: ${nameOf(courses.find((c) => c.id === +s.slice(7))?.name)}` : s);

/** value for <input type="datetime-local"> in the admin's own time zone */
const toLocalInput = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};

export default function Broadcasts() {
  const { data, error, reload } = useLoad(() => api<B[]>("/admin/broadcasts"));
  const courses = useLoad(() => api<CourseLite[]>("/admin/courses"));
  const [edit, setEdit] = useState<Partial<B> | null>(null);
  const [msg, setMsg] = useState("");

  // Sending progress: refresh while something is going out.
  useEffect(() => {
    if (!data?.some((b) => b.status === "sending" || b.status === "scheduled")) return;
    const h = window.setInterval(reload, 4000);
    return () => window.clearInterval(h);
  }, [data]); // eslint-disable-line

  const sendNow = async (b: B) => {
    if (!confirm(t("Send this message now to \"{to}\"? It cannot be undone.", { to: segmentLabel(b.segment, courses.data ?? []) }))) return;
    setMsg("");
    try { await post(`/admin/broadcasts/${b.id}/send`); reload(); } catch (e) { setMsg((e as Error).message); }
  };
  const remove = async (b: B) => {
    if (!confirm(t("Delete this broadcast?"))) return;
    try { await del(`/admin/broadcasts/${b.id}`); reload(); } catch (e) { setMsg((e as Error).message); }
  };

  return (
    <Page title={t("Broadcasts")} actions={<button className="btn" onClick={() => setEdit({ text: "", segment: "all", button: null })}>{t("+ New broadcast")}</button>}>
      <Err msg={error || msg} />
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">{t("No broadcasts yet. Write one to message your users through the bot.")}</div> : (
        <table>
          <thead><tr><th>{t("Message")}</th><th>{t("To")}</th><th>{t("Status")}</th><th>{t("Delivered")}</th><th>{t("When")}</th><th /></tr></thead>
          <tbody>
            {data.map((b) => (
              <tr key={b.id}>
                <td className="clip">{b.image ? "🖼 " : ""}{b.text}</td>
                <td>{segmentLabel(b.segment, courses.data ?? [])}</td>
                <td><Badge value={b.status} /></td>
                <td>{b.status === "draft" || b.status === "scheduled" ? "—" : `${b.sent} / ${b.total}${b.failed ? ` (${t("{n} failed", { n: b.failed })})` : ""}`}</td>
                <td>{fmtDate(b.sent_at ?? b.scheduled_at ?? b.created_at)}</td>
                <td className="row gap">
                  {(b.status === "draft" || b.status === "scheduled") && (
                    <>
                      <button className="btn small" onClick={() => sendNow(b)}>{t("Send now")}</button>
                      <button className="btn small secondary" onClick={() => setEdit(b)}>{t("Edit")}</button>
                      <button className="btn small danger" onClick={() => remove(b)}>{t("Delete")}</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {edit && <BroadcastModal b={edit} courses={courses.data ?? []} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </Page>
  );
}

function BroadcastModal({ b, courses, onClose, onSaved }: { b: Partial<B>; courses: CourseLite[]; onClose: () => void; onSaved: () => void }) {
  const initialKind = b.segment?.startsWith("course:") ? "course" : b.segment ?? "all";
  const [text, setText] = useState(b.text ?? "");
  const [kind, setKind] = useState(initialKind);
  const [courseId, setCourseId] = useState<number | "">(b.segment?.startsWith("course:") ? +b.segment.slice(7) : courses[0]?.id ?? "");
  const [btnText, setBtnText] = useState(b.button?.text ?? "");
  const [btnUrl, setBtnUrl] = useState(b.button?.url ?? "");
  const [when, setWhen] = useState<"draft" | "now" | "later">(b.status === "scheduled" ? "later" : "draft");
  const [at, setAt] = useState(toLocalInput(b.scheduled_at ?? null));
  const [file, setFile] = useState<File | null>(null);
  const [hasImage, setHasImage] = useState(Boolean(b.image));
  const [count, setCount] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [savedId, setSavedId] = useState<number | undefined>(b.id);  // set once a draft exists, so saving again updates it

  const segment = kind === "course" ? `course:${courseId}` : kind;
  useEffect(() => {
    setCount(null);
    if (kind === "course" && courseId === "") return;
    api<{ count: number }>(`/admin/broadcasts/preview?segment=${encodeURIComponent(segment)}`).then((r) => setCount(r.count)).catch(() => setCount(null));
  }, [segment]); // eslint-disable-line

  const body = () => ({
    text, segment, button_text: btnText.trim() || null, button_url: btnUrl.trim() || null,
    send_now: when === "now", scheduled_at: when === "later" && at ? new Date(at).toISOString() : null,
  });

  /** Create or update, then attach the image. Returns the saved id. */
  const persist = async (): Promise<number> => {
    const saved = savedId ? await put<B>(`/admin/broadcasts/${savedId}`, { ...body(), send_now: false }) : await post<B>("/admin/broadcasts", { ...body(), send_now: false });
    setSavedId(saved.id);
    if (file) {
      const fd = new FormData();
      fd.append("image", file);
      await post(`/admin/broadcasts/${saved.id}/image`, fd);
    } else if (!hasImage) {
      await del(`/admin/broadcasts/${saved.id}/image`);
    }
    return saved.id;
  };

  const run = async (fn: () => Promise<void>) => {
    setBusy(true); setMsg(""); setNote("");
    try { await fn(); } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  const save = () => run(async () => {
    if (when === "later" && !at) throw new Error(t("Pick the date and time to send."));
    const id = await persist();
    if (when === "now") {
      if (!confirm(t("Send this message now to {n} people? It cannot be undone.", { n: count ?? "?" }))) { onSaved(); return; }
      await post(`/admin/broadcasts/${id}/send`);
    }
    onSaved();
  });
  const test = () => run(async () => {
    const id = await persist();
    const r = await post<{ ok: boolean }>(`/admin/broadcasts/${id}/test`);
    setNote(r.ok ? t("Test message sent to your Telegram. A draft was saved.") : t("Telegram refused the test. Have you started the bot from your admin account? A draft was saved."));
  });

  return (
    <Modal title={savedId ? t("Edit broadcast") : t("New broadcast")} onClose={onClose} wide>
      <div className="form">
        <label>{t("Message *")}<textarea rows={6} maxLength={4000} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("Plain text. Up to 4000 characters.")} /></label>
        <div className="muted small">{text.length} / 4000{hasImage || file ? " · " + t("with an image: text over 1024 characters is sent as a separate message") : ""}</div>

        <div className="row gap wrap">
          <label style={{ flex: 1, minWidth: 220 }}>{t("Send to")}
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              {SEGMENTS.map(([k, l]) => <option key={k} value={k}>{t(l)}</option>)}
              <option value="course">{t("Users of a course…")}</option>
            </select>
          </label>
          {kind === "course" && (
            <label style={{ flex: 1, minWidth: 220 }}>{t("Course")}
              <select value={courseId} onChange={(e) => setCourseId(+e.target.value)}>
                {courses.map((c) => <option key={c.id} value={c.id}>{nameOf(c.name)}</option>)}
              </select>
            </label>
          )}
          <div style={{ alignSelf: "flex-end" }} className="muted">{count == null ? "…" : <b>{count} {count === 1 ? t("person") : t("people")}</b>} {t("will receive it")}</div>
        </div>

        <fieldset>
          <legend>{t("Button (optional)")}</legend>
          <div className="row gap">
            <input style={{ width: 180 }} value={btnText} onChange={(e) => setBtnText(e.target.value)} placeholder={t("Button label")} maxLength={60} />
            <input style={{ flex: 1 }} value={btnUrl} onChange={(e) => setBtnUrl(e.target.value)} placeholder={t("https://… (link opened by the button)")} />
          </div>
        </fieldset>

        <fieldset>
          <legend>{t("Image (optional)")}</legend>
          <div className="row gap wrap">
            {(hasImage && !file) && <span>{t("🖼 Image attached")} <button className="btn small danger" onClick={() => setHasImage(false)}>{t("Remove")}</button></span>}
            {file && <span>🖼 {file.name} <button className="btn small danger" onClick={() => setFile(null)}>{t("Remove")}</button></span>}
            <label className="btn small secondary">{hasImage || file ? t("Replace") : t("Choose image")}
              <input type="file" accept="image/*" hidden onChange={(e) => { if (e.target.files?.[0]) { setFile(e.target.files[0]); setHasImage(true); } }} />
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend>{t("When")}</legend>
          <div className="row gap wrap">
            <label className="check"><input type="radio" name="when" checked={when === "draft"} onChange={() => setWhen("draft")} /> {t("Save as draft")}</label>
            <label className="check"><input type="radio" name="when" checked={when === "now"} onChange={() => setWhen("now")} /> {t("Send now")}</label>
            <label className="check"><input type="radio" name="when" checked={when === "later"} onChange={() => setWhen("later")} /> {t("Schedule")}</label>
            {when === "later" && <input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />}
          </div>
        </fieldset>

        <Err msg={msg} />
        {note && <div className="alert">{note}</div>}
        <div className="row gap">
          <button className="btn" onClick={save} disabled={busy || !text.trim()}>{when === "now" ? t("Send") : when === "later" ? t("Schedule") : t("Save draft")}</button>
          <button className="btn secondary" onClick={test} disabled={busy || !text.trim()}>{t("Send test to me")}</button>
        </div>
      </div>
    </Modal>
  );
}
