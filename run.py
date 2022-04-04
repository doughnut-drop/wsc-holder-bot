import os
from dotenv import load_dotenv
from datetime import datetime

import ethscan_api
import web3_functions
import settings
import discord


class DiscordClient(discord.Client):

    async def on_ready(self):
        self.eth_client = web3_functions.EthClient()
        self.ethscan = ethscan_api.EthScan()
        self.date_format = "%Y-%m-%d"
        self.current_date = datetime.strptime("2022-04-03", self.date_format)

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

    def get_wsc_token_count(self, wallet_address):
        staked_list = self.eth_client.get_wsc_token_count(self.staking_contract_obj, self.count_staking_function, wallet_address)  # get staked count from address; returns list(int)
        unstaked_count = self.eth_client.get_wsc_token_count(self.unstaked_contract_obj, self.count_unstaked_function, wallet_address)  # get staked count from address; returns int
        total_wsc_token_owned = len(staked_list) + unstaked_count
        return total_wsc_token_owned

    def confirm_signed_message(self, member, signature):
        wallet_address = self.eth_client.get_address_of_signed_msg(member, signature)
        return wallet_address

    async def grant_role(self):
        wallet_address = self.msg.split(" ")[-2]
        signature = self.msg.split(" ")[-1]
        member = self.message.author

        try:
            confirmed_wallet_address = self.confirm_signed_message(str(member), signature)
        except:
            confirmed_wallet_address = None
        
        if wallet_address == confirmed_wallet_address:
            token_count = self.get_wsc_token_count(wallet_address)

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
            await self.message.channel.send(f"<@{member.id}>: `{role.name}` & `{default_role.name}` roles have been granted.")
        else:
            await self.message.channel.send(f'''
            <@{member.id}>, Make sure you followed the correct format: `!verify [your wallet address] [sig]`
Either you submitted an incorrect wallet address input or the signed message did not contain the right discord id message (e.g. test#1234). Please try again.
            ''')

    async def remove_non_holders(self):
        await self.message.channel.send("Starting the check for non holders...")
        owners_data = [
            {"discord_id": os.environ["DISCORD_ID"], "wallet_address": "0x310421C955b9a714Ad7a86C1c57c9698FD962318"},
        ]
        # check total token staked per address
        holder_roles_to_remove = [discord.utils.get(bot.get_all_members(), id=owner_data["discord_id"]) for owner_data in owners_data if self.get_wsc_token_count(owner_data["wallet_address"]) == 0]
        holder_role_ids = [x["role_id"] for x in settings.HOLDER_ROLES]

        for member in holder_roles_to_remove:
            for member_role in member.roles:
                if member_role.id in holder_role_ids:
                    role = discord.utils.get(member.guild.roles, id=member_role.id)
                    await member.remove_roles(role, reason="user is no longer a holder.")

            # remove default holder role
            default_role = discord.utils.get(member.guild.roles, id=settings.DEFAULT_HOLDER_ROLE)
            await member.remove_roles(default_role, reason="user is no longer a holder.")
        await self.message.channel.send("Holder roles have been removed from non holders.")

    async def update_holders(self):
        pass

    async def on_message(self, message):

        if message.author == self.user:
            return

        self.message = message
        self.msg = message.content

        # # check to remove non-holders
        # message_date = datetime.strptime(message.created_at.strftime(self.date_format), self.date_format)
        # if message_date > self.current_date:
        #     self.current_date = message_date
        #     await self.update_holders()
        #     await self.remove_non_holders()
        if self.msg == "!verify":
            await self.message.channel.send(f'''Please follow this format `!verify [your wallet address] [sig]`''')

        elif self.msg.startswith("!verify"):
            await self.grant_role()
            await message.delete()  # delete message after granting the role

        elif self.msg.startswith("!connection"):
            await self.eth_connection()


if __name__ == "__main__":
    load_dotenv()
    discord_token = os.environ["DISCORD_TOKEN"]

    bot = DiscordClient()
    bot.run(discord_token)
