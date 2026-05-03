from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from ipv8.community import Community, CommunitySettings
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.lazy_payload import VariablePayload
from ipv8.messaging.payload_dataclass import vp_compile
from ipv8.peer import Peer
from ipv8_service import IPv8

from lab1_config import DEFAULT_CONFIG_FILE, load_lab1_config, resolve_config_value
from lab1_pow import MAX_NONCE, PowInput


COMMUNITY_ID_HEX = "2c1cc6e35ff484f99ebdfb6108477783c0102881"
SERVER_PUBLIC_KEY_HEX = (
    "4c69624e61434c504b3a86b23934a28d669c390e2d1fc0b0870706c4591cc0cb"
    "178bc5a811da6d87d27ef319b2638ef60cc8d119724f4c53a1ebfad919c3ac413"
    "6c501ce5c09364e0ebb"
)
DEFAULT_KEY_FILE = "lab1_identity.pem"
DISCOVERY_TIMEOUT_SECONDS = 60.0
DISCOVERY_POLL_INTERVAL_SECONDS = 2.0
RESPONSE_TIMEOUT_SECONDS = 15.0
RANDOM_WALK_TARGET_PEERS = 20
RANDOM_WALK_TIMEOUT_SECONDS = 3.0
DEFAULT_EMAIL = "student123@student.tudelft.nl"
DEFAULT_GITHUB_URL = "https://github.com/example/blockchain-engineering--individual"


def decode_hex(value: str, expected_length: int, field_name: str) -> bytes:
    try:
        data = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be valid hex") from exc

    if len(data) != expected_length:
        raise ValueError(
            f"{field_name} must be exactly {expected_length} bytes, got {len(data)}"
        )
    return data


COMMUNITY_ID = decode_hex(COMMUNITY_ID_HEX, expected_length=20, field_name="community_id")
SERVER_PUBLIC_KEY = decode_hex(
    SERVER_PUBLIC_KEY_HEX,
    expected_length=74,
    field_name="server_public_key",
)


@dataclass(frozen=True)
class ServerInfo:
    address: tuple[str, int]
    public_key_hex: str
    mid_hex: str


@vp_compile
class SubmissionPayload(VariablePayload):
    msg_id = 1
    format_list = ["varlenHutf8", "varlenHutf8", "q"]
    names = ["email", "github_url", "nonce"]


@vp_compile
class ServerResponsePayload(VariablePayload):
    msg_id = 2
    format_list = ["?", "varlenHutf8"]
    names = ["success", "message"]


@dataclass(frozen=True)
class Submission:
    email: str
    github_url: str
    nonce: int

    def validate(self) -> None:
        PowInput(email=self.email, github_url=self.github_url).validate()

        canonical_email = self.email.strip().casefold()
        if not (
            canonical_email.endswith("@tudelft.nl")
            or canonical_email.endswith("@student.tudelft.nl")
        ):
            raise ValueError(
                "email must end in @tudelft.nl or @student.tudelft.nl for server acceptance"
            )

        if not 0 <= self.nonce <= MAX_NONCE:
            raise ValueError("nonce must be a non-negative integer that fits in 63 bits")


@dataclass(frozen=True)
class ServerResponse:
    success: bool
    message: str


class Lab1Community(Community):
    community_id = COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(ServerResponsePayload, self.on_server_response)
        self.response_future: asyncio.Future[ServerResponse] | None = None

    def find_server_peer(self) -> Peer | None:
        for peer in self.get_peers():
            if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY:
                return peer
        return None

    def get_discovered_peers(self) -> list[Peer]:
        return self.get_peers()

    def prepare_response_future(self) -> asyncio.Future[ServerResponse]:
        self.response_future = asyncio.get_running_loop().create_future()
        return self.response_future

    def submit_solution(self, server_peer: Peer, submission: Submission) -> None:
        submission.validate()
        self.ez_send(
            server_peer,
            SubmissionPayload(submission.email, submission.github_url, submission.nonce),
        )

    @lazy_wrapper(ServerResponsePayload)
    def on_server_response(self, peer: Peer, payload: ServerResponsePayload) -> None:
        if peer.public_key.key_to_bin() != SERVER_PUBLIC_KEY:
            print(f"Ignored response from non-server peer: {describe_peer(peer)}")
            return

        print("Received authenticated response from the verified server.")
        if self.response_future is not None and not self.response_future.done():
            self.response_future.set_result(
                ServerResponse(success=payload.success, message=payload.message)
            )


