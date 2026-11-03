/**
 * JSON exactly as Python's `json` module reads and writes it, for the one
 * serialization `src/dataset.py` accepts.
 *
 * `JSON.parse` is not enough for byte-for-byte parity: it turns `2.0` into `2`,
 * loses integers past 2^53, and rejects the `NaN`/`Infinity` literals Python
 * accepts on read. So this module has its own small parser that keeps every
 * number as the text Python would print for it, and a writer that mirrors
 * `json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False)`.
 *
 * Known divergence (documented, not reachable through valid data): JS objects
 * list integer-like keys ("1", "42") first, so `pyRepr` of an object prints such
 * keys in a different order than Python's dict repr. Canonical output sorts
 * those keys anyway, so `dumps` is unaffected.
 */

/** A JSON number, held as the text Python's repr would print for it. */
export class PyNumber {
  private constructor(
    readonly kind: "int" | "float",
    /** Python repr: "12", "2.0", "1e-05", "nan", "inf", "-inf". */
    readonly text: string,
  ) {}

  static fromLexeme(lexeme: string): PyNumber {
    if (/[.eE]/.test(lexeme)) return PyNumber.float(Number(lexeme));
    // Python: int(lexeme), then str(). JSON forbids leading zeros, so the only
    // rewrite is "-0" -> "0". Arbitrary precision is kept as text.
    return new PyNumber("int", lexeme === "-0" ? "0" : lexeme);
  }

  static float(value: number): PyNumber {
    return new PyNumber("float", pyFloatRepr(value));
  }

  get finite(): boolean {
    return this.kind === "int" || !["nan", "inf", "-inf"].includes(this.text);
  }
}

export type Json = string | boolean | null | PyNumber | Json[] | JsonObject;
export interface JsonObject {
  [key: string]: Json;
}

export class JsonParseError extends Error {}
/** `pyError` names the exception Python raises in the same case (for parity). */
export class JsonEncodeError extends Error {
  constructor(message: string, readonly pyError: "ValueError" | "UnicodeEncodeError") {
    super(message);
  }
}

export function isObject(value: Json | undefined): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value) && !(value instanceof PyNumber);
}

/** Set a key as an own property, so data keys like "__proto__" stay data. */
export function setKey(obj: JsonObject, key: string, value: Json): void {
  Object.defineProperty(obj, key, { value, enumerable: true, writable: true, configurable: true });
}

export function has(obj: JsonObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

/** Python's float.__repr__ (shortest round-trip, its own fixed/exponent rule). */
export function pyFloatRepr(value: number): string {
  if (Number.isNaN(value)) return "nan";
  if (value === Infinity) return "inf";
  if (value === -Infinity) return "-inf";
  if (value === 0) return Object.is(value, -0) ? "-0.0" : "0.0";
  const sign = value < 0 ? "-" : "";
  // toExponential() with no argument gives the shortest digits that round-trip.
  const [mantissa, exponent] = Math.abs(value).toExponential().split("e") as [string, string];
  const digits = mantissa.replace(".", "");
  const decpt = Number(exponent) + 1; // value = 0.<digits> * 10^decpt
  if (decpt > -4 && decpt <= 16) {
    if (decpt <= 0) return `${sign}0.${"0".repeat(-decpt)}${digits}`;
    if (decpt >= digits.length) return `${sign}${digits}${"0".repeat(decpt - digits.length)}.0`;
    return `${sign}${digits.slice(0, decpt)}.${digits.slice(decpt)}`;
  }
  const exp = decpt - 1;
  const lead = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
  return `${sign}${lead}e${exp < 0 ? "-" : "+"}${String(Math.abs(exp)).padStart(2, "0")}`;
}

// --- parsing (json.loads semantics) -----------------------------------------------

const WHITESPACE = new Set([" ", "\t", "\n", "\r"]);
const NUMBER_RE = /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?/y;
const ESCAPES: Record<string, string> = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };

