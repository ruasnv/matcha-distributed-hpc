import os
import threading
import json

# Global variables to cache the connection so we don't reload it every time
_W3 = None
_CONTRACT = None

def record_on_chain(task_id, status):
    """
    Decoupled logger. Spawns a thread so the main app stays fast.
    """
    # 1. THE SAFETY VALVE: Default to false so you don't crash by accident
    if os.getenv('BLOCKCHAIN_ENABLED', 'false').lower() != 'true':
        print(f"🔗 Ledger (SIMULATED): {task_id} -> {status}")
        return

    # 2. RUN IN BACKGROUND: Don't make the user wait for the blockchain
    thread = threading.Thread(target=_heavy_blockchain_call, args=(task_id, status))
    thread.daemon = True # Thread dies if the main app stops
    thread.start()

def _heavy_blockchain_call(task_id, status):
    global _W3, _CONTRACT
    
    try:
        # 🚀 LAZY IMPORTS: Only eats RAM when actually recording
        from web3 import Web3 
        
        # 1. Initialize only once to save resources
        if _W3 is None:
            rpc_url = "https://sepolia.base.org"
            _W3 = Web3(Web3.HTTPProvider(rpc_url))
            
            contract_addr = os.getenv('CONTRACT_ADDRESS')
            base_dir = os.path.dirname(os.path.abspath(__file__))
            abi_path = os.path.join(base_dir, 'contract_abi.json')
            
            if not os.path.exists(abi_path):
                print(f"❌ Ledger Error: ABI file missing at {abi_path}")
                return

            with open(abi_path, 'r') as f:
                abi = json.load(f)
            
            _CONTRACT = _W3.eth.contract(address=contract_addr, abi=abi)

        # 2. Setup Credentials
        account_addr = os.getenv('LEDGER_ACCOUNT_ADDRESS')
        raw_key = os.getenv('LEDGER_PRIVATE_KEY')
        if not account_addr or not raw_key:
            print("❌ Ledger Error: Missing credentials in Env Vars")
            return

        private_key = raw_key if raw_key.startswith('0x') else '0x' + raw_key
        nonce = _W3.eth.get_transaction_count(account_addr)
        
        # 3. Build & Sign Transaction
        tx = _CONTRACT.functions.recordTask(str(task_id), str(status)).build_transaction({
            'from': account_addr,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': _W3.eth.gas_price,
            'chainId': 84532
        })

        signed_tx = _W3.eth.account.sign_transaction(tx, private_key)
        tx_hash = _W3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        print(f"🔗 Ledger SUCCESS! Hash: {_W3.to_hex(tx_hash)}")

    except Exception as e:
        # We catch everything so the background thread dying doesn't kill Flask
        print(f"🔗 Ledger Background Error: {e}")