"""
Projects a master population record into an agency-specific "view" of that
same identity - the mechanism behind "one fake person, three different-
looking records across three agencies."

This is deliberately NOT the same thing as dirty.py's failure injection.
present_identity() models ordinary, expected cross-system variation that
exists even in perfectly healthy government data - nicknames, minor
transcription drift, each agency minting its own reference number for the
same person - and is always applied. dirty.py instead models genuine data
QUALITY defects (nulls, invalid codes, drift) at a configurable rate, on
top of whichever presentation came out of here. Keeping the two separate
means "realistic-looking" and "deliberately broken for QA testing" stay
independently controllable.
"""
from __future__ import annotations
import hashlib
import numpy as np

NICKNAMES = {
    "William": ["Will", "Bill", "Liam"],
    "Charlotte": ["Charlie", "Lottie"],
    "Alexander": ["Alex", "Xander"],
    "Samuel": ["Sam"],
    "Thomas": ["Tom", "Tommy"],
    "Michael": ["Mike"],
    "Isaac": ["Ike"],
    "Joshua": ["Josh"],
    "Jacob": ["Jake"],
    "Matilda": ["Tilly"],
    "Eleanor": ["Nell", "Ellie"],
    "Elijah": ["Eli"],
    "Isabella": ["Bella"],
    "Nathan": ["Nate"],
    "Benjamin": ["Ben"],
}

_QWERTY_NEIGHBOR = {
    "a": "sq", "b": "vn", "c": "xv", "d": "sf", "e": "wr", "f": "dg", "g": "fh",
    "h": "gj", "i": "uo", "j": "hk", "k": "jl", "l": "k", "m": "n", "n": "bm",
    "o": "ip", "p": "o", "q": "wa", "r": "et", "s": "ad", "t": "ry", "u": "yi",
    "v": "cb", "w": "qe", "x": "zc", "y": "tu", "z": "x",
}

def _agency_id(agency_prefix: str, person_uid: int, width: int = 9) -> str:
    """A stable, agency-specific reference number for this identity - looks
    nothing like the master person_uid or another agency's number for the
    same person, matching how real agencies never share a common key."""
    h = hashlib.sha256(f"{agency_prefix}:{person_uid}".encode()).hexdigest()
    digits = str(int(h[:12], 16))[-width:].rjust(width, "0")
    return f"{agency_prefix}-{digits}"

def _typo(s: str, rng: np.random.Generator) -> str:
    if len(s) < 3:
        return s
    i = rng.integers(1, len(s) - 1)
    ch = s[i].lower()
    choices = _QWERTY_NEIGHBOR.get(ch)
    if not choices:
        return s
    repl = rng.choice(list(choices))
    repl = repl.upper() if s[i].isupper() else repl
    return s[:i] + repl + s[i + 1:]

def present_identity(given_name: str, family_name: str, person_uid: int, agency_prefix: str,
                      rng: np.random.Generator, nickname_rate: float = 0.12, typo_rate: float = 0.035) -> dict:
    """Return {given_name, family_name, agency_id} as this agency would have
    it on file for this person - independently perturbed per agency, so the
    same person's three agency records don't all drift the same way."""
    g = given_name
    if g in NICKNAMES and rng.random() < nickname_rate:
        g = rng.choice(NICKNAMES[g])
    f = family_name
    if rng.random() < typo_rate:
        if rng.random() < 0.5:
            g = _typo(g, rng)
        else:
            f = _typo(f, rng)
    return {
        "given_name": g,
        "family_name": f,
        "agency_id": _agency_id(agency_prefix, person_uid),
    }

def present_identity_batch(given_names, family_names, person_uids, agency_prefix: str,
                            seed: int, nickname_rate: float = 0.12, typo_rate: float = 0.035):
    """Vectorized-ish batch version (still a Python loop, but isolated to
    the identity fields only - the rest of a dataset's columns are built
    fully vectorized). Fine up to several million rows; see README for the
    cost if a downstream dataset needs tens of millions of presented names."""
    rng = np.random.default_rng(seed)
    out_given = np.empty(len(given_names), dtype=object)
    out_family = np.empty(len(given_names), dtype=object)
    out_id = np.empty(len(given_names), dtype=object)
    for i in range(len(given_names)):
        r = present_identity(given_names[i], family_names[i], person_uids[i], agency_prefix, rng,
                              nickname_rate, typo_rate)
        out_given[i] = r["given_name"]; out_family[i] = r["family_name"]; out_id[i] = r["agency_id"]
    return out_given, out_family, out_id
