/*
 * Parse spoken mute commands. Слот — словом (первый, второго, три) или цифрой.
 * Vosk: «замутить»→«замучить». В JS \b и \w ломают кириллицу — не использовать.
 */

export type VoiceAction =
    | "mute"
    | "unmute"
    | "hide_video"
    | "show_video"
    | "vol_up"
    | "vol_down"
    | "vol_set";

/** 1..N — слот; "all" — все кроме себя; "last" — последний в сайдбаре (не я). */
export type VoiceSlotTarget = number | "all" | "last";

export interface VoiceCommand {
    action: VoiceAction;
    slot: VoiceSlotTarget;
    /** Discord local volume units 0..200 (100 = 100%). Relative for up/down, absolute for set. */
    amount?: number;
    raw: string;
}

const NUM_WORDS: Record<string, number> = {
    один: 1, одна: 1, одно: 1, одного: 1, одному: 1, одним: 1, одном: 1, одной: 1,
    перв: 1, первый: 1, первая: 1, первое: 1, первого: 1, первому: 1, первым: 1, первом: 1, первую: 1, первой: 1, первые: 1, первых: 1,
    два: 2, две: 2, двух: 2, двум: 2, двумя: 2, двое: 2,
    второй: 2, вторая: 2, второе: 2, второго: 2, второму: 2, вторым: 2, втором: 2, вторую: 2, вторых: 2,
    три: 3, трех: 3, трёх: 3, трем: 3, трём: 3, тремя: 3, трое: 3,
    третий: 3, третья: 3, третье: 3, третьего: 3, третьему: 3, третьим: 3, третьем: 3, третью: 3, третьих: 3,
    четыре: 4, четырех: 4, четырёх: 4, четырем: 4, четырьмя: 4, четверо: 4,
    четвертый: 4, четвертая: 4, четвертое: 4, четвертого: 4, четвертому: 4, четвертым: 4, четвертом: 4, четвертую: 4,
    пять: 5, пяти: 5, пятью: 5, пятеро: 5,
    пятый: 5, пятая: 5, пятое: 5, пятого: 5, пятому: 5, пятым: 5, пятом: 5, пятую: 5,
    шесть: 6, шести: 6, шестью: 6, шестеро: 6,
    шестой: 6, шестая: 6, шестое: 6, шестого: 6, шестому: 6, шестым: 6, шестом: 6, шестую: 6,
    семь: 7, семи: 7, семью: 7,
    седьмой: 7, седьмая: 7, седьмое: 7, седьмого: 7, седьму: 7, седьмым: 7, седьмом: 7, седьмую: 7,
    восемь: 8, восьми: 8, восемью: 8, восьмеро: 8,
    восьмой: 8, восьмая: 8, восьмое: 8, восьмого: 8, восьмому: 8, восьмым: 8, восьмом: 8, восьмую: 8,
    девять: 9, девяти: 9, девятью: 9,
    девятый: 9, девятая: 9, девятое: 9, девятого: 9, девятому: 9, девятым: 9, девятом: 9, девятую: 9,
    десять: 10, десяти: 10, десятью: 10, десятеро: 10,
    десятый: 10, десятая: 10, десятое: 10, десятого: 10,
    одиннадцать: 11, одиннадцати: 11,
    двенадцать: 12, двенадцати: 12
};

