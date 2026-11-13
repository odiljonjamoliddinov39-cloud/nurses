import { useState } from "react";
import { api, fmtSum, nameOf, post, put, type I18n } from "../api";
import { Err, Loading, Modal, Page, useLoad } from "../ui";

interface Plan { id: number; name: string; days: number; price_uzs: number; is_active: boolean; course_ids: number[] }
interface CourseLite { id: number; name: I18n }
const EMPTY = { name: "", days: 30, price_uzs: 0, is_active: true, course_ids: [] as number[] };

export default function Plans() {
  const { data, error, reload } = useLoad(() => api<Plan[]>("/admin/plans"));
  const courses = useLoad(() => api<CourseLite[]>("/admin/courses"));
  const [edit, setEdit] = useState<(typeof EMPTY & { id?: number }) | null>(null);
  const [msg, setMsg] = useState("");

  const save = async () => {
    if (!edit) return;
    setMsg("");
    try {
      const { id, ...body } = edit;
      if (id) await put(`/admin/plans/${id}`, body); else await post("/admin/plans", body);
      setEdit(null); reload();
    } catch (e) { setMsg((e as Error).message); }
  };
  const cname = (id: number) => nameOf(courses.data?.find((c) => c.id === id)?.name);

  return (
    <Page title="Plans" actions={<button className="btn" onClick={() => setEdit({ ...EMPTY })}>+ New plan</button>}>
      <Err msg={error} />
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">No plans yet. Users can't subscribe until you add one.</div> : (
        <table>
          <thead><tr><th>Name</th><th>Days</th><th>Price</th><th>Courses</th><th>Shown</th><th /></tr></thead>
          <tbody>
            {data.map((p) => (
              <tr key={p.id}>
                <td><b>{p.name}</b></td><td>{p.days}</td><td>{fmtSum(p.price_uzs)} UZS</td>
                <td>{p.course_ids.length ? p.course_ids.map(cname).join(", ") : <span className="muted">All courses</span>}</td>
                <td>{p.is_active ? "Yes" : "Hidden"}</td>
                <td><button className="btn small" onClick={() => setEdit({ ...p })}>Edit</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {edit && (
        <Modal title={edit.id ? "Edit plan" : "New plan"} onClose={() => setEdit(null)}>
          <div className="form">
            <label>Name<input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} placeholder="1 oy" /></label>
            <label>Days<input type="number" min={1} value={edit.days} onChange={(e) => setEdit({ ...edit, days: +e.target.value })} /></label>
            <label>Price, UZS<input type="number" min={0} value={edit.price_uzs} onChange={(e) => setEdit({ ...edit, price_uzs: +e.target.value })} /></label>
            <fieldset>
              <legend>Courses (none = all courses)</legend>
              {courses.data?.map((c) => (
                <label key={c.id} className="check">
                  <input type="checkbox" checked={edit.course_ids.includes(c.id)} onChange={(e) => setEdit({
                    ...edit, course_ids: e.target.checked ? [...edit.course_ids, c.id] : edit.course_ids.filter((x) => x !== c.id) })} />
                  {nameOf(c.name)}
                </label>
              ))}
            </fieldset>
            <label className="check"><input type="checkbox" checked={edit.is_active}
              onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} /> Shown to users</label>
            <Err msg={msg} />
            <button className="btn" onClick={save} disabled={!edit.name || edit.days < 1}>Save</button>
          </div>
        </Modal>
      )}
    </Page>
  );
}
