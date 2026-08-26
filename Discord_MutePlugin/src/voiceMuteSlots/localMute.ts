/*
 * Local mute / unmute / hide-video by voice slot (client-side only).
 * APIs: VoiceActions.toggleLocalMute, setDisableLocalVideo, MediaEngineStore
 */

import { MediaEngineStore, VoiceActions } from "@webpack/common";

import { getVoiceSnapshot, type VoiceMemberSlot } from "./voiceMembers";

export type SlotResult =
    | {
          ok: true;
          action:
              | "muted"
              | "unmuted"
              | "already_muted"
              | "already_unmuted"
              | "video_hidden"
              | "video_shown"
              | "video_already_hidden"
              | "video_already_shown";
          slot: VoiceMemberSlot;
      }
    | { ok: false; reason: "not_in_voice" | "bad_slot" | "is_me" };

/** @deprecated use SlotResult */
export type MuteSlotResult = SlotResult;

function resolveSlot(slotNumber: number): SlotResult {
    const snap = getVoiceSnapshot();
    if (!snap?.inVoice) {
        return { ok: false, reason: "not_in_voice" };
    }

    const slot = snap.slots.find(s => s.slot === slotNumber);
    if (!slot) {
        return { ok: false, reason: "bad_slot" };
    }

    if (slot.isMe) {
        return { ok: false, reason: "is_me" };
    }

    return { ok: true, action: "muted", slot };
}

export function muteVoiceSlot(slotNumber: number): SlotResult {
    const base = resolveSlot(slotNumber);
    if (!base.ok) return base;

    const { slot } = base;
    if (MediaEngineStore.isLocalMute(slot.userId)) {
        return { ok: true, action: "already_muted", slot };
    }

    VoiceActions.toggleLocalMute(slot.userId);
    return { ok: true, action: "muted", slot };
}

export function unmuteVoiceSlot(slotNumber: number): SlotResult {
    const base = resolveSlot(slotNumber);
    if (!base.ok) return base;

    const { slot } = base;
    if (!MediaEngineStore.isLocalMute(slot.userId)) {
        return { ok: true, action: "already_unmuted", slot };
    }

    VoiceActions.toggleLocalMute(slot.userId);
    return { ok: true, action: "unmuted", slot };
}

/** Hide their camera/stream tile locally (you don't see their video). */
export function hideLocalVideoSlot(slotNumber: number): SlotResult {
    const base = resolveSlot(slotNumber);
    if (!base.ok) return base;

    const { slot } = base;
    if (MediaEngineStore.isLocalVideoDisabled(slot.userId)) {
        return { ok: true, action: "video_already_hidden", slot };
    }

    VoiceActions.setDisableLocalVideo(slot.userId, "DISABLED", "default");
    return { ok: true, action: "video_hidden", slot };
}

export function showLocalVideoSlot(slotNumber: number): SlotResult {
    const base = resolveSlot(slotNumber);
    if (!base.ok) return base;

    const { slot } = base;
    if (!MediaEngineStore.isLocalVideoDisabled(slot.userId)) {
        return { ok: true, action: "video_already_shown", slot };
    }

    VoiceActions.setDisableLocalVideo(slot.userId, "ENABLED", "default");
    return { ok: true, action: "video_shown", slot };
}

function clampVolume(v: number): number {
    return Math.max(0, Math.min(200, Math.round(v)));
}

function readLocalVolume(userId: string): number {
    const v = MediaEngineStore.getLocalVolume?.(userId);
    return typeof v === "number" && Number.isFinite(v) ? v : 100;
}

function writeLocalVolume(userId: string, volume: number): number {
    const v = clampVolume(volume);
    const va = VoiceActions as { setLocalVolume?: (id: string, vol: number) => void };
    if (typeof va.setLocalVolume === "function") {
        va.setLocalVolume(userId, v);
    } else if (typeof MediaEngineStore.setLocalVolume === "function") {
        MediaEngineStore.setLocalVolume(userId, v);
    } else {
        throw new Error("setLocalVolume API not found");
    }
    return v;
}

export type VolumeSlotResult =
    | {
          ok: true;
          slot: VoiceMemberSlot;
          from: number;
          to: number;
          mode: "up" | "down" | "set";
      }
    | { ok: false; reason: "not_in_voice" | "bad_slot" | "is_me" | "no_api" };

function ensureNotLocalMuted(userId: string) {
    if (MediaEngineStore.isLocalMute?.(userId)) {
        VoiceActions.toggleLocalMute(userId);
    }
}

export function adjustLocalVolumeSlot(
    slotNumber: number,
    mode: "up" | "down" | "set",
    amount: number
): VolumeSlotResult {
    const base = resolveSlot(slotNumber);
    if (!base.ok) return base;
    const { slot } = base;
    try {
        // После full mute громкость не слышно — снимаем local mute
        ensureNotLocalMuted(slot.userId);
        const from = readLocalVolume(slot.userId);
        let to = from;
        if (mode === "set") to = amount;
        else if (mode === "up") to = from + amount;
        else to = from - amount;
        to = writeLocalVolume(slot.userId, to);
        return { ok: true, slot, from, to, mode };
    } catch {
        return { ok: false, reason: "no_api" };
    }
}

export type BulkVolumeResult =
    | { ok: true; changed: number; total: number; mode: "up" | "down" | "set"; amount: number }
    | { ok: false; reason: "not_in_voice" | "no_others" | "no_api" };

