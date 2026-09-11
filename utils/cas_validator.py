import re


CAS_PATTERN = re.compile(
    r"^\d{2,7}-\d{2}-\d$"
)


def validate_cas(cas_number):
    """
    Validate both the CAS number format and checksum.

    Example of a valid CAS number:
    110-94-1
    """

    if not cas_number:
        return False

    cas_number = cas_number.strip().replace(" ", "")

    if not CAS_PATTERN.fullmatch(cas_number):
        return False

    body, check_digit_text = cas_number.rsplit(
        "-",
        1,
    )

    digits = body.replace("-", "")
    check_digit = int(check_digit_text)

    calculated_total = 0

    for position, digit in enumerate(
        reversed(digits),
        start=1,
    ):
        calculated_total += int(digit) * position

    calculated_check_digit = calculated_total % 10

    return calculated_check_digit == check_digit