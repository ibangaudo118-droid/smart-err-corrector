import smart_err_corrector

smart_err_corrector.enable()


def divide_items(total: int, count: int) -> int:
    return total // count


def main() -> None:
    print("Result:", divide_items(50, 0))


if __name__ == "__main__":
    main()
