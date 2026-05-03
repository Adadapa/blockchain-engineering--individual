from __future__ import annotations

import argparse
import hashlib
import time
from dataclasses import dataclass

from lab1_config import DEFAULT_CONFIG_FILE, load_lab1_config, resolve_config_value


DIFFICULTY_BITS = 28
MAX_NONCE = (1 << 63) - 1
PROGRESS_INTERVAL = 1_000_000
DEFAULT_EMAIL = "student123@student.tudelft.nl"
DEFAULT_GITHUB_URL = "https://github.com/example/blockchain-engineering--individual"


@dataclass(frozen=True)
class PowInput:
    email: str
    github_url: str

    def validate(self) -> None:
        if not self.email:
            raise ValueError("email must be non-empty")
        if "\n" in self.email:
            raise ValueError("email must not contain newlines")
        if len(self.email.encode("utf-8")) > 254:
            raise ValueError("email must be <= 254 UTF-8 bytes")

        if not self.github_url:
            raise ValueError("github_url must be non-empty")
        if "\n" in self.github_url:
            raise ValueError("github_url must not contain newlines")
        if len(self.github_url.encode("utf-8")) > 512:
            raise ValueError("github_url must be <= 512 UTF-8 bytes")
        if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in self.github_url):
            raise ValueError("github_url must not contain whitespace or control characters")

    def prefix_bytes(self) -> bytes:
        self.validate()
        return self.email.encode("utf-8") + b"\n" + self.github_url.encode("utf-8") + b"\n"


def nonce_to_bytes(nonce: int) -> bytes:
    if not 0 <= nonce <= MAX_NONCE:
        raise ValueError("nonce must be between 0 and 2^63 - 1")
    return nonce.to_bytes(8, byteorder="big", signed=False)


def hash_pow_input(pow_input: PowInput, nonce: int) -> bytes:
    return hashlib.sha256(pow_input.prefix_bytes() + nonce_to_bytes(nonce)).digest()


def count_leading_zero_bits(digest: bytes) -> int:
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        return bits + (8 - byte.bit_length())
    return bits


def is_valid_pow(digest: bytes, difficulty_bits: int = DIFFICULTY_BITS) -> bool:
    if difficulty_bits < 0:
        raise ValueError("difficulty_bits must be non-negative")
    return count_leading_zero_bits(digest) >= difficulty_bits


def mine_pow(
    pow_input: PowInput,
    difficulty_bits: int = DIFFICULTY_BITS,
    start_nonce: int = 0,
    max_tries: int | None = None,
) -> tuple[int, bytes]:
    if start_nonce < 0:
        raise ValueError("start_nonce must be non-negative")
    if max_tries is not None and max_tries <= 0:
        raise ValueError("max_tries must be positive when provided")

    prefix = pow_input.prefix_bytes()
    tries = 0
    nonce = start_nonce

    while nonce <= MAX_NONCE:
        digest = hashlib.sha256(prefix + nonce_to_bytes(nonce)).digest()
        if is_valid_pow(digest, difficulty_bits):
            return nonce, digest

        nonce += 1
        tries += 1
        if max_tries is not None and tries >= max_tries:
            break

    raise RuntimeError("no valid nonce found in the searched range")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mine the Lab 1 IPv8 proof of work for a TU Delft email and GitHub URL."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_FILE,
        help="JSON config file to read defaults from.",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Exact email bytes to hash and later submit.",
    )
    parser.add_argument(
        "--github-url",
        default=None,
        help="Exact GitHub repo URL bytes to hash and later submit.",
    )
    parser.add_argument(
        "--difficulty",
        type=int,
        default=DIFFICULTY_BITS,
        help="Number of leading zero bits required.",
    )
    parser.add_argument(
        "--start-nonce",
        type=int,
        default=0,
        help="Nonce to start searching from.",
    )
    parser.add_argument(
        "--max-tries",
        type=int,
        default=None,
        help="Optional cap on the number of nonces to test.",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=PROGRESS_INTERVAL,
        help="How often to print mining progress in tested nonces.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_lab1_config(args.config)
    email = resolve_config_value(args.email, config.email, DEFAULT_EMAIL)
    github_url = resolve_config_value(args.github_url, config.github_url, DEFAULT_GITHUB_URL)
    pow_input = PowInput(email=str(email), github_url=str(github_url))
    prefix = pow_input.prefix_bytes()

    print(f"Email: {pow_input.email}")
    print(f"GitHub URL: {pow_input.github_url}")
    print(f"Difficulty: {args.difficulty} leading zero bits")
    print(f"Hash prefix bytes length: {len(prefix)}")
    print("Mining started...")

    start_time = time.perf_counter()
    nonce = args.start_nonce
    tries = 0

    while nonce <= MAX_NONCE:
        digest = hashlib.sha256(prefix + nonce_to_bytes(nonce)).digest()
        if is_valid_pow(digest, args.difficulty):
            elapsed = time.perf_counter() - start_time
            print(f"Nonce: {nonce}")
            print(f"Digest: {digest.hex()}")
            print(f"Leading zero bits: {count_leading_zero_bits(digest)}")
            print(f"Elapsed seconds: {elapsed:.2f}")
            return

        nonce += 1
        tries += 1

        if args.max_tries is not None and tries >= args.max_tries:
            raise RuntimeError("reached max_tries without finding a valid nonce")

        if args.progress_interval > 0 and tries % args.progress_interval == 0:
            elapsed = time.perf_counter() - start_time
            rate = tries / elapsed if elapsed else 0.0
            print(
                f"Tried {tries} nonces, current nonce {nonce}, "
                f"rate {rate:,.0f} hashes/sec"
            )

    raise RuntimeError("exhausted all valid nonces without finding a solution")


if __name__ == "__main__":
    main()
