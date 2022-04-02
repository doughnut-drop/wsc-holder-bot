import os
from web3 import Web3


class EthClient:

    def __init__(self):
        self.node_provider = os.environ['NODE_PROVIDER']
        self.web3_connection = Web3(Web3.HTTPProvider(self.node_provider))

    def is_connected(self):
        '''
        connect to the ethereum network
        '''
        return self.web3_connection.isConnected()

    def get_contract_obj(self, contract_address, contract_abi):
        '''
        get the contract object
        '''
        contract_address = Web3.toChecksumAddress(contract_address)
        contract_obj = self.web3_connection.eth.contract(address=contract_address, abi=contract_abi)
        return contract_obj

    def get_wsc_token_count(self, contract_obj, function, wallet_address):
        wallet_address = Web3.toChecksumAddress(wallet_address)
        token_count = contract_obj.functions[function](wallet_address).call()
        return token_count
