"""Shared HTTPS client factory — the ONE place Greco builds an outbound client.

Build an httpx client that verifies TLS using the operating system's NATIVE
trust store, via the `truststore` package.

Why this matters here: this machine's network re-signs HTTPS through a
corporate/AV middlebox whose CA lives in the Windows certificate store but
has its Basic Constraints extension not marked "critical". OpenSSL 3.x (which
ships with Python 3.11+ — so our Python 3.14 venv) rejects that cert as
malformed, while Windows' own verifier (SChannel) accepts it. The old Python
3.8 build used an OpenSSL that also tolerated it, which is why this only broke
after the interpreter upgrade. `truststore` delegates verification to SChannel
on Windows (and to the native store on macOS/Linux), so the chain validates
exactly as the OS would — the correct, secure fix, and one that also works
unchanged on a clean cloud host where there is no interception.

Fallback: if `truststore` isn't installed, build a context from certifi plus
whatever Windows roots load cleanly (the pre-upgrade behaviour).

History note: this logic used to be duplicated in narrator.py and importers.py;
only the narrator copy got the truststore fix after the Python 3.14 upgrade, so
every Lichess fetch kept failing with CERTIFICATE_VERIFY_FAILED while narration
worked. Centralising it here is the fix for that class of bug.
"""
from __future__ import annotations

import ssl

import httpx

# Chess-site APIs (notably api.chess.com) reject clients with no/default UA.
USER_AGENT = "Greco chess analyzer (personal-use; github.com/JamesTyhurst)"


def make_http_client(timeout_seconds: float = 30.0) -> httpx.Client:
    """Return an httpx.Client with OS-native TLS verification (see module doc)."""
    timeout = httpx.Timeout(timeout_seconds)
    headers = {"User-Agent": USER_AGENT}
    try:
        import truststore

        ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        return httpx.Client(verify=ctx, timeout=timeout, headers=headers)
    except Exception:
        pass  # fall back to the manual context below

    ctx = ssl.create_default_context()
    try:
        ctx.load_default_certs()  # pulls Windows / macOS / Linux system roots
        if hasattr(ssl, "enum_certificates"):  # Windows only
            for store_name in ("ROOT", "CA"):
                try:
                    for cert, encoding, _trust in ssl.enum_certificates(store_name):
                        if encoding == "x509_asn":
                            try:
                                ctx.load_verify_locations(
                                    cadata=ssl.DER_cert_to_PEM_cert(cert)
                                )
                            except ssl.SSLError:
                                pass
                except (OSError, FileNotFoundError):
                    pass
    except Exception:
        pass
    return httpx.Client(verify=ctx, timeout=timeout, headers=headers)