export function loads(text: string): Json {
  let pos = 0;
  const fail = (message: string): never => {
    throw new JsonParseError(`${message} at char ${pos}`);
  };
  const skip = () => {
    while (pos < text.length && WHITESPACE.has(text[pos]!)) pos++;
  };
  const hex4 = (at: number): number => {
    const chunk = text.slice(at, at + 4);
    if (!/^[0-9a-fA-F]{4}$/.test(chunk)) fail("Invalid \\uXXXX escape");
    return parseInt(chunk, 16);
  };
  const parseString = (): string => {
    pos++; // opening quote
    let out = "";
    for (;;) {
      if (pos >= text.length) fail("Unterminated string");
      const ch = text[pos]!;
      if (ch === '"') {
        pos++;
        return out;
      }
      if (ch === "\\") {
        const esc = text[pos + 1];
        if (esc === "u") {
          let code = hex4(pos + 2);
          pos += 6;
          // A high surrogate followed by an escaped low surrogate is one code point;
          // anything else (a lone surrogate) is kept as-is, as Python does.
          if (code >= 0xd800 && code <= 0xdbff && text[pos] === "\\" && text[pos + 1] === "u") {
            const low = hex4(pos + 2);
            if (low >= 0xdc00 && low <= 0xdfff) {
              code = 0x10000 + ((code - 0xd800) << 10) + (low - 0xdc00);
              pos += 6;
            }
          }
          out += String.fromCodePoint(code);
          continue;
        }
        if (esc === undefined || !(esc in ESCAPES)) fail("Invalid \\escape");
        out += ESCAPES[esc!];
        pos += 2;
        continue;
      }
      if (ch.charCodeAt(0) < 0x20) fail("Invalid control character");
      out += ch;
      pos++;
    }
  };
  const parseValue = (): Json => {
    skip();
    const ch = text[pos];
    if (ch === "{") {
      pos++;
      const obj: JsonObject = {};
      skip();
      if (text[pos] === "}") {
        pos++;
        return obj;
      }
      for (;;) {
        skip();
        if (text[pos] !== '"') fail("Expecting property name enclosed in double quotes");
        const key = parseString();
        skip();
        if (text[pos] !== ":") fail("Expecting ':' delimiter");
        pos++;
        // Duplicate keys: last value wins, first position kept (a Python dict).
        setKey(obj, key, parseValue());
        skip();
        if (text[pos] === ",") {
          pos++;
          continue;
        }
        if (text[pos] === "}") {
          pos++;
          return obj;
        }
        fail("Expecting ',' delimiter");
      }
    }
    if (ch === "[") {
      pos++;
      const list: Json[] = [];
      skip();
      if (text[pos] === "]") {
        pos++;
        return list;
      }
      for (;;) {
        list.push(parseValue());
        skip();
        if (text[pos] === ",") {
          pos++;
          continue;
        }
        if (text[pos] === "]") {
          pos++;
          return list;
        }
        fail("Expecting ',' delimiter");
      }
    }
    if (ch === '"') return parseString();
    for (const [word, value] of [["true", true], ["false", false], ["null", null]] as const) {
      if (text.startsWith(word, pos)) {
        pos += word.length;
        return value;
      }
    }
    // Python's json accepts these non-standard literals on read.
    for (const [word, value] of [["NaN", NaN], ["Infinity", Infinity], ["-Infinity", -Infinity]] as const) {
      if (text.startsWith(word, pos)) {
        pos += word.length;
        return PyNumber.float(value);
      }
    }
    NUMBER_RE.lastIndex = pos;
    const match = NUMBER_RE.exec(text);
    if (match) {
      pos += match[0].length;
      return PyNumber.fromLexeme(match[0]);
    }
    return fail("Expecting value");
  };

  const value = parseValue();
  skip();
  if (pos !== text.length) fail("Extra data");
  return value;
}

// --- writing (json.dumps(indent=2, ensure_ascii=False, allow_nan=False)) ----------

function encodeString(value: string): string {
  let out = '"';
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i);
    const ch = value[i]!;
    if (ch === '"') out += '\\"';
    else if (ch === "\\") out += "\\\\";
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (ch === "\b") out += "\\b";
    else if (ch === "\f") out += "\\f";
    else if (code < 0x20) out += `\\u${code.toString(16).padStart(4, "0")}`;
    else if (code >= 0xd800 && code <= 0xdfff) {
      const next = value.charCodeAt(i + 1);
      if (code <= 0xdbff && next >= 0xdc00 && next <= 0xdfff) {
        out += ch + value[i + 1];
        i++;
      } else {
        // Python writes the lone surrogate raw, and then cannot encode the text
        // as UTF-8. Fail the same way, here, instead of writing a broken file.
        throw new JsonEncodeError("a lone surrogate cannot be encoded as UTF-8", "UnicodeEncodeError");
      }
    } else out += ch;
  }
  return out + '"';
}

