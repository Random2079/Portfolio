/*
 * Hold Shift+K or middle mouse (wheel click) → STT daemon → parse mute command.
 */

import {
    extractAction,
    extractVolumeAmount,
    parseSlotOnly,
    parseVoiceCommand,
    DEFAULT_VOLUME_STEP,
    type VoiceAction,
    type VoiceCommand
} from "./parseCommand";
import { removeListenHud, setListenHud } from "./listenHud";

const STT_BASE = "http://127.0.0.1:39281";
const PENDING_ACTION_MS = 12_000;
/** Mouse button: 0=left, 1=middle (колесико), 2=right */
const PTT_MOUSE_BUTTON = 1;

export interface VoiceListenOptions {
    onCommand: (cmd: VoiceCommand, transcript: string) => void;
    onPartial?: (transcript: string) => void;
    onError?: (message: string) => void;
    onListeningChange?: (listening: boolean) => void;
}

export async function voskDaemonAvailable(): Promise<boolean> {
    try {
        const r = await fetch(`${STT_BASE}/health`, { method: "GET" });
        if (!r.ok) return false;
        const j = await r.json();
        return !!j?.ok;
    } catch {
        return false;
    }
}

/** @deprecated name kept for callers — now means vosk daemon up */
export function speechRecognitionAvailable(): boolean {
    return true;
}

export function explainSttError(code: string): string {
    return code;
}

