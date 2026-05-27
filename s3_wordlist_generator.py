#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import re
import string
import sys
from pathlib import Path
from urllib.parse import urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_WORDLIST = SCRIPT_DIR / "common-s3-bucket-names-list.txt"
BARE_TOKEN_BOUNDARY = r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9])"

CHARSET_OPTIONS = {
    "1": ("alphabet only", string.ascii_lowercase),
    "2": ("capital alphabet", string.ascii_uppercase),
    "3": ("numbers only", string.digits),
    "4": ("alphabet with numbers", string.ascii_lowercase + string.digits),
    "5": ("capital with numbers", string.ascii_uppercase + string.digits),
    "6": ("alphabet with capital", string.ascii_lowercase + string.ascii_uppercase),
    "7": ("mix of 3", string.ascii_lowercase + string.ascii_uppercase + string.digits),
}


def clean_domain(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("domain cannot be empty")

    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc or parsed.path
    else:
        value = value.split("/", 1)[0]

    if "@" in value:
        value = value.rsplit("@", 1)[1]

    value = value.split(":", 1)[0].strip().strip("/")
    if not value:
        raise ValueError("domain cannot be empty after removing the URL scheme")
    return value.lower()


def has_bare_token(style: str, token: str) -> bool:
    pattern = BARE_TOKEN_BOUNDARY.format(re.escape(token))
    return re.search(pattern, style, re.IGNORECASE) is not None


def replace_bare_token(style: str, token: str, replacement: str) -> str:
    pattern = BARE_TOKEN_BOUNDARY.format(re.escape(token))
    return re.sub(pattern, replacement, style, flags=re.IGNORECASE)


def build_style(
    template: str,
    length: int | None,
    number_placeholder: str | None,
) -> tuple[str, int | None, str | None, bool, bool, bool]:
    uses_domain = "<domain>" in template
    uses_name = "<name>" in template
    uses_token = number_placeholder is not None

    if not uses_domain and not uses_name and not uses_token:
        raise ValueError("style must include at least one placeholder: domain, name, or a number")

    return template, length, number_placeholder, uses_domain, uses_name, uses_token


def parse_angle_style(style: str) -> tuple[str, int | None, str | None, bool, bool, bool]:
    unknown = [
        placeholder
        for placeholder in re.findall(r"<([^>]+)>", style)
        if placeholder not in {"domain", "name"} and not placeholder.isdigit()
    ]
    if unknown:
        raise ValueError(f"unknown placeholder: <{unknown[0]}>")

    placeholder_matches = re.findall(r"<\d+>", style)
    if len(placeholder_matches) > 1:
        raise ValueError("style can include only one number placeholder, like <3>")

    number_placeholder = placeholder_matches[0] if placeholder_matches else None
    length = int(number_placeholder.strip("<>")) if number_placeholder else None
    if length is not None and length <= 0:
        raise ValueError("number placeholder length must be greater than 0")

    return build_style(style, length, number_placeholder)


def parse_bare_style(style: str) -> tuple[str, int | None, str | None, bool, bool, bool]:
    placeholder_matches = re.findall(r"(?<![A-Za-z0-9])\d+(?![A-Za-z0-9])", style)
    if len(placeholder_matches) > 1:
        raise ValueError("style can include only one standalone number length, like 3")

    number_placeholder = None
    length = None
    template = replace_bare_token(style, "domain", "<domain>")
    template = replace_bare_token(template, "name", "<name>")

    if placeholder_matches:
        length = int(placeholder_matches[0])
        if length <= 0:
            raise ValueError("number placeholder length must be greater than 0")
        number_placeholder = f"<{length}>"
        template = re.sub(
            r"(?<![A-Za-z0-9])\d+(?![A-Za-z0-9])",
            number_placeholder,
            template,
            count=1,
        )

    return build_style(template, length, number_placeholder)


def parse_style(style: str) -> tuple[str, int | None, str | None, bool, bool, bool]:
    if "<" in style or ">" in style:
        return parse_angle_style(style)
    return parse_bare_style(style)


def choose_charset() -> tuple[str, str]:
    print("\nGenerated-token type")
    print("--------------------")
    for key, (label, chars) in CHARSET_OPTIONS.items():
        print(f"  {key}) {label:<22} {len(chars):>2} chars")

    while True:
        choice = input("Option: ").strip().lower()
        if choice in CHARSET_OPTIONS:
            return CHARSET_OPTIONS[choice]

        for label, chars in CHARSET_OPTIONS.values():
            if choice == label.lower():
                return label, chars

        print("Please choose a number from 1 to 7.")


def read_names(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"wordlist not found: {path}")

    with path.open("r", encoding="utf-8-sig") as file:
        names = [line.strip() for line in file if line.strip()]

    if not names:
        raise ValueError(f"wordlist is empty: {path}")
    return names


def generated_tokens(charset: str, length: int):
    for chars in itertools.product(charset, repeat=length):
        yield "".join(chars)


def write_wordlist(
    template: str,
    domain: str,
    names: list[str] | None,
    number_placeholder: str | None,
    charset: str | None,
    length: int | None,
    output_path: Path,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    name_values = names if names is not None else [""]
    count = 0

    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        for name in name_values:
            base = template.replace("<domain>", domain).replace("<name>", name)

            if number_placeholder is None:
                file.write(base)
                file.write("\n")
                count += 1
                continue

            for token in generated_tokens(charset or "", length or 0):
                file.write(base.replace(number_placeholder, token))
                file.write("\n")
                count += 1

    return count


def prompt_non_empty(label: str) -> str:
    while True:
        value = input(label).strip()
        if value:
            return value
        print("This value cannot be empty.")


def describe_generation(
    name_count: int,
    token_count: int,
    charset_label: str | None,
    uses_name: bool,
    uses_token: bool,
) -> str:
    parts = []
    if uses_name:
        parts.append(f"{name_count:,} names")
    if uses_token:
        parts.append(f"{token_count:,} {charset_label} tokens")
    if not parts:
        parts.append("1 static template")
    return " x ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate S3 bucket-name wordlists from a reusable style.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=f"""Examples:
  python s3_wordlist_generator.py 1-name--domain
  python s3_wordlist_generator.py domain-1
  python s3_wordlist_generator.py name_domain
  python s3_wordlist_generator.py "<domain>-<1>"

Style placeholders:
  domain    target domain, entered later at the prompt
  name      each line from {DEFAULT_WORDLIST.name}
  1, 2, 3   generated token length

You can use any subset of the placeholders:
  domain-1      domain + generated token
  domain-name   domain + common names
  name-2        common names + generated token

Notes:
  The unquoted style avoids < and > because shells treat them as redirection.
  Put {DEFAULT_WORDLIST.name} in the same folder as this script.""",
    )
    parser.add_argument(
        "style",
        help="Style template, for example: 1-name--domain, domain-1, or name_domain",
    )
    parser.add_argument(
        "--wordlist",
        type=Path,
        default=DEFAULT_WORDLIST,
        help="Base names wordlist. Default: common-s3-bucket-names-list.txt beside the script.",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()

    try:
        template, length, number_placeholder, uses_domain, uses_name, uses_token = parse_style(args.style)
        names = read_names(args.wordlist) if uses_name else None
        domain = clean_domain(prompt_non_empty("Domain: ")) if uses_domain else ""

        charset_label = None
        charset = None
        if uses_token:
            charset_label, charset = choose_charset()

        output_path = Path(prompt_non_empty("\nOutput file name: ")).expanduser()

        name_count = len(names) if names is not None else 1
        token_count = len(charset or "") ** (length or 0) if uses_token else 1
        total_count = name_count * token_count
        details = describe_generation(name_count, token_count, charset_label, uses_name, uses_token)
        print(f"\nGenerating {total_count:,} lines ({details})...")

        written = write_wordlist(
            template=template,
            domain=domain,
            names=names,
            number_placeholder=number_placeholder,
            charset=charset,
            length=length,
            output_path=output_path,
        )
    except (OSError, ValueError) as error:
        print(f"Error: {error}")
        return 1

    print(f"Done. Wrote {written:,} lines to {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
