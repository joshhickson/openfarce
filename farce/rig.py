"""
rig.py — what this rig is, stamped into everything it produces.

The campaign page makes a promise: *no measurement taken on eight lanes will be
presented as a measurement of forty, and every figure the rig produces will
carry the lane count it was measured on.* A promise in prose is worth nothing.
This module makes it mechanical — every JSON artifact written by `bench.py`,
`endure.py` and `thermal.py` carries a `rig` block naming the lane count, the
card size and the host, so a number cannot be lifted out of a file and quoted as
though it came from a different machine.

The reference rig (Addendum A2) is eight 16 GB cards on a Raspberry Pi 4B. The
Developer Kit is forty 32 GB cards. They are different machines and the files
say which one they came from.

Configuration comes from the environment so that a systemd unit, a shell and a
dry run all agree:

    FARCE_LANES        number of card slots           (default 8)
    FARCE_CARD_BYTES   nominal bytes per card         (default 16 GB)
    FARCE_HOST         free-text host description     (default: uname)
    FARCE_RIG_NAME     what to call this rig          (default: reference rig)
"""
import os
import platform

DEFAULT_LANES = 8
DEFAULT_CARD_BYTES = 16 * 10**9          # 16 GB nominal, as the box is labelled
DEFAULT_NAME = "reference rig"

# Lane counts that have a name on the site. Anything else is fine, and is
# reported as-is; this only exists so the stamp can say which one it is.
KNOWN = {
    8:  "reference rig (Addendum A2): 8 lanes on a Raspberry Pi 4B",
    40: "Developer Kit array: 40 lanes, the configuration the site headlines",
}


def lanes() -> int:
    return int(os.environ.get("FARCE_LANES", DEFAULT_LANES))


def card_bytes() -> int:
    return int(os.environ.get("FARCE_CARD_BYTES", DEFAULT_CARD_BYTES))


def host() -> str:
    described = os.environ.get("FARCE_HOST")
    if described:
        return described
    return "%s %s" % (platform.system(), platform.machine())


def name() -> str:
    return os.environ.get("FARCE_RIG_NAME", DEFAULT_NAME)


def raw_capacity_bytes() -> int:
    return lanes() * card_bytes()


def stamp() -> dict:
    """The block every artifact embeds. Never omit it from a written file."""
    n = lanes()
    return {
        "name": name(),
        "lanes": n,
        "card_bytes": card_bytes(),
        "raw_capacity_bytes": raw_capacity_bytes(),
        "host": host(),
        "configuration": KNOWN.get(n, "%d lanes; not a configuration the site names" % n),
        "caveat": (
            "Every number in this file was measured on %d lane%s. It describes "
            "this rig and nothing else. Do not quote it as a figure for a "
            "different lane count without saying so." % (n, "" if n == 1 else "s")
        ),
    }


def describe() -> str:
    """One line for a log header."""
    n = lanes()
    return "%s: %d lanes x %.0f GB = %.0f GB raw, on %s" % (
        name(), n, card_bytes() / 1e9, raw_capacity_bytes() / 1e9, host())


if __name__ == "__main__":
    import json
    print(describe())
    print(json.dumps(stamp(), indent=2))
