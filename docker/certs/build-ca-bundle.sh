#!/usr/bin/env bash
# ─── Build a CA bundle combining certifi + system corporate CAs ──────
# This script extracts corporate CA certificates (e.g. Zscaler) from the
# macOS System Keychain and appends them to the certifi CA bundle.
# The result is written to docker/certs/ca-bundle.crt for Docker use.
#
# Usage: ./docker/certs/build-ca-bundle.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT="$SCRIPT_DIR/ca-bundle.crt"

echo "Building CA bundle for Docker containers..."

# Start with the system cert bundle (contains standard CAs)
if [ -f /etc/ssl/cert.pem ]; then
    cp /etc/ssl/cert.pem "$OUTPUT"
    echo "  Base: /etc/ssl/cert.pem"
else
    echo "ERROR: /etc/ssl/cert.pem not found"
    exit 1
fi

# Append corporate CAs from System Keychain (Zscaler, etc.)
CORPORATE_CAS=$(security find-certificate -a -p /Library/Keychains/System.keychain 2>/dev/null | \
    python3 -c "
import sys, re
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
except ImportError:
    sys.exit(0)  # Skip if cryptography not available

pem_data = sys.stdin.read()
certs = re.findall(r'(-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----)', pem_data, re.DOTALL)
for pem in certs:
    try:
        cert = x509.load_pem_x509_certificate(pem.encode(), default_backend())
        subject = cert.subject.rfc4514_string().lower()
        if 'zscaler' in subject or 'corporate' in subject:
            print(pem)
    except Exception:
        pass
" 2>/dev/null || true)

if [ -n "$CORPORATE_CAS" ]; then
    echo "" >> "$OUTPUT"
    echo "# Corporate CA certificates (extracted from macOS System Keychain)" >> "$OUTPUT"
    echo "$CORPORATE_CAS" >> "$OUTPUT"
    echo "  Added: Corporate CA certificates (Zscaler)"
else
    echo "  Note: No corporate CAs found in System Keychain"
fi

echo "  Output: $OUTPUT"
echo "Done."
