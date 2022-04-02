import os
import json
import requests


class EthScan:

    def __init__(self):
        self.ethscan_api = os.environ['ETHSCAN_API']

    def get_contract_abi(self, contract_address):
        url = f"""https://api.etherscan.io/api?module=contract&action=getabi&address={contract_address}&apikey={self.ethscan_api}"""
        res = requests.get(url)
        contract_abi = json.loads(res.json()['result'])
        return contract_abi
