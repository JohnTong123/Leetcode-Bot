import os
import random
import time

# from pkg_resources import get_distribution

import discord
import requests
from discord.ext import commands, tasks
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import date
load_dotenv()
from discord.ui import Button, View


BOT_TOKEN = os.getenv("DISCORD_TOKEN")
PRODUCTION = os.getenv("PRODUCTION")
CONNECTION_STRING = os.getenv("CONNECTION_STRING")
CLIENT = MongoClient(CONNECTION_STRING)


# last_embed = None
SCORES = {}
MONTHLY_SCORES = {}

bot = None
if int(PRODUCTION) == 1:
    intents = discord.Intents(
        messages=True, message_content=True, guilds=True, guild_messages=True
    )
    bot = commands.Bot(command_prefix="!", intents=intents)
else:
    intents = discord.Intents(
        messages=True, message_content=True, guilds=True, guild_messages=True
    )
    bot = commands.Bot(command_prefix="!", intents=intents)


bot.remove_command("help")

def get_database():
    return CLIENT["users"]


class TimeoutView(View):
    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)  

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.primary, custom_id="left_arrow")
    async def left_arrow_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()  

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary, custom_id="right_arrow")
    async def right_arrow_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer()  

    # Optional: you can customize this method to handle additional things after timeout
    async def on_timeout(self):
        print("Timeout reached, disabling buttons.")
        for item in self.children:
            item.disabled = True  # Disable all buttons when timeout is reached
        await self.message.edit(view=self)  # Update the message to reflect button disablement


def call_leetcode_api(username):
    api_url = "https://leetcode.com/graphql?query="
    query = """
        {{ 
            matchedUser(username: "{0}") {{
                username
                submitStats: submitStatsGlobal {{
                    acSubmissionNum {{
                        difficulty
                        count
                        submissions
                    }}
                }}
            }}
        }}
    """.format(username)
    response = requests.get(api_url + query)
    print("Username " + str(username) + " : " + str(dict(response.json())))
    return dict(response.json())
    #return dict(requests.get(api_url + query).json())


# allows a synchronous call to the discord API
def get_discriminator_sync(id):
    url = f"https://discord.com/api/v9/users/{int(id)}"
    response = dict(requests.get(url, headers={"Authorization": f"Bot {BOT_TOKEN}"}).json())
    print(response)
    while "message" in response:
        time.sleep(1 + response["retry_after"])
        response = dict(requests.get(url, headers={"Authorization": f"Bot {BOT_TOKEN}"}).json())
    return str(f"{response['username']}#{response['discriminator']}")


def update_user_score(discord_id, name):
    db_user = list(get_database()["users"].find({'discord_id': discord_id}))[0]
    response = call_leetcode_api(db_user["leetcode_username"])
    score= calculate_score_from_response(response)
    SCORES[discord_id] = [score, name]

def update_monthly_user_score(discord_id, name):
    database= get_database()
    db_user = list(database["users"].find({'discord_id': discord_id}))[0]
    response = call_leetcode_api(db_user["leetcode_username"])
    score= calculate_month_score_from_response(response,database, discord_id)
    if score >0:
        MONTHLY_SCORES[discord_id] = [score, name]


def calculate_score_from_response(response):
    user_submissions_data = response["data"]["matchedUser"]["submitStats"]["acSubmissionNum"]
    easy = user_submissions_data[1]["count"]
    medium = user_submissions_data[2]["count"]
    hard = user_submissions_data[3]["count"]

    score = easy + (3 * medium) + (5 * hard)
    return score

def calculate_month_score_from_response(response, database, id):
    user_submissions_data = response["data"]["matchedUser"]["submitStats"]["acSubmissionNum"]
    easy = user_submissions_data[1]["count"]
    medium = user_submissions_data[2]["count"]
    hard = user_submissions_data[3]["count"]

    user =  database["users"].find({"discord_id":id})[0]
    print(user)
    print('debugging')
    score = (easy-user["easy"]) + 3* (medium-user["med"]) + 5*(hard-user["hard"])
    return score

# Method to update the SCORES global variable

def reset_user_monthly(response, database, id):
    user_submissions_data = response["data"]["matchedUser"]["submitStats"]["acSubmissionNum"]
    easy = user_submissions_data[1]["count"]
    medium = user_submissions_data[2]["count"]
    hard = user_submissions_data[3]["count"]
    database["users"].update_one(
        {"discord_id": id},  # Filter
        {
            "$set": {
                "hard": hard,
                "easy": easy,
                "med": medium
            }
        }
    )

