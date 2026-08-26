/*
 * VoiceMuteSlots — IDEA-005
 * A/B: slots + /mute-slot
 * C: Shift+K → offline Vosk daemon (localhost) → «заткни N»
 */

import { ApplicationCommandInputType, ApplicationCommandOptionType, findOption } from "@api/Commands";
import { definePluginSettings } from "@api/Settings";
import definePlugin, { OptionType } from "@utils/types";
import type { VoiceState } from "@vencord/discord-types";
import { Toasts, showToast } from "@webpack/common";

import {
    adjustLocalVolumeAllOthers,
    adjustLocalVolumeSlot,
    formatBulkMuteResult,
    formatBulkVolumeResult,
    formatMuteResult,
    formatVolumeResult,
    hideLocalVideoSlot,
    muteAllOthers,
    muteVoiceSlot,
    resolveLastOtherSlot,
    showLocalVideoSlot,
    unmuteAllOthers,
    unmuteVoiceSlot
} from "./localMute";
import { DEFAULT_VOLUME_STEP, parseVoiceCommand, type VoiceCommand } from "./parseCommand";
import {
    formatSnapshotLog,
    formatSnapshotToast,
    getVoiceSnapshot,
    snapshotFingerprint,
    type VoiceSnapshot
} from "./voiceMembers";
import { VoiceCommandListener, voskDaemonAvailable } from "./voiceListen";
import { GlobalCommandPoller } from "./globalCommandPoll";

const TOAST_COOLDOWN_MS = 2000;
let lastFingerprint = "";
let lastToastAt = 0;
let voiceListener: VoiceCommandListener | null = null;
let globalPoller: GlobalCommandPoller | null = null;
let lastCmdKey = "";
let lastCmdAt = 0;

const settings = definePluginSettings({
    voiceCommands: {
        type: OptionType.BOOLEAN,
        description: "Голос: колёсико / Shift+K (глобально через STT-демон, можно из игры)",
        default: true
    },
    localPttAlso: {
        type: OptionType.BOOLEAN,
        description: "Также PTT внутри окна Discord (обычно ВЫКЛ — иначе гонка с глобальным колёсиком)",
        default: false
    }
});

function publishSnapshot(snap: VoiceSnapshot, opts?: { forceToast?: boolean }) {
    const fp = snapshotFingerprint(snap);
    if (fp === lastFingerprint && !opts?.forceToast) return;
    lastFingerprint = fp;

    const line = formatSnapshotLog(snap);
    console.info("[VoiceMuteSlots]", line);

    const now = Date.now();
    if (opts?.forceToast || now - lastToastAt >= TOAST_COOLDOWN_MS) {
        lastToastAt = now;
        showToast(formatSnapshotToast(snap), Toasts.Type.MESSAGE);
    }
}

function runMuteSlot(slotNumber: number) {
    const result = muteVoiceSlot(slotNumber);
    const msg = formatMuteResult(result);
    showToast(msg, result.ok ? Toasts.Type.SUCCESS : Toasts.Type.FAILURE);
    console.info("[VoiceMuteSlots]", msg);
}

function runUnmuteSlot(slotNumber: number) {
    const result = unmuteVoiceSlot(slotNumber);
    const msg = formatMuteResult(result);
    showToast(msg, result.ok ? Toasts.Type.SUCCESS : Toasts.Type.FAILURE);
    console.info("[VoiceMuteSlots]", msg);
}

function runHideVideoSlot(slotNumber: number) {
    const result = hideLocalVideoSlot(slotNumber);
    const msg = formatMuteResult(result);
    showToast(msg, result.ok ? Toasts.Type.SUCCESS : Toasts.Type.FAILURE);
    console.info("[VoiceMuteSlots]", msg);
}

function runShowVideoSlot(slotNumber: number) {
    const result = showLocalVideoSlot(slotNumber);
    const msg = formatMuteResult(result);
    showToast(msg, result.ok ? Toasts.Type.SUCCESS : Toasts.Type.FAILURE);
    console.info("[VoiceMuteSlots]", msg);
}

function resolveCommandSlot(cmd: VoiceCommand): number | null {
    if (cmd.slot === "all") return null;
    if (cmd.slot === "last") return resolveLastOtherSlot();
    return cmd.slot;
}

function volumeMode(action: VoiceCommand["action"]): "up" | "down" | "set" | null {
    if (action === "vol_up") return "up";
    if (action === "vol_down") return "down";
    if (action === "vol_set") return "set";
    return null;
}

