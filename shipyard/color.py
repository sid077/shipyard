"""Colour maths, so a palette can be judged before anyone writes code.

The same formulas the app uses at runtime in
`templates/expo-app/src/theme/index.ts`. Keeping a Python copy means a
low-contrast palette fails contract validation in stage 30 rather than being
discovered by a screenshot probe in stage 65 - or by a user.

WCAG 2.1 SC 1.4.3 / 1.4.11 thresholds:
  4.5:1  normal body text
  3.0:1  large text (>= 18.66pt regular or 14pt bold) and non-text UI
"""

from __future__ import annotations

import re

TEXT_CONTRAST = 4.5
LARGE_TEXT_CONTRAST = 3.0
NON_TEXT_CONTRAST = 3.0

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class ColorError(ValueError):
    pass


def parse_hex(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not HEX_RE.match(value):
        raise ColorError(f"{value!r} is not a hex colour like #1f6feb")
    digits = value.lstrip("#")
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return tuple(int(digits[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def relative_luminance(value: str) -> float:
    """WCAG 2.1 relative luminance."""

    def channel(raw: int) -> float:
        c = raw / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in parse_hex(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """Contrast between two colours: 1.0 (identical) to 21.0 (black on white)."""
    light, dark = sorted((relative_luminance(a), relative_luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def readable_on(background: str) -> str:
    """Black or white, whichever is legible on the given background."""
    return (
        "#ffffff"
        if contrast_ratio("#ffffff", background) >= contrast_ratio("#000000", background)
        else "#000000"
    )


def check_contrast(
    pairs: list[tuple[str, str, str, float]],
) -> list[str]:
    """Check (label, foreground, background, minimum) pairs.

    Returns one readable problem per failing pair, shaped so a design role can
    act on it: it names the ratio it achieved and the one it needed.
    """
    problems: list[str] = []
    for label, foreground, background, minimum in pairs:
        ratio = contrast_ratio(foreground, background)
        if ratio + 1e-9 < minimum:
            problems.append(
                f"{label}: {foreground} on {background} is {ratio:.2f}:1, "
                f"needs at least {minimum}:1 - darken the foreground or "
                f"lighten the background"
            )
    return problems
