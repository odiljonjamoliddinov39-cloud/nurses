import { useEffect, useRef, useState } from "react";
import { api, del, download, nameOf, post, put, type I18n } from "../api";
import { AuthAudio, Err, Loading, Modal, Page, useLoad } from "../ui";

interface Topic { id: number; name: string; order: number }
interface Course { id: number; name: I18n; description: I18n | null; is_published: boolean; questions: number; topics: Topic[] }
interface KP { id?: number; text: string; weight: number }
interface Q {
  id: number; course_id: number; topic_id: number | null; number: number; text: string; model_answer: string;
  explanation: string | null; is_active: boolean; question_audio: number | null; answer_audio: number | null; key_points: KP[];
}

export default function Content() {
  const courses = useLoad(() => api<Course[]>("/admin/courses"));
  const [cid, setCid] = useState<number | null>(null);
  const [editCourse, setEditCourse] = useState<Partial<Course> | null>(null);
  const course = courses.data?.find((c) => c.id === cid) ?? courses.data?.[0] ?? null;

  useEffect(() => { if (course && cid !== course.id) setCid(course.id); }, [course?.id]); // eslint-disable-line

  return (
    <Page title="Courses and questions" actions={
      <>
        {courses.data && courses.data.length > 0 && (
          <select value={course?.id ?? ""} onChange={(e) => setCid(+e.target.value)}>
            {courses.data.map((c) => <option key={c.id} value={c.id}>{nameOf(c.name)}{c.is_published ? "" : " (hidden)"}</option>)}
          </select>
        )}
        {course && <button className="btn secondary" onClick={() => setEditCourse(course)}>Edit course</button>}
        <button className="btn" onClick={() => setEditCourse({ name: {}, description: {}, is_published: false })}>+ New course</button>
      </>}>
      <Err msg={courses.error} />
      {!courses.data ? <Loading /> : !course ? (
        <div className="empty">No courses yet. Create the first course, e.g. "Hamshiralar og'zaki imtihoni".</div>
      ) : (
        <>
          {!course.is_published && <div className="alert warn">This course is hidden from users. Open "Edit course" and tick "Published" when it's ready.</div>}
          <Topics course={course} onChange={courses.reload} />
          <Questions key={course.id} course={course} onChange={courses.reload} />
        </>
      )}
      {editCourse && <CourseModal course={editCourse} onClose={() => setEditCourse(null)}
        onSaved={(id) => { setEditCourse(null); courses.reload(); if (id) setCid(id); }} />}
    </Page>
  );
}

function CourseModal({ course, onClose, onSaved }: { course: Partial<Course>; onClose: () => void; onSaved: (id?: number) => void }) {
  const [name, setName] = useState<I18n>(course.name ?? {});
  const [desc, setDesc] = useState<I18n>(course.description ?? {});
  const [pub, setPub] = useState(course.is_published ?? false);
  const [msg, setMsg] = useState("");
  const save = async () => {
    try {
      const body = { name, description: desc, is_published: pub };
      if (course.id) { await put(`/admin/courses/${course.id}`, body); onSaved(); }
      else onSaved((await post<{ id: number }>("/admin/courses", body)).id);
    } catch (e) { setMsg((e as Error).message); }
  };
  return (
    <Modal title={course.id ? "Edit course" : "New course"} onClose={onClose}>
      <div className="form">
        {(["uz", "ru", "en"] as const).map((l) => (
          <label key={l}>Name ({l}){l === "uz" ? " *" : ""}<input value={name[l] ?? ""} onChange={(e) => setName({ ...name, [l]: e.target.value })} /></label>
        ))}
        {(["uz", "ru", "en"] as const).map((l) => (
          <label key={l}>Description ({l})<textarea rows={2} value={desc[l] ?? ""} onChange={(e) => setDesc({ ...desc, [l]: e.target.value })} /></label>
        ))}
        <label className="check"><input type="checkbox" checked={pub} onChange={(e) => setPub(e.target.checked)} /> Published (visible to users)</label>
        <Err msg={msg} />
        <button className="btn" onClick={save} disabled={!name.uz && !name.ru && !name.en}>Save</button>
      </div>
    </Modal>
  );
}

function Topics({ course, onChange }: { course: Course; onChange: () => void }) {
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const add = async () => {
    try { await post(`/admin/courses/${course.id}/topics`, { name, order: course.topics.length }); setName(""); onChange(); }
    catch (e) { setMsg((e as Error).message); }
  };
  const rename = async (t: Topic) => {
    const n = prompt("Topic name", t.name);
    if (n && n.trim()) { await put(`/admin/topics/${t.id}`, { name: n, order: t.order }); onChange(); }
  };
  const remove = async (t: Topic) => {
    if (confirm(`Delete topic "${t.name}"? Its questions stay, without a topic.`)) { await del(`/admin/topics/${t.id}`); onChange(); }
  };
  return (
    <div className="panel">
      <h3>Topics</h3>
      <div className="row gap wrap">
        {course.topics.map((t) => (
          <span key={t.id} className="tag">{t.name}
            <button className="icon" title="Rename" onClick={() => rename(t)}>✎</button>
            <button className="icon" title="Delete" onClick={() => remove(t)}>✕</button>
          </span>
        ))}
        <input placeholder="New topic" value={name} onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && name.trim() && add()} />
        <button className="btn small" disabled={!name.trim()} onClick={add}>Add</button>
      </div>
      <Err msg={msg} />
    </div>
  );
}

