"""Regenerates tests/fixtures/parity/ (exact bytes matter): python tests/make_parity_fixtures.py"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))
import dataset  # noqa: E402

OUT = os.path.join(REPO, "viewer", "tests", "fixtures", "parity")
os.makedirs(OUT, exist_ok=True)


def move(inp, **kw):
    m = {"input": inp, "image": f"https://example.test/{inp}.png", "first_active": "5", "active": "3",
         "recovery": "8", "frame_adv": "1", "proration": "75%", "invuln": "-", "alts": []}
    m.update(kw)
    return m


def w(name, text):
    with open(os.path.join(OUT, name), "wb") as f:
        f.write(text.encode("utf-8") if isinstance(text, str) else text)


BS = "\\"
canon = {"character_name": "Ciel", "moon": "Half_Moon",
         "moves": [move("5A", guard="LH"), move("2C", alts=["2c", "low"])]}
w("canonical.json", dataset.dumps(canon))
w("scrambled.json", json.dumps({"zeta": {"b": 1, "a": [{"y": 1, "x": 2}]}, "moves": [
    {"alts": ["a"], "zz": "1", "aa": "2", "nested": {"k2": "v", "k1": "v"}, "input": "5A", "image": "i",
     "guard": "L", "first_active": "1", "active": "1", "recovery": "1", "frame_adv": "1", "proration": "1",
     "invuln": "-"}],
    "moon": "Full_Moon", "alpha": True, "character_name": "Akiha_Tohno"}, indent=4, ensure_ascii=False))
w("numbers.json", '{"character_name": "Len", "moon": "Crescent_Moon", "moves": [], "n": [0, -0, 12, -7, 2.0, '
  '-0.0, 1.5, 1E2, 1e16, 1e15, 0.0001, 0.00001, 1.0e-7, 123456789012345678901234567890, 3.141592653589793, '
  '0.1, 1e22, 1e21, 5e-324, 1.7976931348623157e308, 100.0, 12345678901234567.0, 9007199254740993, 1e-4, '
  '-1.25e-10, 2.5E+3]}')
w("escapes.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "s": ['
  '"\\u00e9\\u2192", "tab\\tnl\\ncr\\r", "\\b\\f\\u0001\\u001f\\u007f", "\\/slash", "\\ud83d\\ude00", '
  '"raw \U0001F600 \u2028 \u2029 \x7f \u00a0", "quote\\" back\\\\", "\\uD83D\\uDE00 upper hex"]}')
w("nan.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "x": NaN}')
w("infinity.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "x": [Infinity, -Infinity]}')
w("huge-float.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "x": 1e400}')
w("invalid.json", '{"character_name": "Len", "moon": ')
w("trailing-comma.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [],}')
w("extra-data.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": []} {}')
w("control-char.json", '{"character_name": "Len\x01", "moon": "Half_Moon", "moves": []}')
w("bad-escape.json", '{"character_name": "Len\\x", "moon": "Half_Moon", "moves": []}')
w("bom.json", "\ufeff" + dataset.dumps(canon))
w("crlf.json", dataset.dumps(canon).replace("\n", "\r\n"))
w("no-trailing-newline.json", dataset.dumps(canon).rstrip("\n"))
w("not-object.json", '[{"character_name": "Len"}]')
w("empty-object.json", "{}")
w("missing-keys.json", json.dumps({"character_name": "", "moon": 5, "content_hash": "abc", "moves": [
    {"input": "5A"}, {"input": 7, "image": "x", "alts": "nope"}, {"image": "i", "alts": [1]}, "notadict",
    {"input": "it's", "alts": None}, {"input": "both ' and \"", "alts": None},
    {"input": "nb\u00a0sp\u200b\x7f\U0001F600\u0300\x01\u0085" + BS, "alts": None},
    {"input": None, "alts": None}, {"input": [1, "a", None, True, 2.5, {"k": "v"}], "alts": None},
    {"input": 1e100, "alts": ["ok"]}]}, indent=2))
w("moves-not-list.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": {"a": 1}}')
w("unmapped.json", dataset.dumps({"character_name": 'Some: Weird/Char?*|<>"' + BS, "moon": "Eclipse_Moon",
                                  "moves": [move("5A")]}))
w("unknown-moon.json", dataset.dumps({"character_name": "Ciel", "moon": "Blood_Moon", "moves": []}))
w("percent-name.json", dataset.dumps({"character_name": "Hisui_%26_Kohaku", "moon": "Full_Moon", "moves": []}))
w("dot-name.json", '{"character_name": "..", "moon": "Full_Moon", "moves": []}')
w("dupe-keys.json", '{"moon": "Half_Moon", "character_name": "Len", "moves": [], "z": 1, "a": 2, "z": 3, '
  '"moon": "Full_Moon"}')
w("sort-order.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [{"input": "5A", "\\ufb01": 1, '
  '"\\ud83d\\ude00": 2, "Z": 0}], "\\ufb01": 1, "\\ud83d\\ude00": 2, "B": 3, "a": 4, "\\u00e9": 5, "_": 6, '
  '"10": 7, "9": 8, "__proto__": 9, "constructor": 10}')
w("lone-surrogate.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "s": "\\ud800x"}')
w("lone-low-surrogate.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "s": "\\udc00"}')
w("high-then-nonlow.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "s": "\\ud800\\u0041"}')
w("invalid-utf8.json", b'{"character_name": "Len\xff", "moon": "Half_Moon", "moves": []}')
w("deep-empty.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [{}, [], {"input": "5A", "x": {}, '
  '"y": [[], {}]}], "e": {}, "l": []}')
w("whitespace.json", ' \t\r\n {"character_name" : "Len" , "moon":"Half_Moon","moves":[ ]} \n\n')
w("literals.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "t": true, "f": false, "n": null}')
w("leading-zero.json", '{"character_name": "Len", "moon": "Half_Moon", "moves": [], "n": 01}')
w("scalar.json", '"just a string"')
print(len(os.listdir(OUT)), "fixtures")
