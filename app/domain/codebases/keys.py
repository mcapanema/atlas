import re

# A tracker key such as DEP-123: a letter-led prefix, a hyphen, digits, and
# no letter or digit glued on either side. Branch names are lower case.
_KEY = re.compile(r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]{0,9}-\d{1,7})(?![A-Za-z0-9])")


def work_item_keys(*texts: str) -> tuple[str, ...]:
    """Work-item keys found in the texts: upper-cased, unique, first-seen order."""
    found: dict[str, None] = {}
    for text in texts:
        for match in _KEY.finditer(text):
            found.setdefault(match.group(1).upper())
    return tuple(found)