async function postJson(path: string): Promise<any> {
    const r = await fetch(`${STT_BASE}${path}`, {
        method: "POST",
        signal: AbortSignal.timeout(path.includes("stop") ? 15000 : 5000)
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j?.ok === false) {
        throw new Error(j?.error || `HTTP ${r.status}`);
    }
    return j;
}

function formatHearHud(j: {
    transcript?: string;
    free_text?: string;
    peak_rms?: number;
    speech_ms?: number;
    hint?: string;
    clip?: string;
}): string {
    const free = String(j.free_text || "").trim() || "—";
    const cmd = String(j.transcript || "").trim() || "—";
    const rms = Math.round(Number(j.peak_rms ?? 0));
    const ms = Math.round(Number(j.speech_ms ?? 0));
    const hint = String(j.hint || "").trim();
    const clip = j.clip ? "\nWAV сохранён (stt/logs/clips)" : "";
    return (
        `МИК → STT:\n` +
        `  свободно: «${free}»\n` +
        `  команда:  «${cmd}»\n` +
        `rms ${rms} · ${ms}ms` +
        (hint ? `\n${hint}` : "") +
        clip
    );
}

export class VoiceCommandListener {
    private holding = false;
    private holdStartedAt = 0;
    private startedUi = false;
    private busy = false;
    private lastHandled = "";
    private lastHandledAt = 0;
    private hideErrorTimer: number | null = null;
    private partialTimer: number | null = null;
    private pendingAction: VoiceAction | null = null;
    private pendingAmount: number | undefined;
    private pendingActionAt = 0;
    private holdSource: "key" | "mouse" | null = null;
    private readonly opts: VoiceListenOptions;
    private readonly onKeyDown: (e: KeyboardEvent) => void;
    private readonly onKeyUp: (e: KeyboardEvent) => void;
    private readonly onMouseDown: (e: MouseEvent) => void;
    private readonly onMouseUp: (e: MouseEvent) => void;
    private readonly onAuxClick: (e: MouseEvent) => void;

    constructor(opts: VoiceListenOptions) {
        this.opts = opts;
        this.onKeyDown = e => void this.handleKeyDown(e);
        this.onKeyUp = e => void this.handleKeyUp(e);
        this.onMouseDown = e => void this.handleMouseDown(e);
        this.onMouseUp = e => void this.handleMouseUp(e);
        this.onAuxClick = e => {
            if (e.button === PTT_MOUSE_BUTTON) {
                e.preventDefault();
                e.stopPropagation();
            }
        };
    }

    start() {
        window.addEventListener("keydown", this.onKeyDown, true);
        window.addEventListener("keyup", this.onKeyUp, true);
        window.addEventListener("mousedown", this.onMouseDown, true);
        window.addEventListener("mouseup", this.onMouseUp, true);
        window.addEventListener("auxclick", this.onAuxClick, true);
    }

    stop() {
        window.removeEventListener("keydown", this.onKeyDown, true);
        window.removeEventListener("keyup", this.onKeyUp, true);
        window.removeEventListener("mousedown", this.onMouseDown, true);
        window.removeEventListener("mouseup", this.onMouseUp, true);
        window.removeEventListener("auxclick", this.onAuxClick, true);
        this.stopPartialPoll();
        this.holding = false;
        this.holdSource = null;
        this.startedUi = false;
        removeListenHud();
        this.opts.onListeningChange?.(false);
        void postJson("/listen/stop").catch(() => undefined);
    }

    private isTalkHold(e: KeyboardEvent): boolean {
        return e.code === "KeyK" && e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey;
    }

    private fail(message: string) {
        console.warn("[VoiceMuteSlots] STT fail:", message);
        setListenHud("error", message);
        this.opts.onError?.(message);
        this.hideErrorTimer = window.setTimeout(() => setListenHud("idle", ""), 5000);
    }

    private startPartialPoll() {
        this.stopPartialPoll();
        this.partialTimer = window.setInterval(async () => {
            if (!this.holding) return;
            try {
                const r = await fetch(`${STT_BASE}/status`);
                const j = await r.json();
                const p = (j?.partial || "").trim();
                if (p) {
                    const rms = j?.peak_rms ?? j?.last_rms;
                    const quiet = typeof rms === "number" && rms > 0 && rms < 300;
                    const extra = quiet ? "\n(тихо — громче / другой mic)" : "";
                    setListenHud("listening", `СЛЫШУ:\n«${p}»${extra}`);
                    this.opts.onPartial?.(p);
                }
            } catch {
                /* ignore */
            }
        }, 250);
    }

    private stopPartialPoll() {
        if (this.partialTimer != null) {
            window.clearInterval(this.partialTimer);
            this.partialTimer = null;
        }
    }

    private async handleKeyDown(e: KeyboardEvent) {
        if (!this.isTalkHold(e)) return;
        if (e.repeat) return;
        e.preventDefault();
        e.stopPropagation();
        await this.beginHold("key");
    }

    private async handleKeyUp(e: KeyboardEvent) {
        if (e.code !== "KeyK" && e.key !== "Shift") return;
        if (this.holdSource !== "key") return;
        await this.endHold();
    }

    private async handleMouseDown(e: MouseEvent) {
        if (e.button !== PTT_MOUSE_BUTTON) return;
        e.preventDefault();
        e.stopPropagation();
        await this.beginHold("mouse");
    }

    private async handleMouseUp(e: MouseEvent) {
        if (e.button !== PTT_MOUSE_BUTTON) return;
        if (this.holdSource !== "mouse") return;
        e.preventDefault();
        e.stopPropagation();
        await this.endHold();
    }

    private async beginHold(source: "key" | "mouse") {
        if (this.busy || this.holding) return;

        this.holding = true;
        this.holdSource = source;
        this.holdStartedAt = Date.now();
        this.startedUi = true;
        if (this.hideErrorTimer != null) {
            window.clearTimeout(this.hideErrorTimer);
            this.hideErrorTimer = null;
        }

        const bind = source === "mouse" ? "колёсико" : "Shift+K";
        const pendingHint =
            this.pendingAction != null && Date.now() - this.pendingActionAt < PENDING_ACTION_MS
                ? `\nЖду: «первого» / «пятого» / «всех»`
                : `\nSTT · «уменьши звук пятого» / «замутить»`;
        setListenHud("listening", `СЛУШАЮ… (${bind})${pendingHint}`);
        this.opts.onListeningChange?.(true);
        console.info("[VoiceMuteSlots] PTT down", source);

        try {
            await postJson("/listen/start");
            this.startPartialPoll();
        } catch (err) {
            this.holding = false;
            this.holdSource = null;
            this.fail(
                `STT daemon не запущен.\nЗапусти launch\\Start-VoiceStt.ps1 -ForceRestart\n(${String(err)})`
            );
            this.opts.onListeningChange?.(false);
        }
    }

    private async endHold() {
        if (!this.holding && !this.startedUi) return;
        if (this.busy) return;

        this.holding = false;
        this.holdSource = null;
        this.stopPartialPoll();
        this.busy = true;
        console.info("[VoiceMuteSlots] PTT up → /listen/stop");

        try {
            setListenHud("listening", "Обрабатываю…");
            const j = await postJson("/listen/stop");
            // Nested with global PTT — real decode happens on the other release
            if (j?.deferred) {
                console.info("[VoiceMuteSlots] stop deferred (global PTT still holding mic)");
                setListenHud("idle", "");
                this.opts.onListeningChange?.(false);
                this.startedUi = false;
                return;
            }
            const transcript = String(j?.transcript || "").trim();
            const free = String(j?.free_text || "").trim();
            const peak = Number(j?.peak_rms ?? 0);
            const holdMs = this.holdStartedAt ? Date.now() - this.holdStartedAt : 0;
            console.info("[VoiceMuteSlots] HEARD free=", free, "cmd=", transcript, "rms=", peak, "holdMs=", holdMs);

            if (!transcript) {
                setListenHud("error", formatHearHud(j));
                this.hideErrorTimer = window.setTimeout(() => setListenHud("idle", ""), 6000);
                this.opts.onListeningChange?.(false);
                this.startedUi = false;
                return;
            }
            setListenHud("listening", formatHearHud(j));
            this.tryHandle(transcript, free);
        } catch (err) {
            this.fail(`Stop STT: ${String(err)}`);
            this.opts.onListeningChange?.(false);
        } finally {
            this.busy = false;
            this.startedUi = false;
            window.setTimeout(() => {
                if (!this.holding) this.opts.onListeningChange?.(false);
            }, 800);
        }
    }

    private tryHandle(transcript: string, freeText = "") {
        const cmd = parseVoiceCommand(transcript);
        if (cmd) {
            this.pendingAction = null;
            this.pendingAmount = undefined;
            this.pendingActionAt = 0;
            this.dispatch(cmd, transcript, freeText);
            return;
        }

        const action = extractAction(transcript);
        const slot = parseSlotOnly(transcript);
        const amount = extractVolumeAmount(transcript) ?? undefined;
        const now = Date.now();
        const pendingFresh =
            this.pendingAction != null && now - this.pendingActionAt < PENDING_ACTION_MS;

        if (pendingFresh && slot != null) {
            const act = action ?? this.pendingAction!;
            const amt =
                amount ??
                this.pendingAmount ??
                (act === "vol_up" || act === "vol_down" ? DEFAULT_VOLUME_STEP : undefined);
            this.pendingAction = null;
            this.pendingAmount = undefined;
            this.pendingActionAt = 0;
            this.dispatch({ action: act, slot, amount: amt, raw: transcript }, transcript, freeText);
            return;
        }

        if (action && !slot) {
            this.pendingAction = action;
            this.pendingAmount =
                amount ??
                (action === "vol_up" || action === "vol_down" ? DEFAULT_VOLUME_STEP : undefined);
            this.pendingActionAt = now;
            const verb =
                action === "mute"
                    ? "замутить"
                    : action === "unmute"
                      ? "размутить"
                      : action === "hide_video"
                        ? "убрать видео"
                        : action === "show_video"
                          ? "вернуть видео"
                          : action === "vol_up"
                            ? `увеличь${this.pendingAmount != null ? ` на ${this.pendingAmount}` : ""}`
                            : action === "vol_down"
                              ? `уменьши${this.pendingAmount != null ? ` на ${this.pendingAmount}` : ""}`
                              : action === "vol_set"
                                ? `громкость${this.pendingAmount != null ? ` ${this.pendingAmount}` : ""}`
                                : action;
            console.info("[VoiceMuteSlots] STT:", transcript, "→ pending", action, "amt=", this.pendingAmount, "free=", freeText);
            setListenHud(
                "listening",
                `свободно: «${freeText || "—"}»\n${verb} — ок.\n` +
                    `ЕЩЁ РАЗ колёсико/Shift+K — ТОЛЬКО: «первого» / «всех» / «последнего»\n` +
                    `(или одним: «уменьши звук пятого»)`
            );
            this.hideErrorTimer = window.setTimeout(() => {
                if (this.pendingAction === action) {
                    this.pendingAction = null;
                    this.pendingAmount = undefined;
                    setListenHud("idle", "");
                }
            }, PENDING_ACTION_MS);
            return;
        }

        if (slot != null && !action && !pendingFresh) {
            const slotLabel = slot === "all" ? "ALL" : slot === "last" ? "LAST" : `#${slot}`;
            console.info("[VoiceMuteSlots] STT:", transcript, "→ slot only, no pending verb");
            setListenHud(
                "error",
                `свободно: «${freeText || "—"}»\nкоманда: «${transcript}» (${slotLabel})\nСначала «замутить» / «увеличь», потом слот`
            );
            this.hideErrorTimer = window.setTimeout(() => setListenHud("idle", ""), 5000);
            return;
        }

        console.info("[VoiceMuteSlots] STT:", transcript, "→ no command", "free=", freeText);
        setListenHud(
            "error",
            `свободно: «${freeText || "—"}»\nкоманда: «${transcript}»\nне хватает слота/глагола`
        );
        this.hideErrorTimer = window.setTimeout(() => setListenHud("idle", ""), 5000);
    }

    private dispatch(cmd: VoiceCommand, transcript: string, freeText = "") {
        const key = `${cmd.action}:${cmd.slot}:${cmd.amount ?? ""}`;
        const now = Date.now();
        if (key === this.lastHandled && now - this.lastHandledAt < 1500) return;
        this.lastHandled = key;
        this.lastHandledAt = now;

        const label =
            cmd.action === "mute"
                ? "МУТ"
                : cmd.action === "unmute"
                  ? "РАЗМУТ"
                  : cmd.action === "hide_video"
                    ? "БЕЗ ВИДЕО"
                    : cmd.action === "show_video"
                      ? "ВИДЕО ВКЛ"
                      : cmd.action === "vol_up"
                        ? `+${cmd.amount ?? DEFAULT_VOLUME_STEP}%`
                        : cmd.action === "vol_down"
                          ? `−${cmd.amount ?? DEFAULT_VOLUME_STEP}%`
                          : cmd.action === "vol_set"
                            ? `=${cmd.amount ?? "?"}%`
                            : cmd.action;
        const target = cmd.slot === "all" ? "ВСЕХ" : cmd.slot === "last" ? "ПОСЛЕДНЕГО" : `#${cmd.slot}`;
        setListenHud(
            "heard",
            `${label} ${target}\n` +
                `свободно: «${freeText || "—"}»\n` +
                `команда: «${transcript}»`
        );
        window.setTimeout(() => {
            if (!this.holding) setListenHud("idle", "");
        }, 3500);
        console.info("[VoiceMuteSlots] STT:", transcript, "→", `${cmd.action} ${target}`, "amt=", cmd.amount, "free=", freeText);
        this.opts.onCommand(cmd, transcript);
    }
}
