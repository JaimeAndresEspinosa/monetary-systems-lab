"""Despliega los contratos en una red real (por defecto, la testnet Sepolia).

Necesitas, en variables de entorno (nunca en el código ni en git):
    RPC_URL       p. ej. https://sepolia.infura.io/v3/<tu-clave> o https://rpc.sepolia.org
    PRIVATE_KEY   la clave de una cartera de PRUEBAS con algo de SepoliaETH (de un faucet)

    pip install -r requirements-chain.txt
    set RPC_URL=...            (PowerShell: $env:RPC_URL="...")
    set PRIVATE_KEY=...
    python scripts/deploy_contracts.py

Guarda las direcciones en contracts/deployments.json; la web las enlaza a Etherscan.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from msl import Params  # noqa: E402
from msl.chain import compile_all  # noqa: E402

E18 = 10**18
MONTH = 30 * 24 * 3600


def main():
    rpc, key = os.environ.get("RPC_URL"), os.environ.get("PRIVATE_KEY")
    if not rpc or not key:
        sys.exit("Faltan RPC_URL y/o PRIVATE_KEY (ver la cabecera de este script).")
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(rpc))
    acct = w3.eth.account.from_key(key)
    chain_id = w3.eth.chain_id
    if chain_id == 1:
        sys.exit("Esto es Ethereum mainnet: el laboratorio solo se despliega en testnets.")
    print(f"red {chain_id} · cuenta {acct.address} · saldo {w3.from_wei(w3.eth.get_balance(acct.address), 'ether')} ETH")
    arts = compile_all()
    p = Params()

    def deploy(name, *args):
        C = w3.eth.contract(abi=arts[name]["abi"], bytecode=arts[name]["bin"])
        tx = C.constructor(*args).build_transaction({
            "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "chainId": chain_id})
        signed = acct.sign_transaction(tx)
        h = w3.eth.send_raw_transaction(signed.raw_transaction)
        r = w3.eth.wait_for_transaction_receipt(h, timeout=300)
        print(f"  {name:20s} {r.contractAddress}  (gas {r.gasUsed:,})")
        return r.contractAddress

    genesis = 1_000_000 * E18
    out = {"chain_id": chain_id, "deployer": acct.address, "date": time.strftime("%Y-%m-%d"), "contracts": {
        "HalvingToken": deploy("HalvingToken", 21_000_000 * E18,
                               genesis * int(p.fixed_initial_issuance * 1e6) // (12 * 10**6),
                               p.halving_months, MONTH, genesis),
        "AlgorithmicDividend": deploy("AlgorithmicDividend",
                                      int(round((p.inflation_target + p.productivity_growth) * 10_000)),
                                      MONTH, acct.address, genesis),
        "DemurrageToken": deploy("DemurrageToken", int(p.demurrage_rate * E18), MONTH, 1_000 * E18, acct.address),
        "ProgrammableCBDC": deploy("ProgrammableCBDC", int(p.cbdc_limit) * E18),
        "HouseRegistry": deploy("HouseRegistry"),
        "LabStable": deploy("LabStable"),
    }}
    path = ROOT / "contracts" / "deployments.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"-> {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