/** Which keys of an object to write, in order. `path` is the keys/indexes from the root. */
export type KeyOrder = (obj: JsonObject, path: readonly (string | number)[]) => string[];

export const sortedKeys: KeyOrder = (obj) => Object.keys(obj).sort(compareCodePoints);

/**
 * json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), no trailing
 * newline, writing object keys in the order `keyOrder` gives. Key order is
 * always explicit: JS objects enumerate integer-like keys ("5") first, so the
 * order an object was built in can't be relied on.
 */
export function encodeJson(value: Json, keyOrder: KeyOrder = sortedKeys): string {
  const encode = (node: Json, indent: string, path: (string | number)[]): string => {
    if (node === null) return "null";
    if (node === true) return "true";
    if (node === false) return "false";
    if (typeof node === "string") return encodeString(node);
    if (node instanceof PyNumber) {
      if (!node.finite) throw new JsonEncodeError(`Out of range float values are not JSON compliant: ${node.text}`, "ValueError");
      return node.text;
    }
    const inner = indent + "  ";
    if (Array.isArray(node)) {
      if (node.length === 0) return "[]";
      return `[\n${node.map((item, i) => inner + encode(item, inner, [...path, i])).join(",\n")}\n${indent}]`;
    }
    const keys = keyOrder(node, path);
    if (keys.length === 0) return "{}";
    const body = keys.map((key) => `${inner}${encodeString(key)}: ${encode(node[key]!, inner, [...path, key])}`);
    return `{\n${body.join(",\n")}\n${indent}}`;
  };
  return encode(value, "", []);
}

/** Python's default string ordering: by code point (JS sorts by UTF-16 unit). */
export function compareCodePoints(a: string, b: string): number {
  const ia = a[Symbol.iterator]();
  const ib = b[Symbol.iterator]();
  for (;;) {
    const na = ia.next();
    const nb = ib.next();
    if (na.done || nb.done) return na.done && nb.done ? 0 : na.done ? -1 : 1;
    const ca = na.value.codePointAt(0)!;
    const cb = nb.value.codePointAt(0)!;
    if (ca !== cb) return ca < cb ? -1 : 1;
  }
}

/** Stable text for comparing two values (keys sorted at every level). */
export function valueKey(value: Json | undefined): string {
  return value === undefined ? "<missing>" : encodeJson(value);
}

// --- Python repr (for validation messages that embed `{value!r}`) ------------------

const NON_PRINTABLE = /^[\p{C}\p{Z}]$/u;

export function pyRepr(value: Json | undefined): string {
  if (value === undefined || value === null) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (value instanceof PyNumber) return value.text;
  if (typeof value === "string") return pyStrRepr(value);
  if (Array.isArray(value)) return `[${value.map(pyRepr).join(", ")}]`;
  return `{${Object.keys(value).map((key) => `${pyStrRepr(key)}: ${pyRepr(value[key])}`).join(", ")}}`;
}

function pyStrRepr(value: string): string {
  const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
  let out = quote;
  for (const ch of value) {
    const code = ch.codePointAt(0)!;
    if (ch === quote || ch === "\\") out += "\\" + ch;
    else if (ch === "\t") out += "\\t";
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (code < 0x20 || code === 0x7f) out += `\\x${code.toString(16).padStart(2, "0")}`;
    else if (code < 0x7f) out += ch;
    else if (!NON_PRINTABLE.test(ch)) out += ch;
    else if (code <= 0xff) out += `\\x${code.toString(16).padStart(2, "0")}`;
    else if (code <= 0xffff) out += `\\u${code.toString(16).padStart(4, "0")}`;
    else out += `\\U${code.toString(16).padStart(8, "0")}`;
  }
  return out + quote;
}
