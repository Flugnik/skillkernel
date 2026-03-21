"""CLI main entrypoint."""

from __future__ import annotations

import sys
from typing import Callable

from .adapter import process_text


def main(argv: list[str] | None = None, input_func: Callable[[], str] = input) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        text = " ".join(args)
    else:
        print("введите текст:")
        text = input_func().strip()

    result = process_text(text)
    print(f"[{result.type}] {result.content}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

