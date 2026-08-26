/*
 * Voice snapshot from Discord internal stores (Equicord/Vencord).
 *
 * Slot order = guild left-sidebar voice list = SortedVoiceStateStore.
 * If this breaks after Discord update — re-find store in docs/parts/02-voice-members.md
 */

import type { Channel, VoiceState } from "@vencord/discord-types";
import { findStoreLazy } from "@webpack";
import { ChannelStore, GuildMemberStore, GuildStore, UserStore, VoiceStateStore } from "@webpack/common";

export interface VoiceMemberSlot {
    slot: number;
    userId: string;
    name: string;
    isMe: boolean;
    /** Discord SortedVoiceStateStore comparator (debug /voice-slots) */
    sortKey?: string;
}

export interface VoiceLobby {
    guildId: string | null;
    guildName: string | null;
    channelId: string;
    channelName: string;
    label: string;
}

export interface VoiceSnapshot {
    inVoice: boolean;
    lobby: VoiceLobby | null;
    me: VoiceMemberSlot | null;
    others: VoiceMemberSlot[];
    slots: VoiceMemberSlot[];
    /** How order was obtained */
    orderSource: "SortedVoiceStateStore" | "comparator-fallback" | "none";
}

/** Entry shape from Discord SortedVoiceStateStore (minified fields may vary). */
interface SortedVoiceEntry {
    user?: { id: string; globalName?: string | null; username?: string };
    nick?: string | null;
    voiceState?: VoiceState;
    comparator?: string;
}

type SortedVoiceStateStoreT = {
    getVoiceStatesForChannel?: (channel: Channel) => SortedVoiceEntry[];
    getVoiceStatesForChannelAlt?: (channelId: string, guildId: string | null) => SortedVoiceEntry[];
};

const SortedVoiceStateStore = findStoreLazy("SortedVoiceStateStore") as SortedVoiceStateStoreT;

function memberName(
    userId: string,
    guildId: string | null,
    user: { globalName?: string | null; username?: string; id: string },
    nickOverride?: string | null
): string {
    if (nickOverride) return nickOverride;
    if (guildId) {
        const nick = GuildMemberStore.getNick(guildId, userId);
        if (nick) return nick;
    }
    return user.globalName || user.username || user.id;
}

/**
 * Discord guild-sidebar comparator (from SortedVoiceStateStore, Discord 1.0.9253):
 *   `${selfStream ? "\0" : "\x01"}${name.toLowerCase()}\0${userId}`
 * selfVideo / speaking do NOT affect sidebar order (only the call grid).
 */
function discordSidebarSortKey(vs: VoiceState, sortName: string): string {
    return `${vs.selfStream ? "\0" : "\x01"}${sortName.toLowerCase()}\0${vs.userId}`;
}

function formatSortKeyForLog(key: string): string {
    return key
        .replace(/\0/g, "\\0")
        .replace(/\x01/g, "\\x01");
}

function buildLobby(channelId: string): VoiceLobby {
    const channel = ChannelStore.getChannel(channelId);
    const channelName = channel?.name ?? channelId;
    const guildId = (channel?.guild_id as string | undefined) ?? null;
    const guildName = guildId ? (GuildStore.getGuild(guildId)?.name ?? null) : null;
    const label = guildName ? `${guildName} / ${channelName}` : channelName;
    return { guildId, guildName, channelId, channelName, label };
}

function userIdFromSortedEntry(entry: SortedVoiceEntry): string | null {
    return entry.voiceState?.userId ?? entry.user?.id ?? null;
}

