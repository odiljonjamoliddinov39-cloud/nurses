import { api, type Attempt } from "./api";
import type { Recording } from "./Recorder";

/** Upload one recorded answer; the backend stores it and returns the new attempt. */
export function uploadAnswer(questionId: number, rec: Recording): Promise<Attempt> {
  const ext = rec.mime.includes("mp4") || rec.mime.includes("aac") ? "m4a" : rec.mime.includes("ogg") ? "ogg" : "webm";
  const fd = new FormData();
  fd.append("question_id", String(questionId));
  fd.append("audio", new File([rec.blob], `answer.${ext}`, { type: rec.mime }));
  return api<Attempt>("/attempts", { method: "POST", body: fd });
}
