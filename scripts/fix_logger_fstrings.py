"""Converte logger.LEVEL(f"...{expr}...") para logger.LEVEL("...%s...", expr)."""

import os
import re

BASE = os.path.join(os.path.dirname(__file__), "..", "app")

PATTERN = re.compile(
    r'(logger\.(info|warning|error|debug|exception|critical))\(f"((?:[^"\\]|\\.)*)"\)'
)


def extract_fstring_parts(fstring_content):
    """Return (template_with_%s, [args]) from an f-string body."""
    args = []
    result = ""
    i = 0
    n = len(fstring_content)
    while i < n:
        ch = fstring_content[i]
        if ch == "{":
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if fstring_content[j] == "{":
                    depth += 1
                elif fstring_content[j] == "}":
                    depth -= 1
                j += 1
            expr = fstring_content[i + 1 : j - 1]
            # Strip str() wrapper: str(e) -> e
            m = re.match(r"^str\((.+)\)$", expr)
            if m:
                expr = m.group(1)
            args.append(expr)
            result += "%s"
            i = j
        else:
            result += ch
            i += 1
    return result, args


def fix_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    original = content
    count = 0

    def replacer(m):
        nonlocal count
        full_call = m.group(1)  # logger.LEVEL
        fstring_content = m.group(3)
        template, args = extract_fstring_parts(fstring_content)
        count += 1
        if not args:
            return f'{full_call}("{template}")'
        return f'{full_call}("{template}", {", ".join(args)})'

    content = PATTERN.sub(replacer, content)
    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  {os.path.relpath(filepath, BASE)}: {count} corrigidos")
    return count


def main():
    total = 0
    for root, dirs, files in os.walk(os.path.abspath(BASE)):
        dirs[:] = [d for d in dirs if d not in (".venv", "__pycache__", ".git")]
        for fname in sorted(files):
            if fname.endswith(".py"):
                total += fix_file(os.path.join(root, fname))
    print(f"\nTotal: {total} ocorrências corrigidas")


if __name__ == "__main__":
    main()