/** Prefer Discord's already-sorted list; fall back to the same comparator. */
function orderedEntriesInChannel(
    channelId: string,
    guildId: string | null
): { userIds: string[]; sortKeys: Map<string, string>; source: VoiceSnapshot["orderSource"] } {
    const sortKeys = new Map<string, string>();

    try {
        const channel = ChannelStore.getChannel(channelId);
        let entries: SortedVoiceEntry[] | undefined;

        if (channel && typeof SortedVoiceStateStore?.getVoiceStatesForChannel === "function") {
            entries = SortedVoiceStateStore.getVoiceStatesForChannel(channel);
        } else if (typeof SortedVoiceStateStore?.getVoiceStatesForChannelAlt === "function") {
            entries = SortedVoiceStateStore.getVoiceStatesForChannelAlt(channelId, guildId);
        }

        if (Array.isArray(entries) && entries.length > 0) {
            const userIds: string[] = [];
            for (const entry of entries) {
                const id = userIdFromSortedEntry(entry);
                if (!id) continue;
                userIds.push(id);
                if (entry.comparator != null) {
                    sortKeys.set(id, entry.comparator);
                } else if (entry.voiceState) {
                    const name = memberName(id, guildId, entry.user ?? { id }, entry.nick);
                    sortKeys.set(id, discordSidebarSortKey(entry.voiceState, name));
                }
            }
            if (userIds.length > 0) {
                return { userIds, sortKeys, source: "SortedVoiceStateStore" };
            }
        }
    } catch (e) {
        console.warn("[VoiceMuteSlots] SortedVoiceStateStore failed, using comparator fallback", e);
    }

    // Fallback: same rules as Discord O() — stream first, then lowercase name, then userId
    const voiceStates = VoiceStateStore.getVoiceStatesForChannel(channelId);
    const list = Object.values(voiceStates).filter((vs): vs is VoiceState => Boolean(vs?.userId));

    list.sort((a, b) => {
        const an = memberName(a.userId, guildId, UserStore.getUser(a.userId) ?? { id: a.userId });
        const bn = memberName(b.userId, guildId, UserStore.getUser(b.userId) ?? { id: b.userId });
        const ka = discordSidebarSortKey(a, an);
        const kb = discordSidebarSortKey(b, bn);
        return ka < kb ? -1 : ka > kb ? 1 : 0;
    });

    const userIds = list.map(vs => {
        const name = memberName(vs.userId, guildId, UserStore.getUser(vs.userId) ?? { id: vs.userId });
        sortKeys.set(vs.userId, discordSidebarSortKey(vs, name));
        return vs.userId;
    });

    return { userIds, sortKeys, source: "comparator-fallback" };
}

export function getSlotByNumber(snap: VoiceSnapshot, slotNumber: number): VoiceMemberSlot | null {
    return snap.slots.find(s => s.slot === slotNumber) ?? null;
}

export function getVoiceSnapshot(): VoiceSnapshot | null {
    const meUser = UserStore.getCurrentUser();
    if (!meUser?.id) return null;

    const myVoice = VoiceStateStore.getVoiceStateForUser(meUser.id);
    const channelId = myVoice?.channelId ?? null;
    if (!channelId) {
        return {
            inVoice: false,
            lobby: null,
            me: null,
            others: [],
            slots: [],
            orderSource: "none"
        };
    }

    const lobby = buildLobby(channelId);
    const { userIds, sortKeys, source } = orderedEntriesInChannel(channelId, lobby.guildId);

    const slots: VoiceMemberSlot[] = [];
    for (let i = 0; i < userIds.length; i++) {
        const userId = userIds[i]!;
        const user = UserStore.getUser(userId);
        if (!user) continue;
        const isMe = userId === meUser.id;
        slots.push({
            slot: i + 1,
            userId,
            name: memberName(userId, lobby.guildId, user),
            isMe,
            sortKey: sortKeys.get(userId)
        });
    }

    const me = slots.find(s => s.isMe) ?? null;
    const others = slots.filter(s => !s.isMe);

    return {
        inVoice: true,
        lobby,
        me,
        others,
        slots,
        orderSource: source
    };
}

export function snapshotFingerprint(snap: VoiceSnapshot): string {
    if (!snap.inVoice || !snap.lobby) return "out";
    const parts = snap.slots.map(s => `${s.slot}:${s.userId}`);
    return `${snap.lobby.channelId}|${parts.join(",")}`;
}

export function formatSnapshotLog(snap: VoiceSnapshot): string {
    if (!snap.inVoice || !snap.lobby) {
        return "not in voice";
    }
    const order = snap.slots
        .map(s => {
            const meTag = s.isMe ? " (me)" : "";
            const key = s.sortKey != null ? ` key=${formatSortKeyForLog(s.sortKey)}` : "";
            return `#${s.slot} "${s.name}"${meTag}${key}`;
        })
        .join(", ");
    return `lobby="${snap.lobby.label}" source=${snap.orderSource} slots=[${order}]`;
}

/** Top-to-bottom sidebar order (includes self) — for toast /voice-slots. */
export function formatSnapshotToast(snap: VoiceSnapshot): string {
    if (!snap.inVoice || !snap.lobby) {
        return "Not in voice";
    }
    if (!snap.slots.length) {
        return `${snap.lobby.channelName} | (empty)`;
    }
    const list = snap.slots
        .map(s => `#${s.slot} ${s.name}${s.isMe ? " (me)" : ""}`)
        .join(", ");
    return `${snap.lobby.channelName} | ${list}`;
}
