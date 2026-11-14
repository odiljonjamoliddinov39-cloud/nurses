import { t } from "../i18n";
import { api, fmtDate } from "../api";
import { Err, Loading, Page, useLoad } from "../ui";

interface L { id: number; admin_id: number; action: string; object: string; old: unknown; new: unknown; reason: string | null; created_at: string }

export default function Logs() {
  const { data, error } = useLoad(() => api<L[]>("/admin/logs"));
  return (
    <Page title={t("Logs")}>
      <Err msg={error} />
      {!data ? <Loading /> : data.length === 0 ? <div className="empty">{t("Nothing yet.")}</div> : (
        <table>
          <thead><tr><th>{t("When")}</th><th>{t("Admin")}</th><th>{t("Action")}</th><th>{t("Object")}</th><th>{t("Details")}</th></tr></thead>
          <tbody>
            {data.map((l) => (
              <tr key={l.id}>
                <td className="small">{fmtDate(l.created_at)}</td><td>{l.admin_id}</td><td><code>{l.action}</code></td><td>{l.object}</td>
                <td className="small clip">{l.reason ? `${l.reason} ` : ""}{l.new ? JSON.stringify(l.new) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Page>
  );
}
