from .hook import ErrorHook

_hook = ErrorHook()


def enable() -> None:
    _hook.install()


def disable() -> None:
    _hook.uninstall()


__all__ = ["ErrorHook", "disable", "enable"]
