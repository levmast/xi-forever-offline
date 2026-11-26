"""Certificate checks for every online call the launcher makes (2026-11-25).

Why: on some Windows PCs the "intermediate certificates" store still holds an old copy of Let's Encrypt's
"ISRG Root X2" (signed by ISRG Root X1, expired 15 September 2025). Python reads that store along with the trusted
roots, picks the expired copy while checking xiforever.com, chat.xiforever.com or the hub, and gives up with
"certificate has expired" - although Windows itself (PowerShell, browsers) gets in fine. Seen on the user's own PC:
hardcore news never reached the hub, and every Python call to xiforever.com failed.

The fix: check certificates against Windows' trusted ROOT store only (no intermediates) plus Mozilla's list from
certifi (bundled in the exe; it also covers a fresh PC that has not fetched a root yet). The servers send their own
intermediates, so nothing else is needed. install() makes this the default for urllib and for
ssl.create_default_context(), so every module gets it without passing a context around. Other systems keep
Python's normal check (plus certifi).
"""
import os, ssl, sys

_ORIGINAL = ssl.create_default_context
_SERVER_AUTH = "1.3.6.1.5.5.7.3.1"


def _windows_roots(context):
    loaded = 0
    for store in ("ROOT",):
        try:
            items = ssl.enum_certificates(store)
        except (AttributeError, OSError, PermissionError):
            continue
        for cert, encoding, trust in items:
            if encoding != "x509_asn":
                continue
            if trust is not True and _SERVER_AUTH not in trust:
                continue                                   # a root Windows does not trust for websites
            try:
                context.load_verify_locations(cadata=cert)
                loaded += 1
            except ssl.SSLError:
                pass
    return loaded


def _certifi(context):
    try:
        import certifi
        context.load_verify_locations(cafile=certifi.where())
        return True
    except (ImportError, OSError, ssl.SSLError):
        return False


def client_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
    """Drop-in for ssl.create_default_context(): the same settings, without Windows' intermediate store."""
    if purpose != ssl.Purpose.SERVER_AUTH or cafile or capath or cadata or sys.platform != "win32":
        context = _ORIGINAL(purpose, cafile=cafile, capath=capath, cadata=cadata)
        if purpose == ssl.Purpose.SERVER_AUTH and not (cafile or capath or cadata):
            _certifi(context)
        return context
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)        # check_hostname on, CERT_REQUIRED
    got = _windows_roots(context)
    if not _certifi(context) and not got:
        return _ORIGINAL(purpose)                            # nothing loaded: Python's own way is better than none
    return context


def install():
    """Makes client_context the default for urllib (no context given) and for ssl.create_default_context()."""
    if getattr(ssl, "_xifo_tls", False):
        return
    ssl.create_default_context = client_context
    ssl._create_default_https_context = client_context
    ssl._xifo_tls = True


if __name__ == "__main__":                                   # python launcher_tls.py  -> tries the project's addresses
    import urllib.request
    install()
    for url in ("https://xiforever.com/", "https://chat.xiforever.com/health", "https://api.github.com/"):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                print(url, r.status)
        except Exception as problem:
            print(url, "FAILED:", problem)