def get_all_scores_from_api():
    # Key: discord id, Value: score
    print("Get scores has been called")

    database = get_database()
    users_collection = database["users"].find()
    users_list = list(users_collection)

    count = 1

    curr_date = str(date.today().month)
    monthly_reset = False
    global MONTHLY_SCORES
    # try:
    #     MONTHLY_SCORES
    # except NameError:
    #     MONTHLY_SCORES={}
    if  not list(database["date"].find({"date": curr_date})):
        # user_score(ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}")
        monthly_reset = True
        print('raaah')
        MONTHLY_SCORES = {}
        database["date"].insert_one({"date":curr_date})

    for user in users_list:
        
        response = call_leetcode_api(user["leetcode_username"])
        if monthly_reset is True:
            reset_user_monthly(response, database, user["discord_id"])

        SCORES[user["discord_id"]] = [calculate_score_from_response(response),
                                      str(get_discriminator_sync(user["discord_id"]))]
        
        month_score = calculate_month_score_from_response(response,database, user["discord_id"])
        # print(month_score)
        # print(user["discord_id"])
        # print('heeyyyyy')
        # print(MONTHLY_SCORES)
        if month_score >0:
            MONTHLY_SCORES[user["discord_id"]] = [month_score,
                                      str(get_discriminator_sync(user["discord_id"]))]

        if count % 30 == 0:
            time.sleep(10)
        count += 1


@tasks.loop(seconds=900)  # task runs every hour
async def score_background_task():
    get_all_scores_from_api()

@bot.command()
async def score(ctx):
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        return
    database = get_database()
    if list(database["users"].find({"discord_id": ctx.author.id})) == []:
        await ctx.send("You have not linked an account!")
    else:
        update_user_score(ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}")
        await ctx.send(f"You have {SCORES[ctx.author.id][0]} points")


def timestamp():
    return str(round(time.time() * 1000))

    