/** Порядковые корни — vosk часто режет окончания. */
const ORDINAL_STEMS: { re: RegExp; slot: number }[] = [
    { re: /(^|\s)перв[\p{L}]*($|\s)/u, slot: 1 },
    { re: /(^|\s)один[\p{L}]*($|\s)/u, slot: 1 },
    { re: /(^|\s)одн[\p{L}]*($|\s)/u, slot: 1 },
    { re: /(^|\s)втор[\p{L}]*($|\s)/u, slot: 2 },
    { re: /(^|\s)дв[\p{L}]{2,}($|\s)/u, slot: 2 },
    { re: /(^|\s)трет[\p{L}]*($|\s)/u, slot: 3 },
    { re: /(^|\s)тр[\p{L}]{2,}($|\s)/u, slot: 3 },
    { re: /(^|\s)четвер[\p{L}]*($|\s)/u, slot: 4 },
    { re: /(^|\s)четыр[\p{L}]*($|\s)/u, slot: 4 },
    { re: /(^|\s)пят[\p{L}]*($|\s)/u, slot: 5 },
    { re: /(^|\s)шест[\p{L}]*($|\s)/u, slot: 6 },
    { re: /(^|\s)седьм[\p{L}]*($|\s)/u, slot: 7 },
    { re: /(^|\s)сем[\p{L}]*($|\s)/u, slot: 7 },
    { re: /(^|\s)восьм[\p{L}]*($|\s)/u, slot: 8 },
    { re: /(^|\s)девят[\p{L}]*($|\s)/u, slot: 9 },
    { re: /(^|\s)десят[\p{L}]*($|\s)/u, slot: 10 }
];

const NUM_WORDS_SORTED = Object.entries(NUM_WORDS).sort((a, b) => b[0].length - a[0].length);

const MUTE_STEM =
    /(замуч|замут|замьют|мьют|мутн|mute|затк|завал|заглуш|глушн)[\p{L}\p{N}]*/iu;

const UNMUTE_STEM =
    /(размуч|размут|размьют|анмьют|unmute|открой|разглуш|включи\s*звук|сними\s*мут)[\p{L}\p{N}]*/iu;

/** Протокол «раз… → unmute». */
const UNMUTE_R_HINT = /(^|\s)(раз[\p{L}]{0,14}|unmute)($|\s)/iu;

const VOL_UP_RE =
    /(увелич|громче|погромче|прибав|добавь\s*(звук|громк)|прибавь\s*(звук|громк)|volume\s*up|louder|(^|\s)звук\s*громче)/iu;
const VOL_DOWN_RE =
    /(уменьш|меньше|убав|тише|потише|приглуш|убери\s*(звук|громк)|сбав|volume\s*down|quieter|(^|\s)звук\s*тише)/iu;
const VOL_SET_RE =
    /(^|\s)(громкость|поставь\s*громкость|выставь\s*громкость|сделай\s*громкость|volume)($|\s)/iu;

/** Протокол «слово на З → mute» — не цеплять «звук». */
const MUTE_Z_HINT = /(^|\s)(?!раз|звук)(з[\p{L}]{0,10})($|\s)/iu;

/** Убрать/вернуть чужое видео локально. */
const HIDE_VIDEO_RE =
    /((убери|скрой|выключ|отключ|без|закры)\s*(видео|камер|стрим))|((видео|камер|стрим)\s*(убери|скрой|выключ|отключ))|(^|\s)(видео|камера|камеру|стрим)($|\s)/iu;
const SHOW_VIDEO_RE =
    /((верни|покажи|открой)\s*(видео|камер|стрим))|((видео|камер)\s*(верни|покажи|включ))/iu;

/** Проценты / шаги громкости (не слоты). */
const AMOUNT_WORDS: Record<string, number> = {
    ноль: 0,
    минимум: 0,
    десять: 10,
    двадцать: 20,
    тридцать: 30,
    сорок: 40,
    пятьдесят: 50,
    половину: 50,
    половина: 50,
    шестьдесят: 60,
    семьдесят: 70,
    восемьдесят: 80,
    девяносто: 90,
    сто: 100,
    полный: 100,
    полная: 100,
    максимум: 200,
    двести: 200
};

export const DEFAULT_VOLUME_STEP = 25;
export const VOLUME_MIN = 0;
export const VOLUME_MAX = 200;

function looksLikeMuteIntent(s: string): boolean {
    if (MUTE_STEM.test(s)) return true;
    return MUTE_Z_HINT.test(` ${s} `);
}

function looksLikeUnmuteIntent(s: string): boolean {
    if (UNMUTE_STEM.test(s)) return true;
    return UNMUTE_R_HINT.test(` ${s} `);
}

function extractVideoAction(s: string): "hide_video" | "show_video" | null {
    if (SHOW_VIDEO_RE.test(s)) return "show_video";
    // «видео второго» / «убери камеру третьего» — hide (не путать с «верни видео»)
    if (HIDE_VIDEO_RE.test(s)) return "hide_video";
    return null;
}

