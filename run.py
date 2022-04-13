import os
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
        self.current_date = datetime.strptime("2022-04-03", self.date_format)
        self.holder_role_ids = [x["role_id"] for x in settings.HOLDER_ROLES]

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

        print("We have logged in as:", self.user)

    async def eth_connection(self):
        await self.message.channel.send(self.eth_client.is_connected())

    def get_wsc_token_count(self, wallet_address):
        staked_list = self.eth_client.get_wsc_token_count(self.staking_contract_obj, self.count_staking_function, wallet_address)  # get staked count from address; returns list(int)
        unstaked_count = self.eth_client.get_wsc_token_count(self.unstaked_contract_obj, self.count_unstaked_function, wallet_address)  # get staked count from address; returns int
        total_wsc_token_owned = len(staked_list) + unstaked_count
        return total_wsc_token_owned

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

    async def grant_role(self, member, role_id):
        role = discord.utils.get(member.guild.roles, id=role_id)
        default_role = discord.utils.get(member.guild.roles, id=settings.DEFAULT_HOLDER_ROLE)

        await member.add_roles(role, reason="add specific nft holder count role")
        await member.add_roles(default_role, reason="add default nft holder count role")
        await self.message.channel.send(f"<@{member.id}>: `{role.name}` & `{default_role.name}` roles have been granted.")

    async def check_holders(self):
        '''
        load data from mongodb
        '''
        owners_data = None

        # check total token staked per address
        holder_roles_to_remove = []
        holder_roles_to_update = []

        for owner_data in owners_data:
            current_token_count = self.get_wsc_token_count(owner_data["wallet_address"])
            if current_token_count == 0:
                holder_roles_to_remove.append(discord.utils.get(bot.get_all_members(), id=owner_data["discord_id"]))
            elif current_token_count != owners_data["token_count"]:
                for holder in settings.HOLDER_ROLES:
                    if current_token_count >= holder["count"]:
                        role_id = holder["role_id"]
                if role_id != owner_data["holder_role"]:
                    holder_roles_to_update.append(discord.utils.get(bot.get_all_members(), id=owner_data["discord_id"]))

        if len(holder_roles_to_remove) > 0:
            for member in holder_roles_to_remove:
                for member_role in member.roles:
                    if member_role.id in self.holder_role_ids:
                        role = discord.utils.get(member.guild.roles, id=member_role.id)
                        await member.remove_roles(role, reason="user is no longer a holder.")

                # remove default holder role
                default_role = discord.utils.get(member.guild.roles, id=settings.DEFAULT_HOLDER_ROLE)
                await member.remove_roles(default_role, reason="user is no longer a holder.")
            await self.message.channel.send("Holder roles have been removed from non holders.")

        if len(holder_roles_to_update) > 0:
            for member in holder_roles_to_update:
                for member_role in member.roles:
                    if member_role.id in self.holder_role_ids:
                        current_role = discord.utils.get(member.guild.roles, id=member_role.id)
                        await member.remove_roles(current_role, reason="user is no longer a holder.")

                        new_role = discord.utils.get(member.guild.roles, id=role_id)
                        await member.add_roles(new_role, reason="add specific nft holder count role")
            await self.message.channel.send("Holder roles have been removed from non holders.")

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
            await self.message.channel.send('''Please follow this format `!verify [your wallet address] [sig]`''')

        elif self.msg.startswith("!verify"):
            wallet_address = self.msg.split(" ")[-2]
            signature = self.msg.split(" ")[-1]
            member = self.message.author

            confirmed_wallet_address = self.confirm_signed_message(str(member), signature, wallet_address)

            if confirmed_wallet_address:
                discord_id_assigned = self.is_wallet_already_assigned(wallet_address)
                if discord_id_assigned is not False:
                    discord_id_assigned = self.is_wallet_already_assigned(wallet_address)
                    await self.message.channel.send(f'''<@{member.id}>, this wallet has already been assigned to this discord account <@{discord_id_assigned}>. If you wish to use a different discord account, please reassign a new wallet to the old discord account first.''')
                    await message.delete()  # delete message after granting the role
                else:
                    holder_roles = self.get_current_holder_role(member.id)
                    for role_id in holder_roles:
                        await self.remove_role(member, role_id, "removing existing roles for a new role.")
                        self.del_data_in_mongodb(member.id)
                    token_count = self.get_wsc_token_count(wallet_address)

                    if token_count == 0:
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

                        await self.grant_role(member, role_id)
                        # create embed message
                        embedMsg = discord.Embed(
                                title="Your Wabis have been verified!",
                                color=discord.Color.green(),
                            )

                        embedMsg.add_field(name="total WSC tokens found", value=token_count, inline=False)
                        await self.message.channel.send(embed=embedMsg)
                        await message.delete()  # delete message after granting the role
            else:
                await self.message.channel.send(f'''
                <@{member.id}>, Make sure you followed the correct format: `!verify [your wallet address] [sig]`
    Either you submitted an incorrect wallet address input or the signed message did not contain the right discord id message (e.g. test#1234). Please try again.
                ''')

        elif self.msg.startswith("!connection"):
            await self.eth_connection()


if __name__ == "__main__":
    load_dotenv()
    discord_token = os.environ["DISCORD_TOKEN"]

    bot = DiscordClient()
    bot.run(discord_token)
