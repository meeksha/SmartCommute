"""Trust an extra root certificate for outbound HTTPS (Google sign-in, TomTom, weather, OSRM).

Some networks and antivirus products (college/office firewalls, Kaspersky, Avast, Zscaler, FortiGate...)
inspect HTTPS by re-signing every site with their own root certificate. Windows trusts that root, but the
backend's Linux container doesn't, so calls fail with CERTIFICATE_VERIFY_FAILED ("self-signed certificate").

Put that root certificate (PEM / Base-64 .crt, .cer or .pem) in the `certs/` folder next to
docker-compose.yml (mounted at /app/certs), or point EXTRA_CA_CERTS at a file. At startup we build one
bundle = the normal public roots (certifi) + those files, and point Python's ssl, requests and httpx at it.
Nothing is turned off: certificates are still fully verified.
"""
from __future__ import annotations

import glob
import os

CERT_DIR = os.environ.get("EXTRA_CA_DIR", "/app/certs")
BUNDLE_PATH = "/tmp/smartcommute-ca-bundle.pem"


def install_extra_ca() -> list[str]:
    files = []
    single = os.environ.get("EXTRA_CA_CERTS")
    if single and os.path.isfile(single):
        files.append(single)
    for pattern in ("*.crt", "*.cer", "*.pem"):
        files.extend(sorted(glob.glob(os.path.join(CERT_DIR, pattern))))
    extra = []
    for f in files:
        try:
            text = open(f, "rb").read().decode("ascii", errors="ignore")
        except OSError:
            continue
        if "BEGIN CERTIFICATE" in text:
            extra.append(text.strip())
        else:
            print(f"[certs] skipped {f}: not a Base-64 (PEM) certificate. Export it as 'Base-64 encoded X.509'.")
    if not extra:
        return []
    import certifi
    with open(certifi.where(), "r", encoding="utf-8") as base, open(BUNDLE_PATH, "w", encoding="utf-8") as out:
        out.write(base.read().rstrip() + "\n\n" + "\n\n".join(extra) + "\n")
    for var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        os.environ[var] = BUNDLE_PATH
    print(f"[certs] trusting {len(extra)} extra root certificate(s) from {', '.join(files)}")
    return files
