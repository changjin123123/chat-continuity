"""Optional BPE counters. Estimation only reads verified LOCAL vocabulary files.

Only the explicit prepare-tokenizers command performs network requests, and it
downloads public vocabulary files without accepting conversation inputs.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from .core import ContinuityError


DATA_DIR = Path(__file__).with_name("tokenizer_data")
HASHES = {
    "cl100k_base": "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7",
    "o200k_base": "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d",
}
# Patterns from OpenAI tiktoken, MIT license; see THIRD_PARTY_NOTICES.md.
PATTERNS = {
    "cl100k_base": r"'(?i:[sdmt]|ll|ve|re)|[^\r\n\p{L}\p{N}]?+\p{L}++|\p{N}{1,3}+| ?[^\s\p{L}\p{N}]++[\r\n]*+|\s++$|\s*[\r\n]|\s+(?!\S)|\s",
    "o200k_base": "|".join([
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
        r"\p{N}{1,3}", r" ?[^\s\p{L}\p{N}]+[\r\n/]*",
        r"\s*[\r\n]+", r"\s+(?!\S)", r"\s+",
    ]),
}


def load_encodings(data_dir=None):
    """Never calls get_encoding(), cache loaders, URLs, or a model API."""
    try:
        import tiktoken
    except ImportError as exc:
        raise ContinuityError("BPE unavailable: install tiktoken==0.12.0") from exc
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    encodings = {}
    for name, digest in HASHES.items():
        path = root / (name + ".tiktoken")
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ContinuityError("BPE vocabulary missing: run prepare-tokenizers first") from exc
        if hashlib.sha256(data).hexdigest() != digest:
            raise ContinuityError("BPE vocabulary hash mismatch; no network fallback")
        ranks = {base64.b64decode(token): int(rank)
                 for token, rank in (line.split() for line in data.splitlines() if line)}
        encodings[name] = tiktoken.Encoding(
            name=name, pat_str=PATTERNS[name], mergeable_ranks=ranks,
            special_tokens={},
        )
    return encodings


def prepare_tokenizers(data_dir=None):
    """Explicit setup only. Download fixed, public files; no user text input."""
    from urllib.request import urlopen
    import os
    import tempfile

    root = Path(data_dir) if data_dir is not None else DATA_DIR
    root.mkdir(parents=True, exist_ok=True)
    for name, digest in HASHES.items():
        target = root / (name + ".tiktoken")
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        with urlopen("https://openaipublic.blob.core.windows.net/encodings/" + name + ".tiktoken", timeout=30) as response:
            data = response.read(8_000_001)
        if len(data) > 8_000_000 or hashlib.sha256(data).hexdigest() != digest:
            raise ContinuityError("Public tokenizer download failed integrity check")
        fd, temporary = tempfile.mkstemp(dir=root)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {"prepared": list(HASHES), "conversation_data_sent": False}