@bot.command(aliases=['t', 'lb', 'leaderboard'])
async def top(ctx, mod=None):
    # global last_embed
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        return
    # try:
        # last_embed
    # except NameError:
        # last_embed = None
    # if not last_embed is None:
        # await last_embed.edit(view=None)
    if mod is not None and mod in {"all","a"}:
        print("Updating user score from API " + timestamp())
        database = get_database()
        if list(database["users"].find({"discord_id": ctx.author.id})):
            update_user_score(ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}")
        print("User score has been updated " + timestamp())
        
        leaderboard = ""

        # Sort data by the total score values, from greatest to least
        print("sorting the SCORES variable " + timestamp())
        sorted_score_totals = sorted(SCORES.values(), reverse=True, key=lambda x: x[0])
        print("done sorting the SCORES variable " + timestamp())


        embed = discord.Embed(title="All-Time Leaderboard Page 1", color = discord.Color(0xFF5F05)) #,color=Hex code
        # embed.set_footer(name="footer") #if you like to
        left_arrow_button = Button(label="Previous", style=discord.ButtonStyle.primary, custom_id="left_arrow")
        right_arrow_button = Button(label="Next", style=discord.ButtonStyle.primary, custom_id="right_arrow")

        # Create a view to hold the buttons
        view = View(timeout=60)
        view.add_item(left_arrow_button)
        view.add_item(right_arrow_button)
        author_rank = -1
        author_score = -1

        pages = []
        current_page = 0
        position_no = 1
        for score_tuple in sorted_score_totals:
            print(f"{score_tuple}, about to append leaderboard string " + timestamp())
            # leaderboard += f"{str(position_no)}. {str(score_tuple[1])}: {str(score_tuple[0])} \n"
            embed.add_field(
                # name=f"{position_no}. {score_tuple[1]}: {score_tuple[0]} points",
                name = "",
                value=f"{position_no}. {score_tuple[1]}: {score_tuple[0]} points",  # Use a zero-width space to prevent empty field errors
                inline=False
            )
            print(f"{score_tuple}, done appending to leaderboard " + timestamp())

            # Save score and rank of user who called the command
            if score_tuple[1] == str(ctx.author.name) + str("#") + str(ctx.author.discriminator):
                author_rank = position_no
                author_score = score_tuple[0]
            # Discord messages are limited to 2000 characters. Every 75 users, the message is sent.
            if position_no % 20 == 0:
                pages.append(embed)
                current_page+=1
                embed = discord.Embed(title="All-Time Leaderboard Page "+str(current_page+1), color = discord.Color(0xFF5F05)) #,color=Hex code
                # await ctx.send(leaderboard)
                # await ctx.send(embed=embed,view=view)
                
                leaderboard = ""
            position_no += 1


        print("done, awaiting send " + timestamp())
        # await ctx.send(leaderboard)
        pages.append(embed)
        # await ctx.send(embed=embed,view=view)


        async def on_button_click(interaction):
            nonlocal current_page

            if interaction.data["custom_id"] == "left_arrow" and current_page > 0:
                current_page -= 1
            elif interaction.data["custom_id"] == "right_arrow" and current_page < len(pages) - 1:
                current_page += 1

            await interaction.response.defer()  # Acknowledge the interaction
            await interaction.message.edit(embed=pages[current_page], view=view)

        left_arrow_button.callback = on_button_click
        right_arrow_button.callback = on_button_click

        message = await ctx.send(embed=pages[0], view=view)
        # last_embed = message
        if author_rank == -1:
            await ctx.send("No account linked!")
        else:
            await ctx.send("You are #" + str(author_rank) + " with " + str(author_score) + " points.")

    elif mod is None:
        # print('heyyyy')
        # print(MONTHLY_SCORES)
        database = get_database()
        
        if list(database["users"].find({"discord_id": ctx.author.id})):
            # update_user_score(ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}")
            update_monthly_user_score(ctx.author.id, f"{ctx.author.name}#{ctx.author.discriminator}")
        print("User monthly score has been updated " + timestamp())
        position_no = 1
        # leaderboard = ""
        embed = discord.Embed(title="Monthly Leaderboard Page 1", color = discord.Color(0xFF5F05)) #,color=Hex code
        # embed.set_footer(name="footer") #if you like to
        left_arrow_button = Button(label="Previous", style=discord.ButtonStyle.primary, custom_id="left_arrow")
        right_arrow_button = Button(label="Next", style=discord.ButtonStyle.primary, custom_id="right_arrow")

        # Create a view to hold the buttons
        view = View(timeout=120)
        view.add_item(left_arrow_button)
        view.add_item(right_arrow_button)
        author_rank = -1
        author_score = -1

        pages = []
        current_page = 0
        position_no = 1
        
        # Sort data by the total score values, from greatest to least
        print("sorting the MONTHLY SCORES variable " + timestamp())
        sorted_score_totals = sorted(MONTHLY_SCORES.values(), reverse=True, key=lambda x: x[0])
        print("done sorting the MONTHLY SCORES variable " + timestamp())

        author_rank = -1
        author_score = -1

        

        for score_tuple in sorted_score_totals:
            print(f"{score_tuple}, about to append leaderboard string " + timestamp())
            # leaderboard += f"{str(position_no)}. {str(score_tuple[1])}: {str(score_tuple[0])} \n"
            embed.add_field(
                # name=f"{position_no}. {score_tuple[1]}: {score_tuple[0]} points",
                name = "",
                value=f"{position_no}. {score_tuple[1]}: {score_tuple[0]} points",  # Use a zero-width space to prevent empty field errors
                inline=False
            )
            print(f"{score_tuple}, done appending to leaderboard " + timestamp())

            # Save score and rank of user who called the command
            if score_tuple[1] == str(ctx.author.name) + str("#") + str(ctx.author.discriminator):
                author_rank = position_no
                author_score = score_tuple[0]
            # Discord messages are limited to 2000 characters. Every 75 users, the message is sent.
            if position_no % 20 == 0:
                pages.append(embed)
                current_page+=1
                embed = discord.Embed(title="MonthlyLeaderboard Page "+str(current_page+1), color = discord.Color(0xFF5F05)) #,color=Hex code
                leaderboard = ""
            position_no += 1

        pages.append(embed)

        print("done, awaiting send " + timestamp())
        # await ctx.send(embed=embed)
        async def on_button_click(interaction):
            nonlocal current_page

            if interaction.data["custom_id"] == "left_arrow" and current_page > 0:
                current_page -= 1
            elif interaction.data["custom_id"] == "right_arrow" and current_page < len(pages) - 1:
                current_page += 1

            await interaction.response.defer()  # Acknowledge the interaction
            await interaction.message.edit(embed=pages[current_page], view=view)

        left_arrow_button.callback = on_button_click
        right_arrow_button.callback = on_button_click

        message = await ctx.send(embed=pages[0], view=view)
        # last_embed = message
        # if leaderboard != "":
        #     await ctx.send(leaderboard)
        if author_rank == -1:
            await ctx.send("You have no monthly points!")
        else:
            await ctx.send("You are #" + str(author_rank) + " in the monthly leaderboard with " + str(author_score) + " points.")

        

    else:
        await ctx.send("Invalid modifier")