function runVolumeCommand(cmd: VoiceCommand, transcript: string) {
    const mode = volumeMode(cmd.action);
    if (!mode) return false;
    const amount = cmd.amount ?? (mode === "set" ? 100 : DEFAULT_VOLUME_STEP);

    if (cmd.slot === "all") {
        const r = adjustLocalVolumeAllOthers(mode, amount);
        const msg = formatBulkVolumeResult(r);
        showToast(msg, r.ok ? Toasts.Type.SUCCESS : Toasts.Type.FAILURE);
        console.info("[VoiceMuteSlots]", msg, transcript);
        return true;
    }

    const slotNum = resolveCommandSlot(cmd);
    if (slotNum == null) {
        showToast("Нет «последнего» (кроме тебя никого?)", Toasts.Type.FAILURE);
        return true;
    }
    const r = adjustLocalVolumeSlot(slotNum, mode, amount);
    const msg = formatVolumeResult(r);
    showToast(msg, r.ok ? Toasts.Type.SUCCESS : Toasts.Type.FAILURE);
    console.info("[VoiceMuteSlots]", msg, transcript);
    return true;
}

function runVoiceCommand(cmd: VoiceCommand, transcript: string) {
    const key = `${cmd.action}:${cmd.slot}:${cmd.amount ?? ""}`;
    const now = Date.now();
    if (key === lastCmdKey && now - lastCmdAt < 2000) {
        console.info("[VoiceMuteSlots] debounce skip", key);
        return;
    }
    lastCmdKey = key;
    lastCmdAt = now;

    // #region agent log
    fetch("http://127.0.0.1:7708/ingest/ca310e03-4ea0-402d-8e13-c40a02268f81", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "121a69" },
        body: JSON.stringify({
            sessionId: "121a69",
            hypothesisId: "D",
            location: "index.ts:runVoiceCommand",
            message: "run_command",
            data: { action: cmd.action, slot: cmd.slot, amount: cmd.amount ?? null, transcript: transcript.slice(0, 120) },
            timestamp: Date.now()
        })
    }).catch(() => undefined);
    // #endregion

    if (runVolumeCommand(cmd, transcript)) return;

    if (cmd.slot === "all") {
        if (cmd.action === "mute") {
            const r = muteAllOthers();
            const msg = formatBulkMuteResult("mute", r);
            showToast(msg, r.ok ? Toasts.Type.SUCCESS : Toasts.Type.FAILURE);
            console.info("[VoiceMuteSlots]", msg, transcript);
            return;
        }
        if (cmd.action === "unmute") {
            const r = unmuteAllOthers();
            const msg = formatBulkMuteResult("unmute", r);
            showToast(msg, r.ok ? Toasts.Type.SUCCESS : Toasts.Type.FAILURE);
            console.info("[VoiceMuteSlots]", msg, transcript);
            return;
        }
        showToast("«Всех» только для mute/unmute/громкости", Toasts.Type.FAILURE);
        return;
    }

    const slotNum = resolveCommandSlot(cmd);
    if (slotNum == null) {
        showToast("Нет «последнего» (кроме тебя никого?)", Toasts.Type.FAILURE);
        return;
    }

    if (cmd.action === "unmute") runUnmuteSlot(slotNum);
    else if (cmd.action === "hide_video") runHideVideoSlot(slotNum);
    else if (cmd.action === "show_video") runShowVideoSlot(slotNum);
    else runMuteSlot(slotNum);
    console.info("[VoiceMuteSlots] heard:", transcript);
}

async function startVoiceListener() {
    stopVoiceListener();
    if (!settings.store.voiceCommands) return;

    const up = await voskDaemonAvailable();
    if (!up) {
        showToast("STT выключен — launch\\Start-VoiceStt.ps1 -ForceRestart", Toasts.Type.FAILURE);
        console.warn("[VoiceMuteSlots] STT daemon down on :39281");
    } else {
        showToast("STT онлайн — глобально колёсико / Shift+K (и из игры)", Toasts.Type.SUCCESS);
    }

    // Global PTT lives in the Python daemon; plugin only polls the command queue.
    globalPoller = new GlobalCommandPoller({
        onCommand(cmd, transcript) {
            runVoiceCommand(cmd, transcript);
        },
        onRaw(transcript, free) {
            console.info("[VoiceMuteSlots] global heard:", transcript, "free=", free);
        },
        onError(message) {
            showToast(message, Toasts.Type.FAILURE);
        }
    });
    globalPoller.start();

    // #region agent log
    fetch("http://127.0.0.1:7708/ingest/ca310e03-4ea0-402d-8e13-c40a02268f81", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "121a69" },
        body: JSON.stringify({
            sessionId: "121a69",
            hypothesisId: "A",
            location: "index.ts:startVoiceListener",
            message: "listener_boot",
            data: { daemonUp: up, localPttAlso: settings.store.localPttAlso },
            timestamp: Date.now()
        })
    }).catch(() => undefined);
    // #endregion

    if (settings.store.localPttAlso) {
        voiceListener = new VoiceCommandListener({
            onCommand(cmd, transcript) {
                runVoiceCommand(cmd, transcript);
            },
            onPartial(t) {
                console.info("[VoiceMuteSlots] partial:", t);
            },
            onError(message) {
                showToast(message.split("\n")[0] ?? message, Toasts.Type.FAILURE);
                console.warn("[VoiceMuteSlots] STT error:", message);
            },
            onListeningChange(listening) {
                console.info("[VoiceMuteSlots] listening=", listening);
            }
        });
        voiceListener.start();
        console.info("[VoiceMuteSlots] local Discord PTT also on");
    }

    console.info("[VoiceMuteSlots] polling global PTT commands from :39281");
}

