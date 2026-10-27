"""Status words with Material icons (OpenDesign: no emoji; pair colour with a word)."""
STATUS = {
    "pass": ":green[:material/check_circle: pass]",
    "warn": ":orange[:material/warning: warn]",
    "fail": ":red[:material/error: fail]",
}


def ok_label(ok: bool, yes: str = "ok", no: str = "missing") -> str:
    return f":green[:material/check_circle: {yes}]" if ok else f":red[:material/error: {no}]"
