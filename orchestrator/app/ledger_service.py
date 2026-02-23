import os
from web3 import Web3
import json

# 1. Setup Connection (Using a public Base Sepolia RPC)
RPC_URL = "https://sepolia.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# 2. Contract Details
CONTRACT_ADDRESS = os.getenv('CONTRACT_ADDRESS') 
# Load the ABI from the file you saved earlier
with open('contract_abi.json', 'r') as f:
    CONTRACT_ABI = json.load(f)

contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

# 3. Your Wallet Details (From MetaMask)
# SAVE THESE IN RENDER ENV VARS!
PRIVATE_KEY = os.getenv('LEDGER_PRIVATE_KEY') 
ACCOUNT_ADDRESS = os.getenv('LEDGER_ACCOUNT_ADDRESS') 

def record_on_chain(task_id, status):
    try:
        if not PRIVATE_KEY:
            print("Blockchain skipped: No Private Key")
            return None

        # Build Transaction
        nonce = w3.eth.get_transaction_count(ACCOUNT_ADDRESS)
        
        # Call the 'recordTask' function from your Solidity code
        tx = contract.functions.recordTask(
            str(task_id), 
            str(status)
        ).build_transaction({
            'from': ACCOUNT_ADDRESS,
            'nonce': nonce,
            'gas': 100000, # Base is cheap, this is plenty
            'gasPrice': w3.eth.gas_price
        })

        # Sign and Send
        signed_tx = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        
        print(f"🔗 Blockchain Audit Logged: {w3.to_hex(tx_hash)}")
        return w3.to_hex(tx_hash)
    except Exception as e:
        print(f"⚠️ Blockchain Logging Failed: {e}")
        return None