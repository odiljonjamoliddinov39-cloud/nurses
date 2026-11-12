import { createContext, useContext } from "react";
import type { I18n } from "./api";

export type Lang = "uz" | "ru" | "en";

const S = {
  loading: { uz: "Yuklanmoqda…", ru: "Загрузка…", en: "Loading…" },
  retry: { uz: "Qayta urinish", ru: "Повторить", en: "Try again" },
  open_in_telegram: {
    uz: "Bu ilova Telegram ichida ishlaydi. Botni oching va «Ilova» tugmasini bosing.",
    ru: "Это приложение работает внутри Telegram. Откройте бота и нажмите кнопку «Приложение».",
    en: "This app works inside Telegram. Open the bot and tap the app button.",
  },
  tab_questions: { uz: "Savollar", ru: "Вопросы", en: "Questions" },
  tab_results: { uz: "Natijalar", ru: "Результаты", en: "Results" },
  tab_profile: { uz: "Profil", ru: "Профиль", en: "Profile" },
  hello: { uz: "Salom", ru: "Здравствуйте", en: "Hello" },
  status_guest: { uz: "Mehmon", ru: "Гость", en: "Guest" },
  status_pending: { uz: "To'lov tekshirilmoqda", ru: "Оплата проверяется", en: "Payment under review" },
  status_subscriber: { uz: "Obuna faol", ru: "Подписка активна", en: "Subscribed" },
  status_expired: { uz: "Obuna tugagan", ru: "Подписка истекла", en: "Subscription ended" },
  status_blocked: { uz: "Bloklangan", ru: "Заблокирован", en: "Blocked" },
  until: { uz: "{d} gacha", ru: "до {d}", en: "until {d}" },
  no_courses: { uz: "Hozircha kurslar yo'q.", ru: "Курсов пока нет.", en: "No courses yet." },
  no_questions: { uz: "Bu kursda hali savollar yo'q.", ru: "В этом курсе пока нет вопросов.", en: "No questions in this course yet." },
  choose_course: { uz: "Kursni tanlang", ru: "Выберите курс", en: "Choose a course" },
  answered: { uz: "Javob berilgan", ru: "Отвечено", en: "Answered" },
  average: { uz: "O'rtacha ball", ru: "Средний балл", en: "Average score" },
  free_hint: {
    uz: "{n} ta savol bepul. Hammasini ochish uchun obuna bo'ling.",
    ru: "{n} вопроса бесплатно. Оформите подписку, чтобы открыть все.",
    en: "{n} questions are free. Subscribe to unlock all of them.",
  },
  subscribe: { uz: "Obuna bo'lish", ru: "Оформить подписку", en: "Subscribe" },
  renew: { uz: "Uzaytirish", ru: "Продлить", en: "Renew" },
  other: { uz: "Boshqa", ru: "Другое", en: "Other" },
  question: { uz: "Savol", ru: "Вопрос", en: "Question" },
  listen_question: { uz: "Savolni tinglash", ru: "Прослушать вопрос", en: "Listen to the question" },
  record_hint: {
    uz: "Mikrofon tugmasini bosing va javobingizni ovoz bilan ayting.",
    ru: "Нажмите на микрофон и ответьте вслух.",
    en: "Tap the microphone and answer out loud.",
  },
  recording: { uz: "Yozilmoqda", ru: "Идёт запись", en: "Recording" },
  stop: { uz: "To'xtatish", ru: "Остановить", en: "Stop" },
  rerecord: { uz: "Qayta yozish", ru: "Перезаписать", en: "Record again" },
  submit_answer: { uz: "Javobni yuborish", ru: "Отправить ответ", en: "Submit answer" },
  sending: { uz: "Yuborilmoqda…", ru: "Отправка…", en: "Sending…" },
  mic_denied: {
    uz: "Mikrofonga ruxsat berilmadi. Telegram sozlamalarida mikrofonni yoqing.",
    ru: "Нет доступа к микрофону. Разрешите микрофон в настройках Telegram.",
    en: "Microphone access was denied. Allow the microphone in Telegram settings.",
  },
  mic_unsupported: {
    uz: "Bu qurilmada ovoz yozib bo'lmaydi. Telegramni yangilang.",
    ru: "На этом устройстве запись недоступна. Обновите Telegram.",
    en: "Recording is not supported here. Please update Telegram.",
  },
  too_short: { uz: "Yozuv juda qisqa.", ru: "Запись слишком короткая.", en: "The recording is too short." },
  locked: { uz: "Bu savol obuna bilan ochiladi.", ru: "Этот вопрос доступен по подписке.", en: "This question needs a subscription." },
  daily_limit: { uz: "Bugungi limit tugadi. Ertaga davom eting.", ru: "Дневной лимит исчерпан. Продолжите завтра.", en: "Daily limit reached. Continue tomorrow." },
  self_check_title: { uz: "O'zingizni tekshiring", ru: "Проверьте себя", en: "Check yourself" },
  self_check_hint: {
    uz: "Namunaviy javob bilan solishtiring va aytgan fikrlaringizni belgilang.",
    ru: "Сравните с эталонным ответом и отметьте пункты, которые вы назвали.",
    en: "Compare with the model answer and tick the points you mentioned.",
  },
  self_score_hint: { uz: "Javobingizni baholang:", ru: "Оцените свой ответ:", en: "Rate your answer:" },
  model_answer: { uz: "Namunaviy javob", ru: "Эталонный ответ", en: "Model answer" },
  explanation: { uz: "Izoh", ru: "Пояснение", en: "Explanation" },
  key_points: { uz: "Asosiy fikrlar", ru: "Ключевые пункты", en: "Key points" },
  your_answer: { uz: "Sizning javobingiz", ru: "Ваш ответ", en: "Your answer" },
  get_score: { uz: "Ballni ko'rish", ru: "Узнать балл", en: "See my score" },
  ai_checking: { uz: "AI javobingizni tekshirmoqda…", ru: "ИИ проверяет ваш ответ…", en: "AI is checking your answer…" },
  ai_failed: {
    uz: "AI hozir ishlamayapti. O'zingiz tekshirishingiz mumkin.",
    ru: "ИИ сейчас недоступен. Вы можете проверить себя сами.",
    en: "AI is unavailable right now. You can check yourself instead.",
  },
  score: { uz: "Ball", ru: "Балл", en: "Score" },
  covered: { uz: "Aytilgan", ru: "Названо", en: "Covered" },
  missed: { uz: "Tushib qolgan", ru: "Пропущено", en: "Missed" },
  wrong: { uz: "Noto'g'ri fikrlar", ru: "Ошибочные утверждения", en: "Wrong statements" },
  comment: { uz: "Izoh", ru: "Комментарий", en: "Comment" },
  what_to_add: { uz: "Nimani qo'shish kerak", ru: "Что добавить", en: "What to add" },
  transcript: { uz: "Matn", ru: "Расшифровка", en: "Transcript" },
  teacher_score: { uz: "O'qituvchi bahosi", ru: "Оценка преподавателя", en: "Teacher's score" },
  try_again: { uz: "Qayta javob berish", ru: "Ответить ещё раз", en: "Answer again" },
  next_question: { uz: "Keyingi savol", ru: "Следующий вопрос", en: "Next question" },
  to_list: { uz: "Savollar ro'yxati", ru: "К списку вопросов", en: "Back to questions" },
  results_empty: { uz: "Hali javoblar yo'q.", ru: "Ответов пока нет.", en: "No answers yet." },
  attempts: { uz: "Urinishlar", ru: "Попытки", en: "Attempts" },
  not_graded: { uz: "baholanmagan", ru: "без оценки", en: "not graded" },
  language: { uz: "Til", ru: "Язык", en: "Language" },
  phone: { uz: "Telefon", ru: "Телефон", en: "Phone" },
  subscription: { uz: "Obuna", ru: "Подписка", en: "Subscription" },
  no_subscription: { uz: "Obuna yo'q", ru: "Подписки нет", en: "No subscription" },
  payments: { uz: "To'lovlar", ru: "Платежи", en: "Payments" },
  support: { uz: "Yordam", ru: "Поддержка", en: "Support" },
  choose_plan: { uz: "Tarifni tanlang", ru: "Выберите тариф", en: "Choose a plan" },
  days: { uz: "kun", ru: "дн.", en: "days" },
  sum: { uz: "so'm", ru: "сум", en: "UZS" },
  no_plans: { uz: "Tariflar hali qo'shilmagan.", ru: "Тарифы ещё не добавлены.", en: "No plans yet." },
  pay_steps: {
    uz: "1. Quyidagi kartaga to'lov qiling.\n2. To'lov chekining skrinshotini yuklang.\n3. Admin tasdiqlagach, kirish ochiladi.",
    ru: "1. Переведите оплату на карту ниже.\n2. Загрузите скриншот чека.\n3. После проверки админом доступ откроется.",
    en: "1. Pay to the card below.\n2. Upload a screenshot of the receipt.\n3. Access opens once the admin approves it.",
  },
  card: { uz: "Karta raqami", ru: "Номер карты", en: "Card number" },
  holder: { uz: "Karta egasi", ru: "Владелец карты", en: "Card holder" },
  amount: { uz: "Summa", ru: "Сумма", en: "Amount" },
  copy: { uz: "Nusxa", ru: "Копировать", en: "Copy" },
  copied: { uz: "Nusxalandi", ru: "Скопировано", en: "Copied" },
  card_missing: { uz: "To'lov rekvizitlari hali kiritilmagan.", ru: "Реквизиты ещё не указаны.", en: "Payment details are not set yet." },
  upload_receipt: { uz: "Chekni yuklash", ru: "Загрузить чек", en: "Upload receipt" },
  change_file: { uz: "Boshqa fayl", ru: "Другой файл", en: "Choose another file" },
  i_paid: { uz: "To'ladim, yuborish", ru: "Я оплатил, отправить", en: "I paid, send" },
  request_sent: {
    uz: "So'rov yuborildi ({code}). Admin tekshirgach, botga xabar keladi.",
    ru: "Заявка отправлена ({code}). После проверки вы получите сообщение в боте.",
    en: "Request sent ({code}). You'll get a message in the bot once it's reviewed.",
  },
  pending_exists: {
    uz: "So'rovingiz tekshirilmoqda. Iltimos, kuting.",
    ru: "Ваша заявка уже на проверке. Пожалуйста, подождите.",
    en: "Your request is being reviewed. Please wait.",
  },
  pay_rejected: { uz: "Oxirgi to'lov rad etildi: {r}", ru: "Последний платёж отклонён: {r}", en: "Last payment rejected: {r}" },
  st_pending: { uz: "kutilmoqda", ru: "ожидает", en: "pending" },
  st_approved: { uz: "tasdiqlandi", ru: "одобрен", en: "approved" },
  st_rejected: { uz: "rad etildi", ru: "отклонён", en: "rejected" },
  r_amount: { uz: "summa noto'g'ri", ru: "неверная сумма", en: "wrong amount" },
  r_unreadable: { uz: "chek o'qib bo'lmaydi", ru: "чек нечитаемый", en: "receipt unreadable" },
  r_notfound: { uz: "to'lov topilmadi", ru: "платёж не найден", en: "payment not found" },
  r_other: { uz: "boshqa sabab", ru: "другая причина", en: "other reason" },
  blocked_text: {
    uz: "Hisobingiz bloklangan. Yordam uchun murojaat qiling.",
    ru: "Ваш аккаунт заблокирован. Обратитесь в поддержку.",
    en: "Your account is blocked. Please contact support.",
  },
  error: { uz: "Xatolik", ru: "Ошибка", en: "Error" },
} satisfies Record<string, Record<Lang, string>>;

export type Key = keyof typeof S;

export function translate(lang: Lang, key: Key, vars?: Record<string, string | number>): string {
  let s: string = S[key][lang] ?? S[key].uz;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, String(v));
  return s;
}

export const LangContext = createContext<Lang>("uz");

export function useT() {
  const lang = useContext(LangContext);
  return (key: Key, vars?: Record<string, string | number>) => translate(lang, key, vars);
}

export function pick(name: I18n | null | undefined, lang: Lang): string {
  if (!name) return "";
  return name[lang] || name.uz || name.ru || name.en || "";
}

export function useLang() {
  return useContext(LangContext);
}

export const fmtSum = (n: number) => n.toLocaleString("ru-RU").replace(/,/g, " ");
export const fmtDate = (s: string) => {
  const d = new Date(s);
  return `${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`;
};
