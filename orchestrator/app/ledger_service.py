import os
import json
from web3 import Web3

# Path discovery for the ABI sibling file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ABI_PATH = os.path.join(BASE_DIR, 'contract_abi.json')

# 1. Setup Connection
RPC_URL = "https://sepolia.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# 2. Load ABI safely
CONTRACT_ABI = []
if os.path.exists(ABI_PATH):
    with open(ABI_PATH, 'r') as f:
        CONTRACT_ABI = json.load(f)
else:
    print(f"⚠️ Ledger Warning: ABI not found at {ABI_PATH}")

def record_on_chain(task_id, status):
    # Retrieve env vars
    raw_key = os.getenv('LEDGER_PRIVATE_KEY')
    ACCOUNT_ADDRESS = os.getenv('LEDGER_ACCOUNT_ADDRESS')
    CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS')

    if not all([raw_key, ACCOUNT_ADDRESS, CONTRACT_ADDRESS]):
        print("🔗 Ledger: Skipping (Missing Env Vars)")
        return None

    # Fix key prefix if necessary
    PRIVATE_KEY = raw_key if raw_key.startswith('0x') else '0x' + raw_key

    try:
        contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
        nonce = w3.eth.get_transaction_count(ACCOUNT_ADDRESS)
        
        tx = contract.functions.recordTask(str(task_id), str(status)).build_transaction({
            'from': ACCOUNT_ADDRESS,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': w3.eth.gas_price,
            'chainId': 84532
        })

        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        print(f"🔗 Ledger Success! Tx: {w3.to_hex(tx_hash)}")
        return w3.to_hex(tx_hash)
    except Exception as e:
        print(f"🔗 Ledger Fail: {e}")
        return None