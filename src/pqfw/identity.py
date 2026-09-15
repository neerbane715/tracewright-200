"""Offline identity management.

PS requirement A13: no dependency on external cloud KMS services. Identities
live in a local directory; there is no CA, no enrolment server, no network.

Trust model for an air-gapped deployment: public identities are exported to
files and exchanged physically (USB, printed QR, internal share). A sender pins
a recipient by FINGERPRINT -- a hash over both public keys -- so substituting a
key changes the fingerprint and breaks the pin. This is the same trust-on-first-
use model SSH uses, which is appropriate when no online CA can exist.

Secret keys never leave the keystore directory, and only the owning recipient's
process reads them (PS requirement A5: the recipient's OWN key signs).
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from .crypto import kem_keygen, sig_keygen, KEM_ALG, SIG_ALG
from .records import PublicIdentity, b64d, b64e


class IdentityError(Exception):
    pass


class Keystore:
    """A directory of identities. One subdirectory per user."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # -- creation ---------------------------------------------------------

    def create(self, user_id: str, overwrite: bool = False) -> PublicIdentity:
        """Generate a fresh PQ identity: one ML-KEM pair + one ML-DSA pair.

        Separate keys per purpose. Reusing one keypair for both encryption and
        signing is a long-standing cryptographic error and would also be
        impossible here, since ML-KEM and ML-DSA are different algorithms.
        """
        d = self.root / user_id
        if d.exists() and not overwrite:
            raise IdentityError(
                f"identity '{user_id}' already exists; pass overwrite=True "
                f"to replace it"
            )
        d.mkdir(parents=True, exist_ok=True)

        kem_pub, kem_sec = kem_keygen()
        sig_pub, sig_sec = sig_keygen()

        ident = PublicIdentity(user_id=user_id, kem_public=kem_pub,
                               sig_public=sig_pub)

        self._write(d / "public.json", json.dumps({
            "user_id": user_id,
            "kem_alg": KEM_ALG, "sig_alg": SIG_ALG,
            "kem_public": b64e(kem_pub), "sig_public": b64e(sig_pub),
            "fingerprint": ident.fingerprint,
        }, indent=2).encode())

        self._write(d / "secret.json", json.dumps({
            "user_id": user_id,
            "kem_alg": KEM_ALG, "sig_alg": SIG_ALG,
            "kem_secret": b64e(kem_sec), "sig_secret": b64e(sig_sec),
            "fingerprint": ident.fingerprint,
        }, indent=2).encode(), secret=True)

        return ident

    @staticmethod
    def _write(path: Path, data: bytes, secret: bool = False) -> None:
        path.write_bytes(data)
        if secret:
            # Best-effort 0600. On Windows this is advisory only; a real
            # deployment would use DPAPI or a smartcard. Stated, not hidden.
            try:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass

    # -- reading ----------------------------------------------------------

    def public(self, user_id: str) -> PublicIdentity:
        p = self.root / user_id / "public.json"
        if not p.exists():
            raise IdentityError(f"no identity '{user_id}' in {self.root}")
        d = json.loads(p.read_text())
        return PublicIdentity(user_id=d["user_id"],
                              kem_public=b64d(d["kem_public"]),
                              sig_public=b64d(d["sig_public"]))

    def secrets(self, user_id: str) -> tuple[bytes, bytes]:
        """Return (kem_secret, sig_secret). Only the owner should call this."""
        p = self.root / user_id / "secret.json"
        if not p.exists():
            raise IdentityError(
                f"no secret key for '{user_id}' in {self.root} -- this "
                f"identity is public-only on this machine"
            )
        d = json.loads(p.read_text())
        return b64d(d["kem_secret"]), b64d(d["sig_secret"])

    def has_secret(self, user_id: str) -> bool:
        return (self.root / user_id / "secret.json").exists()

    def list_identities(self) -> list[str]:
        return sorted(
            p.name for p in self.root.iterdir()
            if p.is_dir() and (p / "public.json").exists()
        )

    # -- exchange ---------------------------------------------------------

    def export_public(self, user_id: str, dest: str | Path) -> Path:
        """Write a shareable public identity file (physical transfer)."""
        dest = Path(dest)
        dest.write_text((self.root / user_id / "public.json").read_text())
        return dest

    def import_public(self, src: str | Path) -> PublicIdentity:
        """Import someone else's public identity.

        Refuses to silently overwrite an existing identity whose fingerprint
        differs -- that is exactly the key-substitution attack the pin exists
        to catch, so it must be loud.
        """
        d = json.loads(Path(src).read_text())
        ident = PublicIdentity(user_id=d["user_id"],
                               kem_public=b64d(d["kem_public"]),
                               sig_public=b64d(d["sig_public"]))
        existing = self.root / ident.user_id / "public.json"
        if existing.exists():
            old = json.loads(existing.read_text()).get("fingerprint")
            if old and old != ident.fingerprint:
                raise IdentityError(
                    f"refusing to import '{ident.user_id}': fingerprint "
                    f"changed {old} -> {ident.fingerprint}. Either the key was "
                    f"rotated legitimately or this is a substitution attack. "
                    f"Delete the old identity explicitly to proceed."
                )
        (self.root / ident.user_id).mkdir(parents=True, exist_ok=True)
        (self.root / ident.user_id / "public.json").write_text(
            json.dumps(d, indent=2))
        return ident
