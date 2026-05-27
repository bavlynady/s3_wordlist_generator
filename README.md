# S3 Wordlist Generator

Build S3 bucket-name wordlists from a domain, a common-name list, and generated tokens.
Use it to create wordlists that follow a specific pattern for authorized S3 bucket testing.

## Quick Start

python3 s3_wordlist_generator.py 1-name--domain


This creates candidates in this format:

```text
<generated-token>-<common-name>--<domain>
```

## Examples

```powershell
python s3_wordlist_generator.py 1-name--domain
python s3_wordlist_generator.py name_domain-2
python s3_wordlist_generator.py domain-name-3
```

## Template Parts

| Part | Meaning |
| --- | --- |
| `domain` | The domain you enter when the script asks |
| `name` | Each line from `common-s3-bucket-names-list.txt` |
| `1`, `2`, `3` | Generated token length |

## Prompts

The script asks for:

1. Domain, such as `https://example.com`, `example.com`, or `example`
2. Token type, such as numbers only or alphabet with numbers
3. Output file name

## Angle Style

Quoted angle style still works:

```powershell
python s3_wordlist_generator.py "<1>-<name>--<domain>"
```

Do not run angle style without quotes because `<` and `>` are shell redirection characters.