function Questions({ course, onChange }: { course: Course; onChange: () => void }) {
  const { data, error, reload } = useLoad(() => api<Q[]>(`/admin/courses/${course.id}/questions`), [course.id]);
  const [edit, setEdit] = useState<Partial<Q> | null>(null);
  const [filter, setFilter] = useState("");
  const [importMsg, setImportMsg] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const refresh = () => { reload(); onChange(); };

  const doImport = async (f: File) => {
    setImportMsg("Importing…");
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await post<{ created: number; updated: number }>(`/admin/courses/${course.id}/import`, fd);
      setImportMsg(`Imported: ${r.created} new, ${r.updated} updated.`);
      refresh();
    } catch (e) { setImportMsg(`Import failed: ${(e as Error).message}`); }
    if (file.current) file.current.value = "";
  };

  const topicName = (id: number | null) => course.topics.find((t) => t.id === id)?.name ?? "";
  const nextNumber = Math.max(0, ...(data ?? []).map((q) => q.number)) + 1;
  const shown = (data ?? []).filter((q) => !filter || q.text.toLowerCase().includes(filter.toLowerCase()) || String(q.number) === filter);

  return (
    <div className="panel">
      <div className="page-head small-head">
        <h3>Questions ({data?.length ?? 0})</h3>
        <div className="row gap wrap">
          <input placeholder="Search" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <button className="btn secondary small" onClick={() => download("/admin/import-template", "questions-template.xlsx")}>Excel template</button>
          <button className="btn secondary small" onClick={() => file.current?.click()}>Import Excel</button>
          <button className="btn secondary small" onClick={() => download(`/admin/courses/${course.id}/export`, `questions-${course.id}.xlsx`)}>Export Excel</button>
          <button className="btn small" onClick={() => setEdit({ course_id: course.id, number: nextNumber, text: "", model_answer: "", key_points: [], is_active: true, topic_id: null })}>+ Question</button>
          <input ref={file} type="file" accept=".xlsx" hidden onChange={(e) => e.target.files?.[0] && doImport(e.target.files[0])} />
        </div>
      </div>
      {importMsg && <div className="alert">{importMsg}</div>}
      <p className="muted small">Excel columns: <code>number, topic, question, model_answer, key_points, explanation</code>. Key points go one per line; add <code>| 2</code> after a point to give it weight 2. Rows with an existing number are updated.</p>
      <Err msg={error} />
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">No questions yet. Add one or import an Excel file.</div> : (
        <table>
          <thead><tr><th>#</th><th>Question</th><th>Topic</th><th>Key points</th><th>Audio</th><th /></tr></thead>
          <tbody>
            {shown.map((q) => (
              <tr key={q.id} className={`clickable ${q.is_active ? "" : "dim"}`} onClick={() => setEdit(q)}>
                <td>{q.number}</td>
                <td className="clip">{q.text}{!q.is_active && <span className="muted small"> (hidden)</span>}</td>
                <td>{topicName(q.topic_id)}</td>
                <td>{q.key_points.length || <span className="warn-text">0</span>}</td>
                <td>{q.question_audio ? "🔊" : ""}{q.answer_audio ? "🎧" : ""}</td>
                <td><button className="btn small">Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {edit && <QuestionModal q={edit} course={course} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); refresh(); }} />}
    </div>
  );
}

