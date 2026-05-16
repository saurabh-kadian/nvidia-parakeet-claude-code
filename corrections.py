"""
Post-processing corrections for Parakeet ASR output.

Each entry is (pattern, replacement) using Python regex syntax.
- Patterns are matched case-insensitively and in order.
- Use r'...' raw strings for patterns with backslashes.
- Capture groups in patterns can be referenced in replacements as \1, \2 etc.

Add your own domain vocabulary here.
"""

CORRECTIONS = [
    # ── Model names ────────────────────────────────────────────────────────────
    # "gemma 4 b" / "gemma four b" / "gemma for b" / "gemma 4 b model" → "gemma:4b"
    (r'\bgemma\s+(?:4|four|for)\s*b\b',         'gemma:4b'),
    (r'\bgemma\s+(?:2|two)\s*b\b',              'gemma:2b'),
    (r'\bgemma\s+(?:7|seven)\s*b\b',            'gemma:7b'),
    (r'\bgemma\s+(?:9|nine)\s*b\b',             'gemma:9b'),
    (r'\bgemma\s+(?:27|twenty.?seven)\s*b\b',   'gemma:27b'),

    # "llama 3" / "llama three" → "llama3"
    (r'\bllama\s+(?:3|three)\b',                'llama3'),
    (r'\bllama\s+3\s*[.·]\s*2\b',              'llama3.2'),
    (r'\bllama\s+(?:3|three)\s+(?:8|eight)\s*b\b',   'llama3:8b'),
    (r'\bllama\s+(?:3|three)\s+(?:70|seventy)\s*b\b', 'llama3:70b'),

    # "mistral 7 b" → "mistral:7b"
    (r'\bmistral\s+(?:7|seven)\s*b\b',          'mistral:7b'),

    # "phi 3" / "phi three" → "phi3"
    (r'\bphi\s+(?:3|three)\b',                  'phi3'),
    (r'\bphi\s+(?:4|four)\b',                   'phi4'),

    # "deep seek" / "deep-seek" → "deepseek"
    (r'\bdeep[\s-]seek\b',                      'deepseek'),

    # "queue wen" / "q wen" → "qwen"
    (r'\b(?:queue|q)\s*wen\b',                  'qwen'),

    # ── Tools & products ──────────────────────────────────────────────────────
    # "ol lama" / "ol' lama" → "ollama"
    (r"\bol['\s-]?lama\b",                      'ollama'),

    # "hugging face" → "HuggingFace"
    (r'\bhugging\s+face\b',                     'HuggingFace'),

    # "pi torch" / "pie torch" → "PyTorch"
    (r'\b(?:pi|pie)\s*torch\b',                 'PyTorch'),

    # "tensor flow" → "TensorFlow"
    (r'\btensor\s*flow\b',                      'TensorFlow'),

    # "cuda" capitalisation
    (r'\bcuda\b',                               'CUDA'),

    # ── Units & notation ──────────────────────────────────────────────────────
    # "3 b parameters" → "3B parameters"
    (r'\b(\d+)\s*b\s+(?=param|model)',          r'\1B '),

    # "dot py" → ".py"
    (r'\bdot\s+py\b',                           '.py'),

    # "dot json" → ".json"
    (r'\bdot\s+json\b',                         '.json'),

    # "dot yaml" / "dot yml" → ".yaml"
    (r'\bdot\s+ya?ml\b',                        '.yaml'),
]
