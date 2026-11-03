# Known wiki mistakes the scraper can't read around, keyed by page.
#
# Each entry renames the nth occurrence (0-based) of an input on that page, as
# the scraper produced it. Alts are rebuilt from the corrected input, so a fixed
# move gets the same alts as the equivalent move on any other page.
from typing import Dict, List, Tuple

INPUT_CORRECTIONS: Dict[Tuple[str, str], Dict[Tuple[str, int], str]] = {
    ("Neco-Arc", "Half_Moon"): {
        # The 5A table holds three unlabelled frame-data blocks: 5A, 5A~6A and
        # 5A~6A~6A (only the image names, MBHNeco5A / MBHNeco5A6A, tell them apart).
        ("5A", 1): "5A~6A",
        ("5A", 2): "5A~6A~6A",
    },
}


def apply_input_corrections(melty_char, get_alt_inputs) -> List[str]:
    """Rename the listed moves in place and rebuild their alts.

    Returns a warning per correction that no longer matches, e.g. because the
    wiki page was fixed, so it can be removed instead of silently doing nothing.
    """
    corrections = INPUT_CORRECTIONS.get((melty_char.character_name, melty_char.moon), {})
    if not corrections:
        return []
    seen: Dict[str, int] = {}
    applied = set()
    for move in melty_char.moves:
        occurrence = seen.get(move.input, 0)
        seen[move.input] = occurrence + 1
        corrected = corrections.get((move.input, occurrence))
        if corrected is not None:
            applied.add((move.input, occurrence))
            move.input = corrected
            move.alts = get_alt_inputs(corrected)
    return [
        f"errata: {melty_char.character_name}/{melty_char.moon} has no {inp!r} #{occ + 1} to rename to {new!r}"
        for (inp, occ), new in corrections.items()
        if (inp, occ) not in applied
    ]
