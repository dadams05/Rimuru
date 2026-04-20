import discord
from discord.ext import commands
import os
import feedparser
import validators
from dotenv import load_dotenv
import bleach
import json
import requests
import json

# https://www.polygon.com/feed/news/

CONFIG_FILE = "config.json"

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)


@bot.tree.command(name="add_feed", description="Add new RSS feed(s) to channel(s)")
async def add_feed(interaction: discord.Interaction, values: str):
    args = list(set([arg.strip() for arg in values.split(" ")]))

    # process the arguments to sort URLs and channels
    new_URLs = []
    new_channels = []
    for arg in args:
        if validators.url(arg):
            new_URLs.append(arg)
        else:
            new_channels.append(arg)
    
    # test the given URLs to make sure they are valid URLs
    invalid_URLs = []
    for url in new_URLs:
        try:
            response = requests.get(url, timeout=5, stream=True)
            response.raise_for_status() # auto check for 4XX or 5XX errors

            # check if the content type is actually XML/RSS
            content_type = response.headers.get('Content-Type', '').lower()
            if 'xml' not in content_type and 'rss' not in content_type:
                raise requests.RequestException
            
        except requests.RequestException:
            invalid_URLs.append(url)
    
    # test the given channels to make sure they are valid
    guild = bot.get_guild(interaction.guild_id)
    empty = (new_channels == [])
    updating_channels = []
    if guild:
        print(guild.channels)
        for channel in guild.channels:
            if "text" in channel.type or "voice" in channel.type:
                if empty: # if no channels were given, add feed to all channels
                    updating_channels.append(channel)
                elif channel.name in new_channels:
                    updating_channels.append(channel)
                    new_channels.remove(channel.name)

    # fail out if any invalid URLs or invalid channels
    if new_channels or invalid_URLs:
        await interaction.response.send_message(f"Invalid arguments(s). Make sure you give valid URLs or channel names:\n{"\n".join(invalid_URLs)}\n{"\n".join(new_channels)}", ephemeral=True)
        return
        
    # all checks passed, update config
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)

    # ensure the keys exist to avoid KeyError
    if "channels" not in configuration: configuration["channels"] = {}
    if "feeds" not in configuration: configuration["feeds"] = {}

    # add the updated channels to the "channels" key
    for new_channel in updating_channels:
        chan_id = str(new_channel.id)
        if chan_id not in configuration["channels"]:
            configuration["channels"][chan_id] = {"muted": False}

    # add/update the feeds
    for url in new_URLs:
        new_ids = [str(c.id) for c in updating_channels]
        if url in configuration["feeds"]:
            current_subs = set(configuration["feeds"][url]["subscribed_channels"])
            configuration["feeds"][url]["subscribed_channels"] = list(current_subs | set(new_ids))
        else:
            configuration["feeds"][url] = {
                "last_post_id": "",
                "last_updated": "",
                "subscribed_channels": new_ids
            }

    # save the config
    with open(CONFIG_FILE, "w") as file:
        json.dump(configuration, file, indent=4)

    # send the success message
    embed = discord.Embed(title="Success!", 
                          description=f"The following channels:{"".join(f"\n- {channel.mention}" for channel in updating_channels)}\nWill now post the following feeds:{"".join(f"\n- {url}" for url in new_URLs)}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# generate the config file if it doesn't exist
try:
    with open(CONFIG_FILE, "x") as file:
        default = {
            "settings": {
                "poll_interval": "1hr",
                "global_muted_feeds": []
            },
            "channels": {},
            "feeds": {}
        }
        json.dump(default, file, indent=4)
except FileExistsError:
    pass # file already exists

# start the bot
bot.run(token)