function extractVolumeAction(s: string): "vol_up" | "vol_down" | "vol_set" | null {
    // «увеличь звук пятого» / «громче второго»
    if (VOL_UP_RE.test(s)) return "vol_up";
    // «уменьши звук пятого» / «тише третьего»
    if (VOL_DOWN_RE.test(s)) return "vol_down";
    // «громкость 100 второго» / «звук сто» — явная установка
    if (VOL_SET_RE.test(s) && extractVolumeAmount(s) != null) return "vol_set";
    return null;
}

function amountTokenToNumber(token: string): number | null {
    const t = token.trim().toLowerCase().replace(/ё/g, "е");
    if (!t) return null;
    if (/^\d{1,3}$/.test(t)) {
        const n = parseInt(t, 10);
        return n >= 0 && n <= VOLUME_MAX ? n : null;
    }
    return AMOUNT_WORDS[t] ?? null;
}

/** «на 50», «100%», «замутить 50», «сто процентов». */
export function extractVolumeAmount(text: string): number | null {
    const s = normalize(text);
    if (!s) return null;

    const na = s.match(/(?:^|\s)на\s+([\p{L}\p{N}]+)\s*(?:процент(?:ов|а)?|%)?/u);
    if (na) {
        const n = amountTokenToNumber(na[1]!);
        if (n != null) return n;
    }

    const pct = s.match(/(?:^|\s)(\d{1,3})\s*(?:процент(?:ов|а)?|%)(?:$|\s)/u);
    if (pct) {
        const n = parseInt(pct[1]!, 10);
        if (n >= 0 && n <= VOLUME_MAX) return n;
    }

    // «замутить 50» / «мьют пятьдесят» — больше НЕ громкость (юзер: только уменьши/увеличь звук)
    // цифры % только через «на N» / «громкость N» / «N%»

    for (const [word, n] of Object.entries(AMOUNT_WORDS).sort((a, b) => b[0].length - a[0].length)) {
        const re = new RegExp(`(^|\\s)${word}($|\\s)`, "u");
        if (re.test(s)) return n;
    }

    // «громкость 100» / «звук 80» — цифра рядом с громкость
    const near = s.match(/(?:громкость|volume)\s+(\d{1,3})/u);
    if (near) {
        const n = parseInt(near[1]!, 10);
        if (n >= 0 && n <= VOLUME_MAX) return n;
    }

    return null;
}

/** Убрать число громкости, чтобы «на 50» не стало слотом 5 / 50. */
function stripVolumeAmountPhrases(s: string): string {
    let out = s;
    out = out.replace(/(?:^|\s)на\s+[\p{L}\p{N}]+\s*(?:процент(?:ов|а)?|%)?/gu, " ");
    out = out.replace(/(?:^|\s)\d{1,3}\s*(?:процент(?:ов|а)?|%)(?:$|\s)/gu, " ");
    out = out.replace(/(?:громкость|volume)\s+\d{1,3}/gu, " ");
    // «уменьши звук пятого» — «звук/громкость» не слот
    out = out.replace(/(^|\s)(звук|громкость|volume)($|\s)/gu, " ");
    for (const word of Object.keys(AMOUNT_WORDS)) {
        if (word.length < 3) continue;
        out = out.replace(new RegExp(`(^|\\s)${word}($|\\s)`, "gu"), " ");
    }
    return out.replace(/\s+/g, " ").trim();
}

function normalize(text: string): string {
    const base = text
        .toLowerCase()
        .replace(/ё/g, "е")
        .replace(/[^\p{L}\p{N}\s]+/gu, " ")
        .replace(/\s+/g, " ")
        .trim();
    return canonicalizeAsrGlitches(base);
}

/**
 * Parakeet часто коверкает mute/unmute на коротком PTT.
 * Правки только лексики команд — не свободной речи.
 */
