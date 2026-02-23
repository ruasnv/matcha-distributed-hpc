import os
import json

# Global variables to store the objects only when needed
_W3 = None
_CONTRACT = None

def record_on_chain(task_id, status):
    global _W3, _CONTRACT
    
    try:
        # 1. Fetch Env Vars
        contract_addr = os.getenv('CONTRACT_ADDRESS')
        account_addr = os.getenv('LEDGER_ACCOUNT_ADDRESS')
        raw_key = os.getenv('LEDGER_PRIVATE_KEY')

        if not all([contract_addr, account_addr, raw_key]):
            return None

        # 2. Only initialize Web3 and Contract on the FIRST call
        if _W3 is None:
            from web3 import Web3 # Import here to save RAM at boot
            _W3 = Web3(Web3.HTTPProvider("https://sepolia.base.org"))
            
            base_dir = os.path.dirname(os.path.abspath(__file__))
            abi_path = os.path.join(base_dir, 'contract_abi.json')
            
            with open(abi_path, 'r') as f:
                abi = json.load(f)
            
            _CONTRACT = _W3.eth.contract(address=contract_addr, abi=abi)

        # 3. Format key and send
        private_key = raw_key if raw_key.startswith('0x') else '0x' + raw_key
        nonce = _W3.eth.get_transaction_count(account_addr)
        
        tx = _CONTRACT.functions.recordTask(str(task_id), str(status)).build_transaction({
            'from': account_addr,
            'nonce': nonce,
            'gas': 200000,
            'gasPrice': _W3.eth.gas_price,
            'chainId': 84532
        })

        signed_tx = _W3.eth.account.sign_transaction(tx, private_key)
        tx_hash = _W3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        print(f"🔗 Ledger SUCCESS: {_W3.to_hex(tx_hash)}")
        return _W3.to_hex(tx_hash)

    except Exception as e:
        print(f"🔗 Ledger Error: {e}")
        return None