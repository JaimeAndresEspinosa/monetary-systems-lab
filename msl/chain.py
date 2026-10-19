"""Compilación y despliegue de los contratos de `contracts/` en una cadena Ethereum.

Por defecto usa una cadena local en memoria (eth-tester + py-evm), que permite
viajar en el tiempo para simular años de política monetaria en segundos. Con
`connect(rpc_url)` se usa una red real (p. ej. la testnet Sepolia).

Dependencias opcionales (requirements-chain.txt): py-solc-x, web3, eth-tester, py-evm.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
BUILD = CONTRACTS / "build"
SOLC = "0.8.24"


def compile_all(force: bool = False) -> dict[str, dict]:
    """Compila todos los .sol y guarda ABI + bytecode en contracts/build/."""
    BUILD.mkdir(exist_ok=True)
    cache = BUILD / "artifacts.json"
    sources = sorted(CONTRACTS.glob("*.sol"))
    newest = max(f.stat().st_mtime for f in sources)
    if cache.exists() and not force and cache.stat().st_mtime >= newest:
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except ImportError:
        pass
    import solcx
    if SOLC not in [str(v) for v in solcx.get_installed_solc_versions()]:
        solcx.install_solc(SOLC)
    out = solcx.compile_files(
        [str(f) for f in sources], output_values=["abi", "bin"], solc_version=SOLC,
        base_path=str(CONTRACTS), allow_paths=[str(CONTRACTS)], optimize=True, optimize_runs=200,
    )
    artifacts = {}
    for key, val in out.items():
        name = key.split(":")[-1]
        if val["bin"]:  # descarta interfaces, librerías y contratos abstractos
            artifacts[name] = {"abi": val["abi"], "bin": val["bin"]}
    cache.write_text(json.dumps(artifacts), encoding="utf-8")
    return artifacts


class Chain:
    """Cadena local con utilidades para desplegar, llamar y avanzar el reloj."""

    def __init__(self, w3=None):
        from web3 import Web3, EthereumTesterProvider
        if w3 is None:
            self.provider = EthereumTesterProvider()
            w3 = Web3(self.provider)
        self.w3 = w3
        self.accounts = w3.eth.accounts
        self.artifacts = compile_all()

    def deploy(self, name: str, *args, sender=None):
        art = self.artifacts[name]
        C = self.w3.eth.contract(abi=art["abi"], bytecode=art["bin"])
        tx = C.constructor(*args).transact({"from": sender or self.accounts[0]})
        receipt = self.w3.eth.wait_for_transaction_receipt(tx)
        return self.w3.eth.contract(address=receipt.contractAddress, abi=art["abi"])

    def tx(self, fn, sender=None):
        h = fn.transact({"from": sender or self.accounts[0]})
        return self.w3.eth.wait_for_transaction_receipt(h)

    def now(self) -> int:
        return self.w3.eth.get_block("latest")["timestamp"]

    def advance(self, seconds: int):
        tester = self.provider.ethereum_tester
        tester.time_travel(self.now() + int(seconds))
        tester.mine_blocks(1)
