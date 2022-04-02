import os
from dotenv import load_dotenv

import ethscan_api
import web3_functions
import settings
import discord


class DiscordClient(discord.Client):

    async def on_ready(self):
        self.eth_client = web3_functions.EthClient()
        self.ethscan = ethscan_api.EthScan()

        # get sabi (staking) contract object
        self.staking_contract_address = settings.STAKING_CONTRACT_ADDRESS
        self.count_staking_function = settings.COUNT_STAKING_FUNCTION
        self.staking_contract_abi = self.ethscan.get_contract_abi(self.staking_contract_address)
        self.staking_contract_obj = self.eth_client.get_contract_obj(self.staking_contract_address, self.staking_contract_abi)

        # get sabi (minting) contract object
        self.unstaked_contract_address = settings.UNSTAKED_CONTRACT_ADDRESS
        self.count_unstaked_function = settings.COUNT_UNSTAKED_FUNCTION
        self.unstaked_contract_abi = self.ethscan.get_contract_abi(self.unstaked_contract_address)
        self.unstaked_contract_obj = self.eth_client.get_contract_obj(self.unstaked_contract_address, self.unstaked_contract_abi)

        print("We have logged in as:", self.user)

    async def eth_connection(self):
        await self.message.channel.send(self.eth_client.is_connected())

    def get_wsc_token_count(self):
        wallet_address = self.msg.split(" ")[-1]
        staked_list = self.eth_client.get_wsc_token_count(self.staking_contract_obj, self.count_staking_function, wallet_address)  # get staked count from address; returns list(int)
        unstaked_count = self.eth_client.get_wsc_token_count(self.unstaked_contract_obj, self.count_unstaked_function, wallet_address)  # get staked count from address; returns int
        total_wsc_token_owned = len(staked_list) + unstaked_count
        return total_wsc_token_owned

    async def grant_role(self):
        member = self.message.author
        token_count = self.get_wsc_token_count()

        role_id = None
        for holder in settings.HOLDER_ROLES:
            if token_count >= holder["count"]:
                role_id = holder["role_id"]
                # end search when a role is assigned
                if role_id is not None:
                    break
                else:
                    continue
        
        role = discord.utils.get(member.guild.roles, id=role_id)
        default_role = discord.utils.get(member.guild.roles, id=settings.DEFAULT_HOLDER_ROLE)

        await member.add_roles(role, reason="add specific nft holder count role")
        await member.add_roles(default_role, reason="add default nft holder count role")

        # create embed message
        embedMsg = discord.Embed(
                title="Your Sabis have been verified!",
                color=discord.Color.green(),
            )

        embedMsg.add_field(name="total WSC tokens found", value=token_count, inline=False)
        await self.message.channel.send(embed=embedMsg)
        await self.message.channel.send("Holder role has been granted.")

    async def on_message(self, message):

        if message.author == self.user:
            return

        self.message = message
        self.msg = message.content
        if self.msg.startswith("!verify"):
            await self.grant_role()

        elif self.msg.startswith("!connection"):
            await self.eth_connection()


if __name__ == "__main__":
    load_dotenv()
    discord_token = os.environ["DISCORD_TOKEN"]

    bot = DiscordClient()
    bot.run(discord_token)
