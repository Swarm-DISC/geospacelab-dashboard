"""Map raw exceptions/credential gaps to short, user-facing messages."""

from __future__ import annotations


def friendly_error(exc: BaseException) -> str:
    name = type(exc).__name__
    msg = str(exc).strip()
    low = msg.lower()
    if "cartopy" in low:
        return "Optional dependency 'cartopy' is required for maps. Install the [geo] extra."
    if any(k in low for k in ("apexpy", "aacgmv2")):
        return "Optional coordinate dependency missing. Install the [apex] extra (needs a Fortran compiler)."
    if any(k in low for k in ("401", "403", "unauthor", "forbidden", "credential", "password", "authentication")):
        return f"Authentication failed — check the source credentials in ~/.geospacelab/config.toml. ({name})"
    if "product version" in low:
        return "geospacelab requires downloading to be enabled for this product (the runner sets allow_download)."
    if isinstance(exc, FileNotFoundError) or any(k in low for k in ("no such file", "not found", "no data", "empty")):
        return "No data found for this selection and time range. Try a different time or product."
    if isinstance(exc, MemoryError):
        return "Ran out of memory building the preview — shorten the time range."
    if isinstance(exc, TimeoutError):
        return "Preview timed out. Shorten the time range or run the generated code locally."
    return f"{name}: {msg}" if msg else name


def credential_message(kind: str | None, product_label: str) -> str:
    hints = {
        "esa_eo": "Set [datahub.esa_eo] username in ~/.geospacelab/config.toml (password stored via keyring).",
        "madrigal": "Set [datahub.madrigal] user_fullname / user_email / user_affiliation in ~/.geospacelab/config.toml.",
        "vires": "Configure a VirES token (`viresclient set_token ...`) or set VIRES_TOKEN.",
    }
    hint = hints.get(kind or "", "")
    return f"{product_label} needs {kind} credentials. {hint} The generated code is still ready to copy."
