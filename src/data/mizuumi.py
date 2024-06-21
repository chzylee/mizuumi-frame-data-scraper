_MOON_MAPPINGS = {
    "Crescent_Moon": "C",
    "Half_Moon": "H",
    "Full_Moon": "F"
}

# For purposes of this app it would be simpler if keys/values were reversed
# but for simplicity this is just copied from what was made for the frame data bot.
CHAR_MAPPINGS = {
    "akiha": "Akiha_Tohno",
    "aoko": "Aoko_Aozaki",
    "arc": "Arcueid_Brunestud",
    "arcueid": "Arcueid_Brunestud",
    "ciel": "Ciel",
    "hime": "Archetype:_Earth",
    "hisui": "Hisui",
    "koha-mech": "Koha_%26_Mech",
    "koha mech": "Koha_%26_Mech",
    "kohamech": "Koha_%26_Mech",
    "kohaku": "Kohaku",
    "kouma": "Kouma_Kishima",
    "len": "Len",
    "maids": "Hisui_%26_Kohaku", # Presetving % codes in routes to avoid errors.
    "mech": "Mech-Hisui",
    "miyako": "Miyako_Arima",
    "nac": "Neco-Arc_Chaos",
    "nanaya": "Shiki_Nanaya",
    "neco": "Neco-Arc",
    "neco-mech": "Neco_%26_Mech", # Support original and common spellings.
    "neco mech": "Neco_%26_Mech",
    "necomech": "Neco_%26_Mech",
    "neko-mech": "Neco_%26_Mech",
    "neko mech": "Neco_%26_Mech",
    "nekomech": "Neco_%26_Mech",
    "nero": "Nero_Chaos",
    "nrvnqsr": "Nero_Chaos",
    "pciel": "Powered_Ciel",
    "p-ciel": "Powered_Ciel",
    "warc": "Red_Arcueid",
    "red arc ": "Red_Arcueid",
    "ries": "Riesbyfe_Stridberg",
    "roa": "Roa",
    "ryougi": "Shiki_Ryougi",
    "sats": "Satsuki_Yumizuka",
    "satsuki": "Satsuki_Yumizuka",
    "sei": "Akiha_Tohno_(Seifuku)",
    "seifuku": "Akiha_Tohno_(Seifuku)",
    "sion": "Sion_Eltnam_Atlasia",
    "tohno": "Shiki_Tohno",
    "tony": "Shiki_Tohno",
    "vaki": "Akiha_Vermilion",
    "vakiha": "Akiha_Vermilion",
    "vsion": "Sion_TATARI",
    "wara": "Warachia",
    "warachia": "Warachia",
    "wlen": "White_Len",
    "w-len": "White_Len"
}

def get_moon_letter(moon: str) -> str:
    return _MOON_MAPPINGS[moon]

def get_char_name(wiki_char_path: str) -> str:
    char_key = next(key for key, value in CHAR_MAPPINGS.items() if value == wiki_char_path)
    return char_key