function canonicalizeAsrGlitches(s: string): string {
    if (!s) return s;
    let t = s;
    // unmute: Размучься / Размочься / Разумче / Размой / Размо / Развод / Rozmot
    t = t.replace(
        /(^|\s)(размуч[\p{L}]*|размоч[\p{L}]*|разумч[\p{L}]*|размой[\p{L}]*|размо[\p{L}]*|развод[\p{L}]*|rozmot[\p{L}]*)($|\s)/gu,
        "$1размутить$3"
    );
    // mute: Завучь / Забудь / Замок / Заводчик / Звонить / За моч / Муч
    t = t.replace(
        /(^|\s)(завуч[\p{L}]*|забудь[\p{L}]*|замок[\p{L}]*|заводчик[\p{L}]*|заводч[\p{L}]*|звонит[\p{L}]*|замоч[\p{L}]*|муч[\p{L}]*)($|\s)/gu,
        "$1замутить$3"
    );
    t = t.replace(/(^|\s)за\s+моч($|\s)/gu, "$1замутить$2");
    // Parakeet UA garble «За моїм» ≈ mute last
    t = t.replace(/(^|\s)за\s+мо[їі]м($|\s)/gu, "$1замутить последнего$2");
    // «Помочь все» ≈ «замутить всех»
    t = t.replace(/(^|\s)помочь\s+(все|всех)($|\s)/gu, "$1замутить всех$3");
    // «Пер» / «пер» обрезок первого после глагола
    t = t.replace(/(замутить|размутить)\s+пер($|\s)/gu, "$1 первого$2");
    return t.replace(/\s+/g, " ").trim();
}

function isVerbToken(token: string): boolean {
    return (
        MUTE_STEM.test(token) ||
        UNMUTE_STEM.test(token) ||
        UNMUTE_R_HINT.test(` ${token} `) ||
        VOL_UP_RE.test(token) ||
        VOL_DOWN_RE.test(token) ||
        /^(видео|камера|камеру|стрим|громкость|звук|volume|на|процент|процентов|всех|все|всем|последн[\p{L}]*)$/iu.test(
            token
        )
    );
}

function tokenToSlot(token: string): number | null {
    const t = token.trim().toLowerCase().replace(/ё/g, "е");
    if (!t) return null;
    if (/^\d{1,2}$/.test(t)) {
        const n = parseInt(t, 10);
        return n >= 1 && n <= 20 ? n : null;
    }
    if (NUM_WORDS[t] != null) return NUM_WORDS[t]!;

    let best: { n: number; len: number } | null = null;
    for (const [word, n] of Object.entries(NUM_WORDS)) {
        if (word.length < 3) continue;
        if (t.startsWith(word) || (t.length >= 3 && word.startsWith(t))) {
            if (!best || word.length > best.len) best = { n, len: word.length };
        }
    }
    return best?.n ?? null;
}

/** Слот словом или цифрой — приоритет словам после глагола. */
export function extractSlot(text: string): number | null {
    const s = normalize(text);
    if (!s) return null;

    // «слот три» / «номер первый»
    const labeled = s.match(/(?:слот|номер|num(?:ber)?)\s+([\p{L}\p{N}]+)/iu);
    if (labeled) {
        const n = tokenToSlot(labeled[1]!);
        if (n) return n;
    }

    // цифра 1-20 (если всё же скажешь)
    const digit = s.match(/(?:^|\s)([1-9]|1[0-9]|20)(?:$|\s)/);
    if (digit) return parseInt(digit[1]!, 10);

    // по токенам (после глагола обычно)
    const tokens = s.split(" ").filter(Boolean);
    for (const token of tokens) {
        if (isVerbToken(token)) continue;
        const n = tokenToSlot(token);
        if (n) return n;
    }

    // целое слово в тексте (длинные формы перв)
    for (const [word, n] of NUM_WORDS_SORTED) {
        if (word.length < 3) continue;
        const re = new RegExp(`(^|\\s)${word}($|\\s)`, "iu");
        if (re.test(s)) return n;
    }

    // корни: первый/первого/первую…
    for (const { re, slot } of ORDINAL_STEMS) {
        if (re.test(` ${s} `)) return slot;
    }

    // Whisper часто склеивает: «замутрипервого» / «замутьвторого»
    const glued = s.match(
        /заму[тчс][\p{L}]*?(перв|втор|трет|четвер|четыр|пят|шест|седьм|сем|восьм|девят|десят)[\p{L}]*/iu
    );
    if (glued) {
        const n = tokenToSlot(glued[1]!);
        if (n) return n;
        for (const { re, slot } of ORDINAL_STEMS) {
            if (re.test(` ${glued[1]} `)) return slot;
        }
    }

    return null;
}

