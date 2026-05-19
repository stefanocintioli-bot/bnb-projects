"""
dca-bnbagent/config.py — per-network constants for the DCA agent.

Every network-dependent address lives here so that flipping NETWORK
from bsc-testnet to bsc-mainnet requires zero changes in dca_runner.py.
"""

from __future__ import annotations


TESTNET_CONFIG = {
    "network":              "bsc-testnet",
    "chain_id":             97,
    "pancake_router":       "0xD99D1c33F9fC3444f8101754aBC46c52416550D1",
    "pancake_factory":      "0x6725F303b657a9451d8BA641348b6761A6CC7a17",
    "wbnb":                 "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd",
    "default_target_token": "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd",  # USDT testnet
    "identity_registry":    "0x8004A818BFB912233c491871b3d84c89A494BD9e",  # ERC-8004 singleton
    "bscscan_base":         "https://testnet.bscscan.com",
}

MAINNET_CONFIG = {
    "network":              "bsc-mainnet",
    "chain_id":             56,
    "pancake_router":       "0x10ED43C718714eb63d5aA57B78B54704E256024E",
    "pancake_factory":      "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73",
    "wbnb":                 "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    "default_target_token": "0x55d398326f99059fF775485246999027B3197955",  # USDT mainnet
    # BAP-692 specifies ERC-8004 as per-chain singletons via the same
    # vanity address as testnet. Mainnet deployment is pending — the
    # SDK README states "BSC Mainnet — Coming Soon" for the registry.
    "identity_registry":    "0x8004A818BFB912233c491871b3d84c89A494BD9e",
    "bscscan_base":         "https://bscscan.com",
}

_CONFIGS = {
    "bsc-testnet": TESTNET_CONFIG,
    "bsc-mainnet": MAINNET_CONFIG,
}


def get_config(network: str) -> dict:
    """Return the address book for ``network``. Raise on unknown name."""
    if network not in _CONFIGS:
        raise ValueError(
            f"Unknown network {network!r}. Valid: {sorted(_CONFIGS)}"
        )
    return _CONFIGS[network]
