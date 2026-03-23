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
    data += b"\x00"
    if expires_after is not None:
        data += b"\x00"
        data += int(expires_after).to_bytes(8, "big")
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


def _parse_nonce_and_expires(args, kwargs) -> tuple:
    if "nonce" in kwargs:
        nonce = int(kwargs["nonce"])
        expires_after = kwargs.get("expires_after")
        return nonce, expires_after

    if len(args) >= 2 and isinstance(args[0], (str, type(None))):
        nonce = int(args[1])
        expires_after = args[2] if len(args) > 2 else kwargs.get("expires_after")
        return nonce, expires_after

    if len(args) >= 1:
        nonce = int(args[0])
        expires_after = args[1] if len(args) > 1 else kwargs.get("expires_after")
        return nonce, expires_after

    raise ValueError("nonce mancante per firma EIP-712")


def _sign_internal(
    account,
    action: Dict[str, Any],
    nonce: int,
    expires_after: Optional[int],
    is_mainnet: bool,
):
    hash_bytes = _action_hash(action, nonce, expires_after)
    phantom_agent = {"source": "a" if is_mainnet else "b", "connectionId": "0x" + hash_bytes.hex()}
    data = _l1_payload(phantom_agent)
    structured_data = encode_typed_data(full_message=data)
    return account.sign_message(structured_data)


def sign_l1_action_exact(
    account,
    action: Dict[str, Any],
    *args,
    is_mainnet: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    nonce, expires_after = _parse_nonce_and_expires(args, kwargs)
    signed = _sign_internal(
        account=account,
        action=action,
        nonce=nonce,
        expires_after=expires_after,
        is_mainnet=is_mainnet,
    )
    return {
        "r": f"0x{signed.r:064x}",
        "s": f"0x{signed.s:064x}",
        "v": signed.v,
    }


def sign_l1_action_exact_legacy(
    account,
    action: Dict[str, Any],
    *args,
    is_mainnet: bool = True,
    **kwargs,
) -> Dict[str, Any]:
    nonce, expires_after = _parse_nonce_and_expires(args, kwargs)
    signed = _sign_internal(
        account=account,
        action=action,
        nonce=nonce,
        expires_after=expires_after,
        is_mainnet=is_mainnet,
    )
    return {
        "r": hex(signed.r),
        "s": hex(signed.s),
        "v": signed.v,
    }