@bot.command()
async def forcetop(ctx):
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        return
    user_roles = ctx.author.roles
    approved_roles = {"Officer","Chair"}
    
    approved = False
    # print(user_roles)
    for role in user_roles:
        print(role.name)
        if role.name in approved_roles:
            approved= True
    
    if approved is True:
        SCORES = {}
        MONTHLY_SCORES = {}
        print("Updating user scores from API " + timestamp())
        get_all_scores_from_api()
        print("User scores has been updated " + timestamp())
        
    else:
        await ctx.send("You do not have permission to run this command")

@bot.command()
async def link(ctx, account_name):
    # Name of leetcode account to add to the database
    account_name = str(account_name)
    database = get_database()
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        return

    # If the user already exists
    if list(database["users"].find({"discord_id": ctx.author.id})):
        await ctx.send("You already linked an account")

    # If the status is "error," then the account does not exist (or some other issue has occurred)
    elif "errors" in call_leetcode_api(account_name):
        await ctx.send("Error while linking account")

    # If account is valid and not in database, add to database
    else:
        new_user = {"leetcode_username": account_name, "discord_id": ctx.author.id, "hard":-1,"med":-1,"easy":-1}
        database["users"].insert_one(new_user)
        await ctx.send(f"Set Leetcode account for {str(ctx.author)} to {account_name}")
        await score(ctx)
        reset_user_monthly( call_leetcode_api(account_name),database,ctx.author.id )

@bot.command()
async def unlink(ctx):
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        return
    # Name of leetcode account to add to the database
    account_id = ctx.author.id
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        return
    database = get_database()

    # If the user already exists
    if not list(database["users"].find({"discord_id": ctx.author.id})):
        await ctx.send("You don't have an account linked")

    else:
        query_filter = {"discord_id": ctx.author.id}
        database["users"].delete_one(query_filter)
        del SCORES[account_id]
        del MONTHLY_SCORES[account_id]
        await ctx.send("Account unlinked")

@bot.command()
async def forceunlink(ctx, discord_id):
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        return
    # Name of leetcode account to add to the database

    user_roles = ctx.author.roles
    approved_roles = {"Officer","Chair"}
    
    approved = False
    # print(user_roles)
    for role in user_roles:
        if role.name in approved_roles:
            approved= True
    
    if approved is True:

        account_id = int(discord_id)
        database = get_database()

        # If the user already exists
        if not list(database["users"].find({"discord_id": account_id})):
            await ctx.send("User doesn't have account linked")

        else:
            query_filter = {"discord_id": account_id}
            database["users"].delete_one(query_filter)
            del SCORES[account_id]
            del MONTHLY_SCORES[account_id]
            await ctx.send("Account unlinked")
    
    else:
        await ctx.send("Not approved to run command")
   

@bot.command()
async def help(ctx):
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        return
    embed = discord.Embed(title = "Help")

    embed.add_field(name = "Use", value = "To add your account, use \"!link [your Leetcode username].\" To unlink your account use !unlink. To see your score, use !score, to see the monthly leaderboard, use !top or !t, and to see the all-time leaderboard use !top a")

    await ctx.send(embed = embed)


@bot.event
async def on_ready():
    print("We have logged in as {0.user}".format(bot))
    score_background_task.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        if str(message.content) == "<@" + str(541736536463507476) + ">":
            await message.delete()
        return
    if "phase 2" in str(message.content).lower():
        await message.channel.send("phase 2 :sparkles: :sparkles:")
    await bot.process_commands(message)


@bot.command()
async def credit(ctx):
    if not str(ctx.channel) in {"lcdegens", "leetcode-leaderboard"}:
        print(ctx.channel)
        return
    await ctx.send("Original bot comes from Georgia Tech's LC Server. Github: https://github.com/SaatvikAgrawal/GT-Leetcode-Bot.git")



bot.run(BOT_TOKEN)
