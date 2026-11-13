import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, inTelegram, tg, type Attempt, type CourseQuestions, type Me } from "./api";
import { LangContext, type Lang, translate } from "./i18n";
import AttemptView from "./screens/AttemptView";
import Home from "./screens/Home";
import Learn from "./screens/Learn";
import Mock from "./screens/Mock";
import Paywall from "./screens/Paywall";
import Profile, { SupportLink } from "./screens/Profile";
import QuestionScreen from "./screens/Question";
import Results from "./screens/Results";
import { ErrorBox, Spinner } from "./ui";

type Tab = "home" | "results" | "profile";
type View =
  | { name: Tab }
  | { name: "question"; id: number }
  | { name: "attempt"; id: number; initial?: Attempt }
  | { name: "paywall" }
  | { name: "mock"; courseId: number }
  | { name: "learn"; courseId: number };

const browserLang = (): Lang => {
  const l = navigator.language?.slice(0, 2);
  return l === "ru" ? "ru" : l === "en" ? "en" : "uz";
};

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<{ status: number; msg: string } | null>(null);
  const [stack, setStack] = useState<View[]>([{ name: "home" }]);
  const view = stack[stack.length - 1];
  const lang: Lang = me?.ui_language ?? browserLang();
  const t = (k: Parameters<typeof translate>[1]) => translate(lang, k);

  const loadMe = useCallback(() => {
    setError(null);
    api<Me>("/me").then(setMe).catch((e) => setError({ status: e instanceof ApiError ? e.status : 0, msg: e.message }));
  }, []);

  useEffect(() => {
    tg()?.ready();
    tg()?.expand();
    if (inTelegram()) loadMe();
  }, [loadMe]);

  const push = (v: View) => { setStack((s) => [...s, v]); window.scrollTo(0, 0); };
  const replace = (v: View) => { setStack((s) => [...s.slice(0, -1), v]); window.scrollTo(0, 0); };
  const back = useCallback(() => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s)), []);
  const tab = (name: Tab) => { setStack([{ name }]); window.scrollTo(0, 0); };

  // Telegram's native back button mirrors the in-app stack.
  const backRef = useRef(back);
  backRef.current = () => { back(); if (stack.length <= 2) loadMe(); };
  useEffect(() => {
    const b = tg()?.BackButton;
    if (!b) return;
    const handler = () => backRef.current();
    b.onClick(handler);
    return () => b.offClick(handler);
  }, []);
  useEffect(() => {
    const b = tg()?.BackButton;
    if (!b) return;
    if (stack.length > 1) b.show(); else b.hide();
  }, [stack.length]);

  const setLang = async (l: Lang) => {
    if (!me) return;
    setMe({ ...me, ui_language: l });
    await api("/me", { method: "PATCH", body: JSON.stringify({ ui_language: l }) }).catch(() => undefined);
  };
  const setCourse = async (id: number) => {
    if (!me) return;
    setMe({ ...me, course_id: id });
    await api("/me", { method: "PATCH", body: JSON.stringify({ course_id: id }) }).catch(() => undefined);
  };

  const nextAfter = async (questionId: number, courseId: number) => {
    try {
      const data = await api<CourseQuestions>(`/courses/${courseId}/questions`);
      const i = data.questions.findIndex((q) => q.id === questionId);
      const next = data.questions.slice(i + 1).find((q) => !q.locked);
      if (next) replace({ name: "question", id: next.id });
      else { setStack([{ name: "home" }]); loadMe(); }
    } catch { setStack([{ name: "home" }]); }
  };

  if (!inTelegram()) {
    return <LangContext.Provider value={lang}><div className="page"><div className="card center-text">
      <div className="big-emoji">📱</div><p>{t("open_in_telegram")}</p></div></div></LangContext.Provider>;
  }
  if (error) {
    if (error.status === 403 && error.msg === "blocked") {
      return <LangContext.Provider value={lang}><div className="page"><div className="card center-text">
        <div className="big-emoji">⛔</div><p>{t("blocked_text")}</p></div></div></LangContext.Provider>;
    }
    return <LangContext.Provider value={lang}><div className="page"><ErrorBox error={`${t("error")}: ${error.msg}`} onRetry={loadMe} /></div></LangContext.Provider>;
  }
  if (!me) return <LangContext.Provider value={lang}><div className="page"><Spinner /></div></LangContext.Provider>;
  if (me.status === "blocked") {
    return <LangContext.Provider value={lang}><div className="page"><div className="card center-text">
      <div className="big-emoji">⛔</div><p>{t("blocked_text")}</p>
      {me.support_contact && <SupportLink contact={me.support_contact} />}</div></div></LangContext.Provider>;
  }

  const isTab = view.name === "home" || view.name === "results" || view.name === "profile";

  return (
    <LangContext.Provider value={lang}>
      <div className={`page ${isTab ? "with-tabs" : ""}`}>
        {!tg()?.BackButton && stack.length > 1 && <button className="btn link back" onClick={back}>← </button>}
        {view.name === "home" && (
          <Home key={me.course_id ?? 0} me={me} onCourse={setCourse}
            onOpen={(id) => push({ name: "question", id })} onPaywall={() => push({ name: "paywall" })}
            onMock={(courseId) => push({ name: "mock", courseId })} onLearn={(courseId) => push({ name: "learn", courseId })} />
        )}
        {view.name === "results" && <Results onOpen={(id) => push({ name: "attempt", id })} />}
        {view.name === "profile" && <Profile me={me} onLang={setLang} onPaywall={() => push({ name: "paywall" })} />}
        {view.name === "paywall" && <Paywall me={me} onDone={() => { setStack([{ name: "home" }]); loadMe(); }} />}
        {view.name === "mock" && (
          <Mock key={view.courseId} me={me} courseId={view.courseId}
            onPaywall={() => replace({ name: "paywall" })}
            onExit={() => { setStack([{ name: "home" }]); loadMe(); }} />
        )}
        {view.name === "learn" && <Learn courseId={view.courseId} />}
        {view.name === "question" && (
          <QuestionScreen key={view.id} me={me} id={view.id}
            onAttempt={(a) => replace({ name: "attempt", id: a.id, initial: a })}
            onPaywall={() => replace({ name: "paywall" })} />
        )}
        {view.name === "attempt" && (
          <AttemptView key={view.id} id={view.id} initial={view.initial}
            onAgain={(qid) => replace({ name: "question", id: qid })}
            onNext={stack.length > 1 && stack[0].name === "home" && view.initial
              ? () => nextAfter(view.initial!.question.id, view.initial!.question.course_id) : undefined}
            onList={() => { setStack([{ name: "home" }]); loadMe(); }} />
        )}
      </div>
      {isTab && (
        <nav className="tabs">
          {(["home", "results", "profile"] as Tab[]).map((n) => (
            <button key={n} className={view.name === n ? "active" : ""} onClick={() => { tab(n); if (n === "home") loadMe(); }}>
              <span className="tab-icon">{n === "home" ? "📚" : n === "results" ? "📊" : "👤"}</span>
              {t(n === "home" ? "tab_questions" : n === "results" ? "tab_results" : "tab_profile")}
            </button>
          ))}
        </nav>
      )}
    </LangContext.Provider>
  );
}
