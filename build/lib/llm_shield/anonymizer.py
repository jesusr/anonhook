from __future__ import annotations

import re
from dataclasses import dataclass

from .config import ShieldConfig


@dataclass(frozen=True)
class ScrubResult:
    text: str
    mapping: dict[str, str]


def scrub(
    text: str,
    config: ShieldConfig,
    mapping: dict[str, str] | None = None,
) -> ScrubResult:
    candidates: list[tuple[int, int, str]] = []
    for term in sorted(set(config.terms), key=len, reverse=True):
        if not term:
            continue
        candidates.extend((match.start(), match.end(), match.group()) for match in re.finditer(re.escape(term), text))
    for pattern in config.patterns:
        candidates.extend(
            (match.start(), match.end(), match.group())
            for match in re.finditer(pattern.regex, text)
            if match.start() != match.end()
        )

    candidates.sort(key=lambda match: (match[0], -(match[1] - match[0])))
    token_to_value = dict(mapping or {})
    replacements = {value: token for token, value in token_to_value.items()}
    indices = [
        int(match.group(1))
        for token in token_to_value
        if (match := re.fullmatch(re.escape(config.placeholder_prefix) + r"(\d+)", token))
    ]
    next_index = max(indices, default=-1) + 1
    chunks: list[str] = []
    cursor = 0
    for start, end, value in candidates:
        if start < cursor:
            continue
        token = replacements.get(value)
        if token is None:
            token = f"{config.placeholder_prefix}{next_index}"
            while token in text:
                next_index += 1
                token = f"{config.placeholder_prefix}{next_index}"
            next_index += 1
            replacements[value] = token
            token_to_value[token] = value
        chunks.extend((text[cursor:start], token))
        cursor = end
    chunks.append(text[cursor:])
    return ScrubResult("".join(chunks), token_to_value)


def restore(text: str, mapping: dict[str, str]) -> str:
    if not mapping:
        return text
    tokens = sorted(mapping, key=len, reverse=True)
    matcher = re.compile("|".join(re.escape(token) for token in tokens))
    return matcher.sub(lambda match: mapping[match.group()], text)
