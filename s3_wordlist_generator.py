#!/usr/bin/env python3
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
    return re.search(BARE_TOKEN_BOUNDARY.format(re.escape(token)), style, re.IGNORECASE) is not None


def replace_bare_token(style: str, token: str, replacement: str) -> str:
    pattern = BARE_TOKEN_BOUNDARY.format(re.escape(token))
    return re.sub(pattern, replacement, style, flags=re.IGNORECASE)


def parse_angle_style(style: str) -> tuple[str, int, str]:
    if "<domain>" not in style:
        raise ValueError("style must include <domain>")
    if "<name>" not in style:
        raise ValueError("style must include <name>")

    placeholder_matches = re.findall(r"<\d+>", style)
    if len(placeholder_matches) != 1:
        raise ValueError("style must include exactly one number placeholder, like <3>")

    number_placeholder = placeholder_matches[0]
    length = int(number_placeholder.strip("<>"))
    if length <= 0:
        raise ValueError("number placeholder length must be greater than 0")

    return style, length, number_placeholder


def parse_bare_style(style: str) -> tuple[str, int, str]:
    if not has_bare_token(style, "domain"):
        raise ValueError("style must include the domain placeholder")
    if not has_bare_token(style, "name"):
        raise ValueError("style must include the name placeholder")

    placeholder_matches = re.findall(r"(?<![A-Za-z0-9])\d+(?![A-Za-z0-9])", style)
    if len(placeholder_matches) != 1:
        raise ValueError("style must include exactly one standalone number length, like 3")

    length = int(placeholder_matches[0])
    if length <= 0:
        raise ValueError("number placeholder length must be greater than 0")

    template = replace_bare_token(style, "domain", "<domain>")
    template = replace_bare_token(template, "name", "<name>")
    template = re.sub(
        r"(?<![A-Za-z0-9])\d+(?![A-Za-z0-9])",
        f"<{length}>",
        template,
        count=1,
    )
    return template, length, f"<{length}>"


def parse_style(style: str) -> tuple[str, int, str]:
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
    names: list[str],
    number_placeholder: str,
    charset: str,
    length: int,
    output_path: Path,
) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with output_path.open("w", encoding="utf-8", newline="\n") as file:
        for name in names:
            base = template.replace("<domain>", domain).replace("<name>", name)
            for token in generated_tokens(charset, length):
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate S3 bucket-name wordlists from a reusable style.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=f"""Examples:
  python s3_wordlist_generator.py 1-name--domain
  python s3_wordlist_generator.py name_domain-2
  python s3_wordlist_generator.py "<1>-<name>--<domain>"

Style placeholders:
  domain    target domain, entered later at the prompt
  name      each line from {DEFAULT_WORDLIST.name}
  1, 2, 3   generated token length

Notes:
  The unquoted style avoids < and > because shells treat them as redirection.
  Put {DEFAULT_WORDLIST.name} in the same folder as this script.""",
    )
    parser.add_argument(
        "style",
        help="Style template, for example: 1-name--domain or name_domain-2",
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
        template, length, number_placeholder = parse_style(args.style)
        names = read_names(args.wordlist)

        domain = clean_domain(prompt_non_empty("Domain: "))
        charset_label, charset = choose_charset()
        output_path = Path(prompt_non_empty("\nOutput file name: ")).expanduser()

        token_count = len(charset) ** length
        total_count = token_count * len(names)
        print(
            f"\nGenerating {total_count:,} lines "
            f"({len(names):,} names x {token_count:,} {charset_label} tokens)..."
        )

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