/** Слот / всех / последнего. */
export function extractSlotTarget(text: string): VoiceSlotTarget | null {
    const s = normalize(text);
    if (!s) return null;

    // «всех» + частые ослышки Whisper / склейки с глаголом
    if (
        /(^|\s)(всех|все|всем|всеми|всехх|фсех|весь|вес|everybody|everyone|all)($|\s)/u.test(s) ||
        /((за|раз)му[тчс][\p{L}]*|unmute)[\p{L}]*?(всех|все|всем|фсех)/iu.test(s)
    ) {
        return "all";
    }
    if (
        /(^|\s)(последн[\p{L}]*|last)($|\s)/u.test(s) ||
        /((за|раз)му[тчс][\p{L}]*|unmute)[\p{L}]*?последн/iu.test(s)
    ) {
        return "last";
    }
    return extractSlot(s);
}

/** Только глагол — «замутить» / «увеличь» / «видео» без слота. */
export function extractAction(text: string): VoiceAction | null {
    const s = normalize(text);
    if (!s) return null;

    const video = extractVideoAction(s);
    if (video) return video;

    const vol = extractVolumeAction(s);
    if (vol) return vol;

    const unmute = looksLikeUnmuteIntent(s);
    const mute = looksLikeMuteIntent(s);
    if (unmute && !mute) return "unmute";
    if (mute && !unmute) return "mute";
    if (unmute && mute) {
        const ui = s.search(/раз/iu);
        const mi = s.search(/(^|\s)з/iu);
        if (ui >= 0 && (mi < 0 || ui <= mi)) return "unmute";
        return "mute";
    }
    return null;
}

/** Слот без глагола — «первого», «всех», «последнего». */
export function parseSlotOnly(text: string): VoiceSlotTarget | null {
    return extractSlotTarget(stripVolumeAmountPhrases(normalize(text)));
}

export function parseVoiceCommand(text: string): VoiceCommand | null {
    if (!text?.trim()) return null;
    const raw = text.trim();
    const s = normalize(raw);

    const action = extractAction(s);
    if (!action) return null;

    const amount = extractVolumeAmount(s) ?? undefined;
    const forSlot =
        action === "vol_up" || action === "vol_down" || action === "vol_set" || amount != null
            ? stripVolumeAmountPhrases(s)
            : s;
    // Short Parakeet clips often drop the slot word («Замок.») — default last other.
    let slot = extractSlotTarget(forSlot);
    if (slot == null && (action === "mute" || action === "unmute")) {
        slot = "last";
    }
    if (slot == null) return null;

    if (action === "vol_set" && amount == null) return null;

    return {
        action,
        slot,
        amount:
            action === "vol_up" || action === "vol_down"
                ? amount ?? DEFAULT_VOLUME_STEP
                : amount,
        raw
    };
}

export function formatVoiceCommand(cmd: VoiceCommand | null): string {
    if (!cmd) return "UNKNOWN";
    const t = cmd.slot === "all" ? "ALL" : cmd.slot === "last" ? "LAST" : `#${cmd.slot}`;
    const amt =
        cmd.amount != null && (cmd.action === "vol_up" || cmd.action === "vol_down" || cmd.action === "vol_set")
            ? ` ${cmd.amount}`
            : "";
    return `${cmd.action.toUpperCase()}${amt} ${t}`;
}

export function slotToSpokenHint(slot: number): string {
    const hints: Record<number, string> = {
        1: "первого",
        2: "второго",
        3: "третьего",
        4: "четвертого",
        5: "пятого",
        6: "шестого",
        7: "седьмого",
        8: "восьмого",
        9: "девятого",
        10: "десятого"
    };
    return hints[slot] ?? String(slot);
}
