import os

# Base load address specified in your offset notes
BASE_ADDR = 0x100000

# Key location and size
KEY_OFFSET = 0x2389d0 - BASE_ADDR
KEY_SIZE = 0x10

# Ciphertext targets: (Name, absolute offset, size)
TARGETS = [
    ("kItfTyp", 0x2376e0, 0x11cf, 0x54),
    ("kCaptabTyp", 0x230540, 0x7190, 0x41),
    ("kItfRcbest", 0x22f2e0, 0x1261, 0x54),
    ("kCaptabRcbest", 0x228140, 0x7190, 0x41),
    ("kItfRcworst", 0x226ec0, 0x1266, 0x54),
    ("kCaptabRcworst", 0x21fd20, 0x7190, 0x41),
    ("kItfRcbest_21eac0", 0x21eac0, 0x1257, 0x54),
    ("kCaptabCbest", 0x217920, 0x7190, 0x41),
    ("kItfCworst", 0x2166c0, 0x124d, 0x54),
    ("kCaptabCworst", 0x20f520, 0x7190, 0x41),
    ("kMapping", 0x2388c0, 0x108, 99),
]


def xor_decrypt(data: bytes, key: bytes) -> bytes:
    """Applies repeating XOR decryption to data using key."""
    return bytes([b ^ key[i % len(key)] for i, b in enumerate(data)])


def process_binary(file_path: str, output_dir: str = "decrypted_output"):
    os.makedirs(output_dir, exist_ok=True)

    with open(file_path, "rb") as f:
        # Fetch the key
        f.seek(KEY_OFFSET)
        key = f.read(KEY_SIZE)

        if len(key) < KEY_SIZE:
            raise ValueError(
                f"Could not read full key from offset {hex(KEY_OFFSET)}"
            )

        print(f"[*] Extracted Key ({len(key)} bytes): {key.hex()}")

        # Process each ciphertext section
        for name, abs_offset, size_p1, start in TARGETS:
            size = size_p1 - 1
            file_offset = abs_offset - BASE_ADDR

            f.seek(file_offset)
            ciphertext = f.read(size)

            if len(ciphertext) < size:
                print(
                    f"[!] Warning: Expected {hex(size)} bytes for {name}, but read {len(ciphertext)} bytes."
                )

            plaintext = xor_decrypt(ciphertext, key)

            out_path = os.path.join(output_dir, f"{name}.txt")
            with open(out_path, "wb") as out_file:
                out_file.write(plaintext)

            print(
                f"[+] Decrypted {name} -> {out_path} ({len(plaintext)} bytes)"
            )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <path_to_so_file>")
        sys.exit(1)

    process_binary(sys.argv[1])