def describe_peer(peer: Peer) -> str:
    return (
        f"address={peer.address} "
        f"mid={peer.mid.hex()} "
        f"public_key={peer.public_key.key_to_bin().hex()}"
    )


def build_config(key_file: Path, listen_port: int) -> dict:
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.set_port(listen_port)
    builder.add_key("lab1", "curve25519", str(key_file))
    builder.add_overlay(
        "Lab1Community",
        "lab1",
        [WalkerDefinition(Strategy.RandomWalk, RANDOM_WALK_TARGET_PEERS, {"timeout": RANDOM_WALK_TIMEOUT_SECONDS})],
        default_bootstrap_defs,
        {},
        [],
    )
    return builder.finalize()


async def discover_server(
    key_file: Path,
    listen_port: int,
    discovery_timeout: float,
    poll_interval: float,
) -> ServerInfo:
    ipv8 = IPv8(build_config(key_file=key_file, listen_port=listen_port), extra_communities={"Lab1Community": Lab1Community})
    await ipv8.start()

    try:
        overlay = ipv8.get_overlay(Lab1Community)
        if overlay is None:
            raise RuntimeError("failed to load Lab1Community overlay")
        if not isinstance(overlay, Lab1Community):
            raise RuntimeError("loaded overlay has unexpected type")

        print(f"Using identity file: {key_file}")
        print(f"Joined community: {COMMUNITY_ID_HEX}")
        print(f"Expecting server public key: {SERVER_PUBLIC_KEY_HEX}")
        print("Starting peer discovery...")

        deadline = asyncio.get_running_loop().time() + discovery_timeout
        seen_peers: set[str] = set()

        while True:
            server_peer = overlay.find_server_peer()
            if server_peer is not None:
                print("Matched server peer by public key.")
                return ServerInfo(
                    address=server_peer.address,
                    public_key_hex=server_peer.public_key.key_to_bin().hex(),
                    mid_hex=server_peer.mid.hex(),
                )

            peers = overlay.get_discovered_peers()
            for peer in peers:
                peer_key_hex = peer.public_key.key_to_bin().hex()
                if peer_key_hex not in seen_peers:
                    seen_peers.add(peer_key_hex)
                    print(f"Discovered non-server peer: {describe_peer(peer)}")

            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    "timed out waiting for the lab server peer; peer discovery may still be working, "
                    "but the server public key was not found"
                )

            if not peers:
                print("No peers discovered yet.")
            else:
                print(f"Discovered {len(peers)} peer(s); server not matched yet.")

            await asyncio.sleep(poll_interval)
    finally:
        await ipv8.stop()


