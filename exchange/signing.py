from typing import Any, Dict, Optional

import msgpack
from Crypto.Hash import keccak
from eth_account.messages import encode_typed_data


def _address_to_bytes(address: str) -> bytes:
    return bytes.fromhex(address[2:].lower())


def _action_hash(
    action: Dict[str, Any],
    vault_address: Optional[str],
    nonce: int,
    expires_after: Optional[int],
) -> bytes:
    data = msgpack.packb(action)
    data += nonce.to_bytes(8, "big")
    if vault_address is None:
        data += b"\x00"
    else:
        data += b"\x01"
        data += _address_to_bytes(vault_address)
    if expires_after is not None:
        # Keep compatibility with existing project behavior.
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


def _sign_internal(
    account,
    action: Dict[str, Any],
    vault_address: Optional[str],
    nonce: int,
    expires_after: Optional[int],
    is_mainnet: bool,
):
    hash_bytes = _action_hash(action, vault_address, nonce, expires_after)
    phantom_agent = {"source": "a" if is_mainnet else "b", "connectionId": "0x" + hash_bytes.hex()}
    data = _l1_payload(phantom_agent)
    structured_data = encode_typed_data(full_message=data)
    return account.sign_message(structured_data)


def sign_l1_action_exact(
    account,
    action: Dict[str, Any],
    vault_address: Optional[str],
    nonce: int,
    expires_after: Optional[int],
    is_mainnet: bool = True,
) -> Dict[str, Any]:
    signed = _sign_internal(
        account=account,
        action=action,
        vault_address=vault_address,
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
    vault_address: Optional[str],
    nonce: int,
    expires_after: Optional[int],
    is_mainnet: bool = True,
) -> Dict[str, Any]:
    signed = _sign_internal(
        account=account,
        action=action,
        vault_address=vault_address,
        nonce=nonce,
        expires_after=expires_after,
        is_mainnet=is_mainnet,
    )
    return {
        "r": hex(signed.r),
        "s": hex(signed.s),
        "v": signed.v,
    }