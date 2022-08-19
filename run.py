import re
import os
import random
from dotenv import load_dotenv
from datetime import datetime

import ethscan_api
import pymongo_api
import web3_functions
import settings
import discord


class DiscordClient(discord.Client):

    async def on_ready(self):
        self.eth_client = web3_functions.EthClient()
        self.ethscan = ethscan_api.EthScan()
        self.pymongo_db = pymongo_api.PyMongo()
        self.date_format = "%Y-%m-%d"
        self.current_date = datetime.strptime("2022-05-17", self.date_format)

        # DISCORD
        self.holder_role_ids = [x["role_id"] for x in settings.HOLDER_ROLES]
        self.instructions_channel = settings.INSTRUCTIONS_CHANNEL
        self.guild = self.get_guild(settings.SERVER_ID)

        # MONGO DB
        self.wsc_holders_db = self.pymongo_db.client.wsc_holders

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

        # get raffle entries contract object
        self.raffle_contract_address = settings.RAFFLE_CONTRACT_ADDRESS
        self.raffle_entries_function = settings.RAFFLE_ENTRIES_FUNCTION
        self.raffle_contract_abi = self.ethscan.get_contract_abi(self.raffle_contract_address)
        self.raffle_contract_obj = self.eth_client.get_contract_obj(self.raffle_contract_address, self.raffle_contract_abi)

        print("We have logged in as:", self.user)

    async def eth_connection(self):
        await self.message.channel.send(self.eth_client.is_connected())

    def get_wsc_token_count(self, wallet_address):
        staked_list = self.eth_client.get_wsc_token_count(self.staking_contract_obj, self.count_staking_function, wallet_address)  # get staked count from address; returns list(int)
        unstaked_count = self.eth_client.get_wsc_token_count(self.unstaked_contract_obj, self.count_unstaked_function, wallet_address)  # get staked count from address; returns int
        total_wsc_token_owned = len(staked_list) + unstaked_count
        return total_wsc_token_owned

    def get_raffle_winner(self):
        raffle_entries = self.raffle_contract_obj.functions.buyersOfDraw().call()
        winner = random.choice(raffle_entries)
        return winner

    def confirm_signed_message(self, member, signature, wallet_address):
        try:
            signed_wallet = self.eth_client.get_address_of_signed_msg(member, signature)
        except Exception:
            signed_wallet = None
        return signed_wallet == wallet_address

    def store_data_to_mongodb(self, member, holder_role, wallet_address, token_count):
        data = {
            "updated_at": datetime.utcnow(),
            "wallet_address": wallet_address,
            "discord_id": str(member.id),
            "token_count": token_count,
            "holder_role": str(holder_role),
            }
        self.pymongo_db.insert_data_into_collection(self.wsc_holders_db.token_tracking, data)

    def del_data_in_mongodb(self, discord_id):
        search_query = {"discord_id": str(discord_id)}
        self.pymongo_db.delete_in_collection(self.wsc_holders_db.token_tracking, search_query)

    def get_current_holder_role(self, discord_id):
        search_query = {"$match": {"discord_id": str(discord_id)}}
        projection = {"holder_role": 1}
        res = list(self.wsc_holders_db.token_tracking.aggregate([search_query, {"$project": projection}]))
        return [int(r["holder_role"]) for r in res]

    def is_wallet_already_assigned(self, wallet_address):
        search_query = {"$match": {"wallet_address": wallet_address}}
        projection = {"discord_id": 1}
        res = list(self.wsc_holders_db.token_tracking.aggregate([search_query, {"$project": projection}]))
        return res[0]["discord_id"] if len(res) > 0 else False

    async def remove_role(self, member, role_id, reason):
        role = discord.utils.get(member.guild.roles, id=int(role_id))
        await member.remove_roles(role, reason=reason)

    async def grant_role(self, member, role_id, verbose=True):
        role = discord.utils.get(member.guild.roles, id=role_id)
        default_role = discord.utils.get(member.guild.roles, id=settings.DEFAULT_HOLDER_ROLE)

        await member.add_roles(role, reason="add specific nft holder count role")
        await member.add_roles(default_role, reason="add default nft holder count role")
        if verbose:
            await self.message.channel.send(f"<@{member.id}>: `{role.name}` & `{default_role.name}` roles have been granted.")
        print(f"<@{member.id}>: `{role.name}` & `{default_role.name}` roles have been granted.")

    async def set_roles(self, member, wallet_address, current_token_count, verbose=True):
        token_count = self.get_wsc_token_count(wallet_address)
        if not(current_token_count == token_count):
            holder_roles = self.get_current_holder_role(member.id)
            for role_id in holder_roles:
                await self.remove_role(member, role_id, "removing existing roles for a new role.")
                self.del_data_in_mongodb(member.id)

            if token_count == 0:
                try:
                    # default_role = discord.utils.get(self.guild.roles, id=settings.DEFAULT_HOLDER_ROLE)
                    await self.remove_role(member, settings.DEFAULT_HOLDER_ROLE, "removing holder role because they no longer have any wabis.")
                    self.del_data_in_mongodb(member.id)
                    print(member.id, "removed role")
                except Exception:
                    pass
                if verbose:
                    await self.message.channel.send(f'''<@{member.id}>, there is no staked/unstaked wabis in this wallet.''')
            else:
                role_id = None
                for holder in settings.HOLDER_ROLES:
                    if token_count >= holder["count"]:
                        role_id = holder["role_id"]
                        # end search when a role is assigned
                        if role_id is not None:
                            break
                        else:
                            continue

                self.store_data_to_mongodb(member, role_id, wallet_address, token_count)

                await self.grant_role(member, role_id, verbose)
                # create embed message
                embedMsg = discord.Embed(
                        title="Your Wabis have been verified!",
                        color=discord.Color.green(),
                    )

                embedMsg.add_field(name="total WSC tokens found", value=token_count, inline=False)
                if verbose:
                    await self.message.channel.send(embed=embedMsg)
                # await message.delete()  # delete message after granting the role
        else:
            print(member.id, "no change.")

    async def check_holders(self, verbose):
        '''
        load data from mongodb
        '''
        owners_data = [(document["discord_id"], document["wallet_address"], document["token_count"]) for document in self.wsc_holders_db.token_tracking.find({})]

        for data in owners_data:
            discord_id = data[0]
            try:
                member = await self.guild.fetch_member(discord_id)
                await self.set_roles(member, data[1], data[2], verbose)
            except Exception:
                self.del_data_in_mongodb(discord_id)
                print(discord_id, "does not exist")

    async def on_message(self, message):

        if message.author == self.user:
            return

        self.message = message
        self.msg = message.content

        if self.msg.startswith("!drawraffle"):
            winner = self.get_raffle_winner()
            await self.message.channel.send(f'''The winner for this draw is: {winner}.''')

        # check to update holder roles
        message_date = datetime.strptime(message.created_at.strftime(self.date_format), self.date_format)
        if message_date > self.current_date:
            self.current_date = message_date
            await self.check_holders(verbose=False)

        if self.msg == "!verify":
            await self.message.channel.send(f'''Read the instructions in <#{self.instructions_channel}>. Please follow this format `!verify [your wallet address] [sig]`''')

        elif self.msg.startswith("!verify"):
            wallet_address = re.sub('[^a-zA-Z0-9]+', '', self.msg.split(" ")[-2])
            signature = re.sub('[^a-zA-Z0-9]+', '', self.msg.split(" ")[-1])
            member = self.message.author

            confirmed_wallet_address = self.confirm_signed_message(str(member), signature, wallet_address)

            if confirmed_wallet_address:
                discord_id_assigned = self.is_wallet_already_assigned(wallet_address)
                if (discord_id_assigned is not False) & (member.id == discord_id_assigned):
                    await self.message.channel.send(f'''<@{member.id}>, this wallet has already been assigned to this discord account <@{discord_id_assigned}>. If you wish to use a different discord account, please reassign a new wallet to the old discord account first.''')
                    await message.delete()  # delete message after granting the role
                else:
                    await self.set_roles(member, wallet_address, 0)
            else:
                await self.message.channel.send(f'''
                <@{member.id}>, Make sure you followed the correct format: `!verify [your wallet address] [sig]`. Read the instructions in <#{self.instructions_channel}>.
    Either you submitted an incorrect wallet address input or the signed message did not contain the right discord id message (e.g. test#1234). Please try again.
                ''')

        elif self.msg.startswith("!connection"):
            await self.eth_connection()

        elif self.msg.startswith("!check"):
            await self.check_holders(verbose=True)


if __name__ == "__main__":
    load_dotenv()
    discord_token = os.environ["DISCORD_TOKEN"]

    bot = DiscordClient()
    bot.run(discord_token)
