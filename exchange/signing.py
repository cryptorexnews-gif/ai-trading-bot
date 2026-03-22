from typing import Any, Dict, Optional

import msgpack
from Crypto.Hash import keccak
from eth_account.messages import encode_typed_data


def _action_hash(
    action: Dict[str, Any],
    nonce: int,
    expires_after: Optional[int],
) -> bytes:
    data = msgpack.packb(action)
    data += nonce.to_bytes(8, "big")

    # Master-only mode: no vault address, always append marker 0x00
    data += b"\x00"

    if expires_after is not None:
        data += b"\x00"
        data += expires_after.to_bytes(8, "big")
    return keccak.new(data=data, digest_bits=256).digest()


def _l1_payload(phantom_agent: Dict[str, str]) -> Dict[str, Any]:
    return {
        "domain": {
            "chainId": 1337,
            "name": "Exchange",
            "verifyingContract": "0x0000000000000000000000000000000000000000",
            "version": "1",
        },
        "types": {
            "Agent": [
                {"name": "source", "type": "string"},
                {"name": "connectionId", "type": "bytes32"},
            ],
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
        },
        "primaryType": "Agent",
        "message": phantom_agent,
    }


def sign_l1_action_exact(
    account,
    action: Dict[str, Any],
    nonce: int,
    expires_after: Optional[int],
    is_mainnet: bool = True,
) -> Dict[str, Any]:
    hash_bytes = _action_hash(action, nonce, expires_after)
    phantom_agent = {"source": "a" if is_mainnet else "b", "connectionId": "0x" + hash_bytes.hex()}
    data = _l1_payload(phantom_agent)
    structured_data = encode_typed_data(full_message=data)
    signed = account.sign_message(structured_data)
    return {"r": hex(signed.r), "s": hex(signed.s), "v": signed.v}