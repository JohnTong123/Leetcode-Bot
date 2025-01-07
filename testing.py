import os
import random
import time

# from pkg_resources import get_distribution

import discord
import requests
from discord.ext import commands, tasks
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

CONNECTION_STRING = os.getenv("CONNECTION_STRING")
CLIENT = MongoClient(CONNECTION_STRING)

print(CLIENT.keys())