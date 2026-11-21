import sys

import smart_err_corrector


def trigger_key_error() -> None:
    scores = {"alice": 90}
    print(scores["bob"])


def trigger_index_error() -> None:
    items = ["first", "second"]
    print(items[5])


def trigger_value_error() -> None:
    raw = "not-an-int"
    print(int(raw))


CASES = {
    "1": ("KeyError rule", trigger_key_error),
    "2": ("IndexError rule", trigger_index_error),
    "3": ("ValueError (Groq / fallback)", trigger_value_error),
}


def main() -> None:
    smart_err_corrector.enable()

    choice = sys.argv[1] if len(sys.argv) > 1 else ""
    if choice not in CASES:
        print("Choose a scenario to trigger:")
        for key, (label, _) in CASES.items():
            print(f"  {key}. {label}")
        choice = input("Enter 1, 2, or 3: ").strip()

    if choice not in CASES:
        print("Invalid choice. Exiting cleanly.")
        return

    _, fn = CASES[choice]
    fn()


if __name__ == "__main__":
    main()
