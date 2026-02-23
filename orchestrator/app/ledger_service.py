import os
import json
from web3 import Web3

# 🚀 ABSOLUTE PATH LOGIC
# This finds the directory where THIS file (ledger_service.py) is located.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# This creates the full path to the ABI file in the same folder.
ABI_PATH = os.path.join(BASE_DIR, 'contract_abi.json')

# 1. Setup Connection (Base Sepolia RPC)
RPC_URL = "https://sepolia.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# 2. Load the ABI with a safety check
CONTRACT_ABI = []
if os.path.exists(ABI_PATH):
    try:
        with open(ABI_PATH, 'r') as f:
            CONTRACT_ABI = json.load(f)
    except Exception as e:
        print(f"⚠️ Error reading ABI file: {e}")
else:
    print(f"⚠️ CRITICAL: contract_abi.json NOT FOUND at {ABI_PATH}")

def record_on_chain(task_id, status):
    """
    Records a task event on the Base Sepolia blockchain.
    """
    # 3. Get Credentials from Environment Variables
    raw_key = os.getenv('LEDGER_PRIVATE_KEY')
    ACCOUNT_ADDRESS = os.getenv('LEDGER_ACCOUNT_ADDRESS')
    CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS')

    # Basic configuration check
    if not raw_key or not ACCOUNT_ADDRESS or not CONTRACT_ADDRESS:
        print("Blockchain skipped: LEDGER env variables are missing.")
        return None

    # 4. Format Private Key (Ensure 0x prefix)
    PRIVATE_KEY = raw_key if raw_key.startswith('0x') else '0x' + raw_key

    try:
        # Initialize Contract
        contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)
        
        # Get Nonce (transaction count for the account)
        nonce = w3.eth.get_transaction_count(ACCOUNT_ADDRESS)
        
        # 5. Build the Transaction
        # Calls the 'recordTask' function from your Solidity contract
        tx = contract.functions.recordTask(
            str(task_id), 
            str(status)
        ).build_transaction({
            'from': ACCOUNT_ADDRESS,
            'nonce': nonce,
            'gas': 200000, # Sufficient limit for simple string storage
            'gasPrice': w3.eth.gas_price,
            'chainId': 84532 # Base Sepolia Chain ID
        })

        # 6. Sign and Send
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        print(f"🔗 Blockchain Audit Logged! Hash: {w3.to_hex(tx_hash)}")
        return w3.to_hex(tx_hash)

    except Exception as e:
        # We catch the error so a blockchain failure doesn't crash the main app
        print(f"⚠️ Blockchain Ledger Sync Failed: {e}")
        return None