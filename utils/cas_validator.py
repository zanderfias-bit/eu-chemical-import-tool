import re


def validate_cas(cas):

    cas = cas.strip()

    pattern = r"^\d{2,7}-\d{2}-\d$"

    if not re.match(pattern, cas):
        return False

    body, checksum = cas.rsplit("-", 1)

    digits = body.replace("-", "")

    total = 0

    for i, digit in enumerate(reversed(digits), start=1):
        total += int(digit) * i

    return total % 10 == int(checksum)