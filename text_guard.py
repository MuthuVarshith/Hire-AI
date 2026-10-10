"""Make untrusted text show what it says, before it is matched against prompt delimiters.

A resume can hide a delimiter tag from a regex while a model still reads it: a zero-width space
inside "</tool_results>", a fullwidth "＜", or bidi controls. `visible()` maps compatibility forms to
their plain characters (NFKC) and drops invisible format and control characters, so delimiter
checks see the same tag the model would. Use it only on text going into a prompt; anything shown
or cited back to a user keeps the original text.
"""
import re
import unicodedata

# Unicode "format" characters (zero-width space/joiners, word joiner, BOM, soft hyphen, bidi
# controls, tag characters) and control characters other than tab, newline and carriage return.
_INVISIBLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def visible(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return _INVISIBLE.sub("", text)
