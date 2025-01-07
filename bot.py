import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(intents=intents, command_prefix='!')

@client.event
async def on_ready():
    print('client ready')

@client.command()
async def ping(ctx):  # Add the 'ctx' parameter
    print('hey')
    await ctx.send('Pong')  # Use 'ctx.send()' instead of 'client.say()'

# @client.event
# async def on_message(message):
#     if client.user.id != message.author.id:
#         if 'foo' in message.content:
#             await message.channel.send('bar')  # Use 'message.channel.send()'

#     await client.process_commands(message)

@client.command()
async def displayembed(ctx):
    embed = discord.Embed(title="Your title here", description="Your desc here", color = discord.Color(0xFF5F05)) #,color=Hex code
    embed.add_field(name="Name", value="you can make as much as fields you like to")
    # embed.set_footer(name="footer") #if you like to
    await ctx.send(embed=embed)

client.run(TOKEN)