async def submit_to_server(
    key_file: Path,
    listen_port: int,
    discovery_timeout: float,
    poll_interval: float,
    response_timeout: float,
    submission: Submission,
) -> ServerResponse:
    ipv8 = IPv8(
        build_config(key_file=key_file, listen_port=listen_port),
        extra_communities={"Lab1Community": Lab1Community},
    )
    await ipv8.start()

    try:
        overlay = ipv8.get_overlay(Lab1Community)
        if overlay is None:
            raise RuntimeError("failed to load Lab1Community overlay")
        if not isinstance(overlay, Lab1Community):
            raise RuntimeError("loaded overlay has unexpected type")

        print(f"Using identity file: {key_file}")
        print(f"Joined community: {COMMUNITY_ID_HEX}")
        print(f"Expecting server public key: {SERVER_PUBLIC_KEY_HEX}")
        print("Starting peer discovery...")

        deadline = asyncio.get_running_loop().time() + discovery_timeout
        seen_peers: set[str] = set()
        server_peer: Peer | None = None

        while server_peer is None:
            server_peer = overlay.find_server_peer()
            if server_peer is not None:
                break

            peers = overlay.get_discovered_peers()
            for peer in peers:
                peer_key_hex = peer.public_key.key_to_bin().hex()
                if peer_key_hex not in seen_peers:
                    seen_peers.add(peer_key_hex)
                    print(f"Discovered non-server peer: {describe_peer(peer)}")

            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    "timed out waiting for the lab server peer; peer discovery may still be working, "
                    "but the server public key was not found"
                )

            if not peers:
                print("No peers discovered yet.")
            else:
                print(f"Discovered {len(peers)} peer(s); server not matched yet.")

            await asyncio.sleep(poll_interval)

        print("Matched server peer by public key.")
        print(f"Server address: {server_peer.address}")
        print(f"Server MID: {server_peer.mid.hex()}")
        print(f"Server public key: {server_peer.public_key.key_to_bin().hex()}")

        response_future = overlay.prepare_response_future()
        overlay.submit_solution(server_peer, submission)
        print("Submission sent with IPv8 authenticated messaging.")
        return await asyncio.wait_for(response_future, timeout=response_timeout)
    finally:
        await ipv8.stop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Join the Lab 1 IPv8 community and discover the server peer."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_FILE,
        help="JSON config file to read defaults from.",
    )
    parser.add_argument(
        "--key-file",
        default=None,
        help="Curve25519 private key file to load or create.",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=8090,
        help="UDP port for the local IPv8 endpoint.",
    )
    parser.add_argument(
        "--discovery-timeout",
        type=float,
        default=DISCOVERY_TIMEOUT_SECONDS,
        help="How long to wait for the server peer before failing.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DISCOVERY_POLL_INTERVAL_SECONDS,
        help="How often to check and report discovery progress.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit a mined solution and wait for the server response.",
    )
    parser.add_argument(
        "--email",
        default=None,
        help="Exact email bytes to submit when using --submit.",
    )
    parser.add_argument(
        "--github-url",
        default=None,
        help="Exact GitHub URL bytes to submit when using --submit.",
    )
    parser.add_argument(
        "--nonce",
        type=int,
        default=None,
        help="Nonce to submit when using --submit.",
    )
    parser.add_argument(
        "--response-timeout",
        type=float,
        default=RESPONSE_TIMEOUT_SECONDS,
        help="How long to wait for the server response after sending a submission.",
    )
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    config = load_lab1_config(args.config)
    key_file = Path(str(resolve_config_value(args.key_file, config.key_file, DEFAULT_KEY_FILE)))
    email = str(resolve_config_value(args.email, config.email, DEFAULT_EMAIL))
    github_url = str(resolve_config_value(args.github_url, config.github_url, DEFAULT_GITHUB_URL))
    nonce = int(resolve_config_value(args.nonce, config.nonce, 0))

    if args.listen_port <= 0 or args.listen_port > 65535:
        raise ValueError("listen_port must be between 1 and 65535")
    if args.discovery_timeout <= 0:
        raise ValueError("discovery_timeout must be positive")
    if args.poll_interval <= 0:
        raise ValueError("poll_interval must be positive")
    if args.response_timeout <= 0:
        raise ValueError("response_timeout must be positive")

    if args.submit:
        response = await submit_to_server(
            key_file=key_file,
            listen_port=args.listen_port,
            discovery_timeout=args.discovery_timeout,
            poll_interval=args.poll_interval,
            response_timeout=args.response_timeout,
            submission=Submission(
                email=email,
                github_url=github_url,
                nonce=nonce,
            ),
        )
        print(f"Server response success: {response.success}")
        print(f"Server response message: {response.message}")
        return

    server = await discover_server(
        key_file=key_file,
        listen_port=args.listen_port,
        discovery_timeout=args.discovery_timeout,
        poll_interval=args.poll_interval,
    )
    print(f"Server address: {server.address}")
    print(f"Server MID: {server.mid_hex}")
    print(f"Server public key: {server.public_key_hex}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
