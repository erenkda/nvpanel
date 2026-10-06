from .base import Backend, BackendError, Monitor


def available_backends() -> dict:
    """Return {id: class} for backends usable in the current session."""
    found = {}
    from .x11 import X11Backend

    if X11Backend.available():
        found["x11"] = X11Backend
    try:
        from .mutter import MutterBackend

        if MutterBackend.available():
            found["mutter"] = MutterBackend
    except (ImportError, ValueError):
        pass
    return found


def pick_backend(preferred=None) -> Backend:
    import os

    found = available_backends()
    if preferred:
        if preferred not in found:
            raise BackendError(f"Backend '{preferred}' is not available here")
        return found[preferred]()
    # Native X11 sessions get the full feature set; otherwise use Mutter.
    order = ["x11", "mutter"] if os.environ.get("XDG_SESSION_TYPE") == "x11" else ["mutter", "x11"]
    for key in order:
        if key in found:
            return found[key]()
    raise BackendError(
        "No supported backend found (needs an X11 session or GNOME/Mutter)."
    )
