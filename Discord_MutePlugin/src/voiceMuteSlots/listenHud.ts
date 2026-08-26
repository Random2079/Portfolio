/*
 * Big on-screen HUD so user sees when Shift+K is listening.
 */

const HUD_ID = "voice-mute-slots-hud";

export type HudState = "idle" | "listening" | "error" | "heard";

function ensureHud(): HTMLDivElement {
    let el = document.getElementById(HUD_ID) as HTMLDivElement | null;
    if (el) return el;

    el = document.createElement("div");
    el.id = HUD_ID;
    el.style.cssText = [
        "position:fixed",
        "top:72px",
        "left:50%",
        "transform:translateX(-50%)",
        "z-index:2147483647",
        "pointer-events:none",
        "font-family:gg sans,Whitney,Helvetica Neue,Helvetica,Arial,sans-serif",
        "font-size:16px",
        "font-weight:700",
        "padding:12px 20px",
        "border-radius:12px",
        "box-shadow:0 8px 24px rgba(0,0,0,.45)",
        "max-width:min(560px,90vw)",
        "text-align:center",
        "display:none",
        "white-space:pre-wrap",
        "line-height:1.35"
    ].join(";");
    document.body.appendChild(el);
    return el;
}

export function setListenHud(state: HudState, text: string) {
    const el = ensureHud();
    if (state === "idle") {
        el.style.display = "none";
        el.textContent = "";
        return;
    }

    el.style.display = "block";
    el.textContent = text;

    if (state === "listening") {
        el.style.background = "rgba(237, 66, 69, 0.95)";
        el.style.color = "#fff";
        el.style.outline = "2px solid rgba(255,255,255,.35)";
    } else if (state === "error") {
        el.style.background = "rgba(240, 178, 50, 0.96)";
        el.style.color = "#000";
        el.style.outline = "none";
    } else {
        el.style.background = "rgba(35, 165, 90, 0.95)";
        el.style.color = "#fff";
        el.style.outline = "none";
    }
}

export function removeListenHud() {
    document.getElementById(HUD_ID)?.remove();
}
