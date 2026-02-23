import os
import json
from web3 import Web3

# 1. Path discovery (Safe for Render)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ABI_PATH = os.path.join(BASE_DIR, 'contract_abi.json')

def record_on_chain(task_id, status):
    """
    Defensive function to record events. 
    If anything is missing, it logs a warning but DOES NOT crash the app.
    """
    try:
        # 1. Get Environment Variables
        rpc_url = "https://sepolia.base.org"
        contract_address = os.getenv('CONTRACT_ADDRESS')
        account_address = os.getenv('LEDGER_ACCOUNT_ADDRESS')
        raw_key = os.getenv('LEDGER_PRIVATE_KEY')

        if not all([contract_address, account_address, raw_key]):
            print("🔗 Ledger: Skipping (Env Vars missing)")
            return None

        # 2. Fix Private Key Prefix
        private_key = raw_key if raw_key.startswith('0x') else '0x' + raw_key

        # 3. Load ABI safely
        if not os.path.exists(ABI_PATH):
            print(f"🔗 Ledger: Skipping (ABI file not found at {ABI_PATH})")
            return None
            
        with open(ABI_PATH, 'r') as f:
            abi = json.load(f)

        # 4. Connect and Transact
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        contract = w3.eth.contract(address=contract_address, abi=abi)
        nonce = w3.eth.get_transaction_count(account_address)
        
        tx = contract.functions.recordTask(str(task_id), str(status)).build_transaction({
            'from': account_address,
            'nonce': nonce,
            'gas': 250000,
            'gasPrice': w3.eth.gas_price,
            'chainId': 84532
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        print(f"🔗 Ledger SUCCESS: {w3.to_hex(tx_hash)}")
        return w3.to_hex(tx_hash)

    except Exception as e:
        # We capture ALL errors so the main Flask app NEVER crashes
        print(f"🔗 Ledger Error: {e}")
        return None