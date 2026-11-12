import { Fragment, useState } from "react";
import { api, fmtDate, put } from "../api";
import { AuthAudio, Err, Loading, Page, Score, useLoad } from "../ui";

interface A { id: number; user_id: number; user: string | null; number: number; question: string; state: string; mode: string;
  score: number | null; manual_score: number | null; audio: number | null; transcript: string | null; comment: string | null; created_at: string }

export default function Attempts() {
  const { data, error, reload } = useLoad(() => api<A[]>("/admin/attempts"));
  const [open, setOpen] = useState<number | null>(null);
  const [msg, setMsg] = useState("");
  const setScore = async (id: number, v: string) => {
    setMsg("");
    try { await put(`/admin/attempts/${id}/score`, { score: v === "" ? null : +v }); reload(); }
    catch (e) { setMsg((e as Error).message); }
  };
  return (
    <Page title="Answers">
      <p className="muted">Every recorded answer. Listen and set a teacher score if the user's score is off; the teacher score is what the user sees.</p>
      <Err msg={error || msg} />
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">No answers yet.</div> : (
        <table>
          <thead><tr><th>When</th><th>User</th><th>Question</th><th>Graded by</th><th>Score</th><th>Teacher score</th><th /></tr></thead>
          <tbody>
            {data.map((a) => (
              <Fragment key={a.id}>
                <tr>
                  <td className="small">{fmtDate(a.created_at)}</td><td>{a.user ?? a.user_id}</td>
                  <td className="clip">Q{a.number}. {a.question}</td>
                  <td>{a.state === "graded" ? a.mode : <span className="muted">{a.state}</span>}</td>
                  <td><Score v={a.score} /></td>
                  <td>
                    <select value={a.manual_score ?? ""} onChange={(e) => setScore(a.id, e.target.value)}>
                      <option value="">—</option>
                      {[0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5].map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td><button className="btn small secondary" onClick={() => setOpen(open === a.id ? null : a.id)}>{open === a.id ? "Hide" : "Listen"}</button></td>
                </tr>
                {open === a.id && (
                  <tr className="expand"><td colSpan={7}>
                    {a.audio ? <AuthAudio id={a.audio} /> : <span className="muted">No audio</span>}
                    {a.transcript && <p><b>Transcript:</b> {a.transcript}</p>}
                    {a.comment && <p><b>AI comment:</b> {a.comment}</p>}
                  </td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </Page>
  );
}
