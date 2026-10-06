#!/usr/bin/env python3
"""Mirror a model directory, decrypting any file whose content starts with ".prot".

Usage: decrypt_models.py <src_dir> <dst_dir> [--decryptor path/to/spice-crypt]

Example: python3 hacking/decrypt_models.py \
  ../pdk/ICsprout_55LLULP1225_1P6M_5Ic_1T4Mc_RDL1_v1p11/model/hspice \
  icsprout55/libs.tech/ngspice
"""
import argparse
import os
import shutil
import subprocess
import sys

PROT_MARKER = b".prot"
DEFAULT_DECRYPTOR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "venv", "bin", "spice-crypt")


def is_protected(path: str) -> bool:
    """Returns True if the file content (ignoring leading whitespace) starts with .prot."""
    with open(path, "rb") as f:
        head = f.read(4096).lstrip()
    return head[:len(PROT_MARKER)].lower() == PROT_MARKER


def decrypt_file(decryptor: str, src: str, dst: str):
    with open(dst, "wb") as out:
        subprocess.run([decryptor, src], stdout=out, check=True)


def process_tree(src_dir: str, dst_dir: str, decryptor: str):
    n_copied = n_decrypted = n_failed = 0

    for root, _, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        out_root = os.path.join(dst_dir, rel)
        os.makedirs(out_root, exist_ok=True)

        for name in files:
            src = os.path.join(root, name)
            dst = os.path.join(out_root, name)

            if is_protected(src):
                try:
                    decrypt_file(decryptor, src, dst)
                    n_decrypted += 1
                    print(f"[DECRYPT] {src} -> {dst}")
                except (subprocess.CalledProcessError, OSError) as e:
                    n_failed += 1
                    print(f"[FAILED]  {src}: {e}", file=sys.stderr)
            else:
                shutil.copy2(src, dst)
                n_copied += 1
                print(f"[COPY]    {src} -> {dst}")

    print(f"\nDone: {n_copied} copied, {n_decrypted} decrypted, {n_failed} failed")
    return n_failed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src_dir", help="Directory to scan recursively")
    parser.add_argument("dst_dir", help="Output directory (structure is preserved)")
    parser.add_argument("--decryptor", default=os.path.normpath(DEFAULT_DECRYPTOR),
                        help="Decryptor command (default: ics55/venv/bin/spice-crypt)")
    args = parser.parse_args()

    if not os.path.isdir(args.src_dir):
        sys.exit(f"Source directory not found: {args.src_dir}")
    if shutil.which(args.decryptor) is None:
        sys.exit(f"Decryptor not found in PATH: {args.decryptor}")

    sys.exit(1 if process_tree(args.src_dir, args.dst_dir, args.decryptor) else 0)


if __name__ == "__main__":
    main()