function QuestionModal({ q, course, onClose, onSaved }: { q: Partial<Q>; course: Course; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<Partial<Q>>({ ...q, key_points: (q.key_points ?? []).map((k) => ({ ...k })) });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [audio, setAudio] = useState({ question: q.question_audio ?? null, answer: q.answer_audio ?? null });
  const kps = f.key_points ?? [];
  const setKp = (i: number, patch: Partial<KP>) => setF({ ...f, key_points: kps.map((k, j) => (j === i ? { ...k, ...patch } : k)) });

  const save = async () => {
    setBusy(true); setMsg("");
    const body = {
      course_id: course.id, topic_id: f.topic_id ?? null, number: f.number, text: f.text ?? "",
      model_answer: f.model_answer ?? "", explanation: f.explanation ?? "", is_active: f.is_active ?? true,
      key_points: kps.filter((k) => k.text.trim()).map((k) => ({ text: k.text, weight: k.weight || 1 })),
    };
    try {
      if (q.id) await put(`/admin/questions/${q.id}`, body); else await post("/admin/questions", body);
      onSaved();
    } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!q.id || !confirm("Delete this question? If users already answered it, it is hidden instead.")) return;
    await del(`/admin/questions/${q.id}`);
    onSaved();
  };
  const upload = async (kind: "question" | "answer", file: File) => {
    const fd = new FormData();
    fd.append("kind", kind);
    fd.append("audio", file);
    try {
      const r = await post<{ file: number }>(`/admin/questions/${q.id}/audio`, fd);
      setAudio({ ...audio, [kind]: r.file });
    } catch (e) { setMsg((e as Error).message); }
  };
  const removeAudio = async (kind: "question" | "answer") => {
    await del(`/admin/questions/${q.id}/audio/${kind}`);
    setAudio({ ...audio, [kind]: null });
  };

  return (
    <Modal title={q.id ? `Question ${q.number}` : "New question"} onClose={onClose} wide>
      <div className="form">
        <div className="row gap">
          <label style={{ width: 100 }}>Number<input type="number" value={f.number ?? ""} onChange={(e) => setF({ ...f, number: +e.target.value })} /></label>
          <label style={{ flex: 1 }}>Topic
            <select value={f.topic_id ?? ""} onChange={(e) => setF({ ...f, topic_id: e.target.value ? +e.target.value : null })}>
              <option value="">— none —</option>
              {course.topics.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </label>
          <label className="check" style={{ alignSelf: "flex-end" }}><input type="checkbox" checked={f.is_active ?? true}
            onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Active</label>
        </div>
        <label>Question *<textarea rows={3} value={f.text ?? ""} onChange={(e) => setF({ ...f, text: e.target.value })} /></label>
        <label>Model answer<textarea rows={6} value={f.model_answer ?? ""} onChange={(e) => setF({ ...f, model_answer: e.target.value })} /></label>
        <fieldset>
          <legend>Key points (what a good answer must mention; weight = importance)</legend>
          {kps.map((k, i) => (
            <div key={i} className="row gap kp-row">
              <input style={{ flex: 1 }} value={k.text} onChange={(e) => setKp(i, { text: e.target.value })} placeholder={`Point ${i + 1}`} />
              <input type="number" min={0.5} step={0.5} value={k.weight} onChange={(e) => setKp(i, { weight: +e.target.value })} style={{ width: 70 }} title="weight" />
              <button className="icon" onClick={() => setF({ ...f, key_points: kps.filter((_, j) => j !== i) })}>✕</button>
            </div>
          ))}
          <button className="btn small secondary" onClick={() => setF({ ...f, key_points: [...kps, { text: "", weight: 1 }] })}>+ Key point</button>
        </fieldset>
        <label>Explanation (optional)<textarea rows={2} value={f.explanation ?? ""} onChange={(e) => setF({ ...f, explanation: e.target.value })} /></label>
        {q.id ? (
          <fieldset>
            <legend>Audio (teacher's recording)</legend>
            {(["question", "answer"] as const).map((kind) => (
              <div key={kind} className="row gap wrap audio-row">
                <b style={{ width: 130 }}>{kind === "question" ? "Question audio" : "Model answer audio"}</b>
                {audio[kind] ? <><AuthAudio id={audio[kind]!} /><button className="btn small danger" onClick={() => removeAudio(kind)}>Remove</button></>
                  : <span className="muted small">none</span>}
                <label className="btn small secondary">Upload<input type="file" accept="audio/*" hidden
                  onChange={(e) => e.target.files?.[0] && upload(kind, e.target.files[0])} /></label>
              </div>
            ))}
          </fieldset>
        ) : <p className="muted small">Save the question first to add audio.</p>}
        <Err msg={msg} />
        <div className="row gap">
          <button className="btn" onClick={save} disabled={busy || !f.text?.trim() || !f.number}>Save</button>
          {q.id && <button className="btn danger" onClick={remove}>Delete</button>}
        </div>
      </div>
    </Modal>
  );
}
