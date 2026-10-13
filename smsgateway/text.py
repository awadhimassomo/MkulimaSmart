"""Phone numbers and SMS text: normalising numbers, GSM-7 versus UCS-2, how many parts a message needs, and trimming."""
import re

# The GSM 03.38 default alphabet: one unit each. The extension set below costs two units each.
GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENSION = "^{}\\[~]|€"

SINGLE_GSM, MULTI_GSM = 160, 153
SINGLE_UCS2, MULTI_UCS2 = 70, 67

# Characters people paste that are not in the GSM alphabet, replaced by plain ones so the SMS stays cheap.
REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...",
    " ": " ", "•": "-", "·": "-", "×": "x",
}


def e164(phone):
    """
    A Tanzanian or international number as +<digits>, or None when it is not a mobile number.
    0712 345 678, 255712345678 and +255 712 345 678 all become +255712345678.
    """
    raw = (phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if raw.startswith("+"):
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    if digits.startswith("00") and 10 <= len(digits) <= 17:
        return f"+{digits[2:]}"
    if digits.startswith("0") and len(digits) == 10:
        return f"+255{digits[1:]}"
    if len(digits) == 9:
        return f"+255{digits}"
    if digits.startswith("255") and len(digits) == 12:
        return f"+{digits}"
    return None


def phone_key(phone):
    """The last nine digits: the same subscriber whatever the format."""
    return re.sub(r"\D", "", phone or "")[-9:]


def local_format(phone):
    """+255712345678 as 0712 345 678, for showing in an SMS."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("255") and len(digits) == 12:
        digits = "0" + digits[3:]
    return f"{digits[:4]} {digits[4:7]} {digits[7:]}".strip() if len(digits) == 10 else (phone or "")


def clean(text):
    """Swap curly quotes, dashes and the like for plain ones, and tidy blank space, so a message stays in the cheap alphabet."""
    text = "".join(REPLACEMENTS.get(char, char) for char in (text or ""))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def analyze(text):
    """Returns (encoding, length in units, parts) where encoding is "gsm7" or "ucs2"."""
    units = 0
    for char in text:
        if char in GSM7_EXTENSION:
            units += 2
        elif char in GSM7_BASIC:
            units += 1
        else:
            units = len(text)
            return "ucs2", units, 1 if units <= SINGLE_UCS2 else -(-units // MULTI_UCS2)
    return "gsm7", units, 1 if units <= SINGLE_GSM else -(-units // MULTI_GSM)


def shorten(text, max_parts=3):
    """Cut a message so it fits in `max_parts` SMS, ending on a whole word with an ellipsis."""
    text = clean(text)
    encoding, units, parts = analyze(text)
    if parts <= max_parts:
        return text
    limit = (MULTI_GSM if encoding == "gsm7" else MULTI_UCS2) * max_parts - 3
    cut = text[:limit]
    # Characters outside the basic alphabet count double; trim until it fits.
    while analyze(cut + "...")[2] > max_parts and cut:
        cut = cut[:-1]
    space = cut.rfind(" ")
    if space > len(cut) * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + "..."