function stopVoiceListener() {
    voiceListener?.stop();
    voiceListener = null;
    globalPoller?.stop();
    globalPoller = null;
}

export default definePlugin({
    name: "VoiceMuteSlots",
    description: "Local mute by slot — offline Vosk voice (Shift+K) + /mute-slot (IDEA-005)",
    authors: [{ name: "Te Yan", id: 0n }],
    dependencies: ["CommandsAPI"],
    settings,

    start() {
        console.info("[VoiceMuteSlots] loaded");
        void startVoiceListener();
        const snap = getVoiceSnapshot();
        if (snap?.inVoice) {
            publishSnapshot(snap, { forceToast: true });
        }
    },

    stop() {
        stopVoiceListener();
        lastFingerprint = "";
    },

    flux: {
        VOICE_STATE_UPDATES(_payload: { voiceStates: VoiceState[] }) {
            const snap = getVoiceSnapshot();
            if (!snap) return;
            publishSnapshot(snap);
        }
    },

    commands: [
        {
            inputType: ApplicationCommandInputType.BUILT_IN,
            name: "voice-slots",
            description: "Show voice channel slots (lobby, me, others)",
            execute() {
                const snap = getVoiceSnapshot();
                if (!snap?.inVoice) {
                    showToast("Not in voice", Toasts.Type.FAILURE);
                    return;
                }
                publishSnapshot(snap, { forceToast: true });
            }
        },
        {
            inputType: ApplicationCommandInputType.BUILT_IN,
            name: "mute-slot",
            description: "Local mute by slot number",
            options: [
                {
                    name: "slot",
                    description: "Slot 1..N",
                    type: ApplicationCommandOptionType.INTEGER,
                    required: true
                }
            ],
            execute(options) {
                const slot = findOption(options, "slot", 0);
                if (!slot || slot < 1) {
                    showToast("Укажи слот: /mute-slot slot:1", Toasts.Type.FAILURE);
                    return;
                }
                runMuteSlot(slot);
            }
        },
        {
            inputType: ApplicationCommandInputType.BUILT_IN,
            name: "parse-voice",
            description: "Тест парсера без микрофона",
            options: [
                {
                    name: "text",
                    description: "заткни три",
                    type: ApplicationCommandOptionType.STRING,
                    required: true
                }
            ],
            execute(options) {
                const text = findOption(options, "text", "");
                const cmd = parseVoiceCommand(text);
                if (!cmd) {
                    showToast(`Не распознал: «${text}»`, Toasts.Type.FAILURE);
                    return;
                }
                runVoiceCommand(cmd, text);
            }
        },
        {
            inputType: ApplicationCommandInputType.BUILT_IN,
            name: "stt-check",
            description: "Проверка офлайн Vosk daemon :39281",
            async execute() {
                try {
                    const r = await fetch("http://127.0.0.1:39281/health");
                    if (!r.ok) throw new Error(`HTTP ${r.status}`);
                    const h = await r.json();
                    const lr = await fetch("http://127.0.0.1:39281/log").catch(() => null);
                    const lj = lr?.ok ? await lr.json() : null;
                    const tail = (lj?.lines as string[] | undefined)?.slice(-3).join(" | ") ?? "";
                    const msg = `Vosk OK · mic: ${h.device ?? "?"} · gain ${h.gain ?? "?"} · grammar ${h.grammar ? "on" : "off"}`;
                    showToast(msg, Toasts.Type.SUCCESS);
                    console.info("[VoiceMuteSlots]", msg, "\nlog:", h.log, tail ? `\nlast: ${tail}` : "");
                } catch {
                    const msg = "Vosk НЕ запущен — launch\\Start-VoiceStt.ps1";
                    showToast(msg, Toasts.Type.FAILURE);
                    console.info("[VoiceMuteSlots]", msg);
                }
            }
        },
        {
            inputType: ApplicationCommandInputType.BUILT_IN,
            name: "stt-last",
            description: "Что услышал мик в последний Shift+K (free + команда)",
            async execute() {
                try {
                    const r = await fetch("http://127.0.0.1:39281/last");
                    const j = await r.json();
                    const free = j.free_text ?? "—";
                    const cmd = j.command_text ?? j.transcript ?? "—";
                    const msg = `свободно: «${free}» | команда: «${cmd}» | rms ${j.peak_rms ?? "?"}`;
                    showToast(msg, Toasts.Type.MESSAGE);
                    console.info("[VoiceMuteSlots] last heard:", j);
                } catch (e) {
                    showToast("Нет /last — демон не запущен?", Toasts.Type.FAILURE);
                    console.warn(e);
                }
            }
        }
    ]
});