export function adjustLocalVolumeAllOthers(
    mode: "up" | "down" | "set",
    amount: number
): BulkVolumeResult {
    const snap = getVoiceSnapshot();
    if (!snap?.inVoice) return { ok: false, reason: "not_in_voice" };
    const others = snap.others;
    if (!others.length) return { ok: false, reason: "no_others" };
    try {
        let changed = 0;
        for (const s of others) {
            ensureNotLocalMuted(s.userId);
            const from = readLocalVolume(s.userId);
            let to = from;
            if (mode === "set") to = amount;
            else if (mode === "up") to = from + amount;
            else to = from - amount;
            const written = writeLocalVolume(s.userId, to);
            if (written !== from) changed++;
        }
        return { ok: true, changed, total: others.length, mode, amount };
    } catch {
        return { ok: false, reason: "no_api" };
    }
}

export function formatVolumeResult(result: VolumeSlotResult): string {
    if (!result.ok) {
        switch (result.reason) {
            case "not_in_voice":
                return "Not in voice";
            case "bad_slot":
                return "Нет такого слота — /voice-slots";
            case "is_me":
                return "Это я — local volume себе так не ставится";
            case "no_api":
                return "API громкости не найден (обнови Discord/Equicord)";
        }
    }
    const { slot, from, to, mode } = result;
    const verb = mode === "up" ? "громче" : mode === "down" ? "тише" : "громкость";
    return `${verb} #${slot.slot} ${slot.name}: ${Math.round(from)}% → ${Math.round(to)}%`;
}

export function formatBulkVolumeResult(result: BulkVolumeResult): string {
    if (!result.ok) {
        if (result.reason === "not_in_voice") return "Not in voice";
        if (result.reason === "no_api") return "API громкости не найден";
        return "Некого — кроме тебя никого в войсе";
    }
    const verb = result.mode === "up" ? "+" : result.mode === "down" ? "−" : "=";
    return `громкость всех ${verb}${result.amount}: ${result.changed}/${result.total}`;
}

/** Last sidebar slot that is not me (or null). */
export function resolveLastOtherSlot(): number | null {
    const snap = getVoiceSnapshot();
    if (!snap?.inVoice || !snap.slots.length) return null;
    for (let i = snap.slots.length - 1; i >= 0; i--) {
        const s = snap.slots[i]!;
        if (!s.isMe) return s.slot;
    }
    return null;
}

export type BulkMuteResult =
    | { ok: true; changed: number; already: number; total: number }
    | { ok: false; reason: "not_in_voice" | "no_others" };

export function muteAllOthers(): BulkMuteResult {
    const snap = getVoiceSnapshot();
    if (!snap?.inVoice) return { ok: false, reason: "not_in_voice" };
    const others = snap.others;
    if (!others.length) return { ok: false, reason: "no_others" };

    let changed = 0;
    let already = 0;
    for (const s of others) {
        if (MediaEngineStore.isLocalMute(s.userId)) {
            already++;
            continue;
        }
        VoiceActions.toggleLocalMute(s.userId);
        changed++;
    }
    return { ok: true, changed, already, total: others.length };
}

export function unmuteAllOthers(): BulkMuteResult {
    const snap = getVoiceSnapshot();
    if (!snap?.inVoice) return { ok: false, reason: "not_in_voice" };
    const others = snap.others;
    if (!others.length) return { ok: false, reason: "no_others" };

    let changed = 0;
    let already = 0;
    for (const s of others) {
        if (!MediaEngineStore.isLocalMute(s.userId)) {
            already++;
            continue;
        }
        VoiceActions.toggleLocalMute(s.userId);
        changed++;
    }
    return { ok: true, changed, already, total: others.length };
}

export function formatBulkMuteResult(kind: "mute" | "unmute", result: BulkMuteResult): string {
    if (!result.ok) {
        if (result.reason === "not_in_voice") return "Not in voice";
        return "Некого — кроме тебя никого в войсе";
    }
    const verb = kind === "mute" ? "замьютил" : "размьютил";
    return `${verb} ${result.changed}/${result.total} (уже ок: ${result.already})`;
}

export function formatMuteResult(result: SlotResult): string {
    if (!result.ok) {
        switch (result.reason) {
            case "not_in_voice":
                return "Not in voice";
            case "bad_slot":
                return "Нет такого слота — /voice-slots";
            case "is_me":
                return "Это я — local mute/video не нужен";
        }
    }

    const { slot, action } = result;
    switch (action) {
        case "already_muted":
            return `#${slot.slot} ${slot.name} — уже локально замьючен`;
        case "already_unmuted":
            return `#${slot.slot} ${slot.name} — уже не в local mute`;
        case "unmuted":
            return `Local unmute: #${slot.slot} ${slot.name}`;
        case "video_hidden":
            return `Видео скрыто: #${slot.slot} ${slot.name}`;
        case "video_shown":
            return `Видео снова видно: #${slot.slot} ${slot.name}`;
        case "video_already_hidden":
            return `#${slot.slot} ${slot.name} — видео уже скрыто`;
        case "video_already_shown":
            return `#${slot.slot} ${slot.name} — видео уже видно`;
        case "muted":
        default:
            return `Local mute: #${slot.slot} ${slot.name}`;
    }
}
