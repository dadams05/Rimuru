import os
import sys
import json
import time
import logging
from typing import Literal
from datetime import datetime
from email.utils import parsedate_to_datetime

import discord
import feedparser
import requests
from discord.ext import commands, tasks
from dotenv import load_dotenv
from markdownify import markdownify as md

# https://www.polygon.com/feed/news/
# https://gamerant.com/feed/gaming/

CONFIG_FILE = "config.json"

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

#############################################################################################
# add/remove RSS feed
#############################################################################################

@bot.tree.command(name="add_feed",description="Add a RSS feed to be posted in a specific channel")
async def add_feed(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.VoiceChannel,
    url: str,
):
    # check if the bot actually HAS permission to send messages there
    if not channel.permissions_for(interaction.guild.me).send_messages:
        await interaction.response.send_message(
            "I don't have permission to post in that channel!", ephemeral=True
        )
        return
    # check that the url is valid RSS feed
    try:
        response = requests.get(url, timeout=5, stream=True)
        response.raise_for_status()  # auto check for 4XX or 5XX errors
        # check if the content type is actually XML/RSS
        content_type = response.headers.get("Content-Type", "").lower()
        if "xml" not in content_type and "rss" not in content_type:
            raise requests.RequestException
    except requests.RequestException:
        await interaction.response.send_message(
            "Invalid URL. Please give a valid RSS URL!", ephemeral=True
        )
        return
    # load current configuration
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    # add the channel into the config if it doesn't exist
    channel_id = str(channel.id)
    if channel_id not in configuration["channels"]:
        configuration["channels"][channel_id] = {
            "name": channel.name,
            "type": channel.type[0],
            "muted": False,
        }
    # add/update the feed
    if url in configuration["feeds"]:
        current_subs = set(configuration["feeds"][url]["subscribed_channels"])
        current_subs.add(channel_id)
        configuration["feeds"][url]["subscribed_channels"] = list(current_subs)
    else:
        configuration["feeds"][url] = {
            "muted": False,
            "last_post_id": "",
            "last_updated": 0,
            "subscribed_channels": [channel_id],
        }
    # save the config
    with open(CONFIG_FILE, "w") as file:
        json.dump(configuration, file, indent=4)
    # send the success message
    embed = discord.Embed(
        title="Success!", description=f"{channel.mention} will now post feed from {url}"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="remove_feed",description="Remove a RSS feed from a specific channel")
async def remove_feed(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.VoiceChannel,
    url: str,
):
    # check if the bot has permission to send messages in the channel
    if not channel.permissions_for(interaction.guild.me).send_messages:
        embed = discord.Embed(
            title="Permission Error!",
            description="I do not have permission to post in that channel!",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    # load current configuration
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    # check that the url is in the configuration
    if url not in configuration["feeds"]:
        embed = discord.Embed(
            title="URL Error!",
            description="Invalid URL. Please give a URL currently in use to remove!",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    # remove/update the feeds
    channel_id = str(channel.id)
    current_subs = set(configuration["feeds"][url]["subscribed_channels"])
    try:
        current_subs.remove(channel_id)
        configuration["feeds"][url]["subscribed_channels"] = list(current_subs)
    except Exception:
        embed = discord.Embed(
            title="Channel URL Error!",
            description=f"{channel.mention} does not post feed from {url}! Nothing changed!",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    # save the config
    with open(CONFIG_FILE, "w") as file:
        json.dump(configuration, file, indent=4)
    # send the success message
    embed = discord.Embed(
        title="Success!",
        description=f"{channel.mention} will no longer post feed from {url}",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

#############################################################################################
# un/mute a channel
#############################################################################################

@bot.tree.command(name="mute_channel",description="Mute a specific channel; RSS feed will no longer be posted in that channel")
async def mute_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.VoiceChannel,
):
    # load current configuration
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    # make sure the key exists
    if str(channel.id) not in configuration["channels"]:
        configuration["channels"][str(channel.id)] = {
            "name": channel.name,
            "type": channel.type[0],
            "muted": True
        }
    else:
        configuration["channels"][str(channel.id)]["muted"] = True
    # save the config
    with open(CONFIG_FILE, "w") as file:
        json.dump(configuration, file, indent=4)
    # send the success message
    embed = discord.Embed(
        title="Success!",
        description=f"{channel.mention} has been muted and will not post any more RSS feed!",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="unmute_channel",description="Unmute a specific channel; RSS feed will be posted in that channel")
async def unmute_channel(
    interaction: discord.Interaction,
    channel: discord.TextChannel | discord.VoiceChannel,
):
    # load current configuration
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    # make sure the key exists
    if str(channel.id) not in configuration["channels"]:
        configuration["channels"][str(channel.id)] = {
            "name": channel.name,
            "type": channel.type[0],
            "muted": False
        }
    else:
        configuration["channels"][str(channel.id)]["muted"] = False
    # save the config
    with open(CONFIG_FILE, "w") as file:
        json.dump(configuration, file, indent=4)
    # send the success message
    embed = discord.Embed(
        title="Success!",
        description=f"{channel.mention} has been unmuted and will now start posting RSS feed again!",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

#############################################################################################
# un/mute all channels
#############################################################################################

@bot.tree.command(name="mute_all_channels", description="Mutes all channels")
async def mute_all_channels(interaction: discord.Interaction):
    # load current config
    with open(CONFIG_FILE, "r") as file: config = json.load(file)
    # mute all the channels
    for channel in config["channels"]: channel["muted"] = True
    # save the config
    with open(CONFIG_FILE, "w") as file: json.dump(config, file, indent=4)
    # send the success message
    embed = discord.Embed(title="Success!", description=f"All channels have been muted!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="unmute_all_channels", description="Unmutes all channels")
async def unmute_all_channels(interaction: discord.Interaction):
    # load current config
    with open(CONFIG_FILE, "r") as file: config = json.load(file)
    # mute all the channels
    for channel in config["channels"]: channel["muted"] = False
    # save the config
    with open(CONFIG_FILE, "w") as file: json.dump(config, file, indent=4)
    # send the success message
    embed = discord.Embed(title="Success!", description=f"All channels have been unmuted!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

#############################################################################################
# un/mute a RSS feed
#############################################################################################

@bot.tree.command(name="mute_feed", description="Mute a specific RSS feed")
async def mute_feed(interaction: discord.Interaction, url: str):
    # load current configuration
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    configuration["feeds"][url]["muted"] = True
    # save the config
    with open(CONFIG_FILE, "w") as file:
        json.dump(configuration, file, indent=4)
    # send the success message
    embed = discord.Embed(
        title="Success!",
        description=f"{url} has been muted for all channels!",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@mute_feed.autocomplete('url')
async def feed_autocomplete(interaction: discord.Interaction, current: str):
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    
    feeds = configuration.get("feeds", {})
    
    # Return a list of choices that match what the user is typing
    return [
        discord.app_commands.Choice(name=url, value=url)
        for url in feeds.keys() if current.lower() in url.lower()
    ][:25] # Discord limits autocomplete to 25 suggestions

@bot.tree.command(name="unmute_feed", description="Unmute a specific RSS feed")
async def unmute_feed(interaction: discord.Interaction, url: str):
    # load current configuration
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    configuration["feeds"][url]["muted"] = False
    # save the config
    with open(CONFIG_FILE, "w") as file:
        json.dump(configuration, file, indent=4)
    # send the success message
    embed = discord.Embed(
        title="Success!",
        description=f"{url} has been unmuted for all channels!",
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@unmute_feed.autocomplete('url')
async def feed_autocomplete(interaction: discord.Interaction, current: str):
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    
    feeds = configuration.get("feeds", {})
    
    return [
        discord.app_commands.Choice(name=url, value=url)
        for url in feeds.keys() if current.lower() in url.lower()
    ][:25] # Discord limits autocomplete to 25 suggestions

#############################################################################################
# un/mute all feeds
#############################################################################################

@bot.tree.command(name="mute_all_feeds", description="Mutes all RSS feeds")
async def mute_all_feeds(interaction: discord.Interaction):
    # load current configuration
    with open(CONFIG_FILE, "r") as file: config = json.load(file)
    # mute all the channels
    for feed in config["feeds"]: feed["muted"] = True
    # save the config
    with open(CONFIG_FILE, "w") as file: json.dump(config, file, indent=4)
    # send the success message
    embed = discord.Embed(title="Success!", description=f"All feeds have been unmuted!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="unmute_all_feeds", description="Unmutes all RSS feeds")
async def unmute_all_feeds(interaction: discord.Interaction):
    # load current configuration
    with open(CONFIG_FILE, "r") as file: config = json.load(file)
    # mute all the channels
    for feed in config["feeds"]: feed["muted"] = False
    # save the config
    with open(CONFIG_FILE, "w") as file: json.dump(config, file, indent=4)
    # send the success message
    embed = discord.Embed(title="Success!", description=f"All feeds have been unmuted!")
    await interaction.response.send_message(embed=embed, ephemeral=True)

#############################################################################################
# polling stuff
#############################################################################################

@tasks.loop(minutes=1.0)
async def poll_feed():
    logger.info("Polling feed now")
    try:
        # load current configuration
        with open(CONFIG_FILE, "r") as file:
            configuration = json.load(file)
        # make sure there are any feeds
        if "feeds" not in configuration.keys():
            return
        current_time = time.time()
        channels = configuration["channels"]
        # start polling feeds
        for feed in configuration["feeds"]:
            # skip muted feeds
            if configuration["feeds"][f"{feed}"]["muted"]: continue
            # get new feed data
            data = feedparser.parse(feed)
            last_post_id = configuration["feeds"][f"{feed}"]["last_post_id"]
            last_updated = float(configuration["feeds"][f"{feed}"].get("last_updated", 0))
            newest_post_id = last_post_id
            # sort through entries retrieved
            for i, entry in enumerate(data.entries):
                if entry.id == last_post_id:
                    break
                if (
                    parsedate_to_datetime(entry.published).timestamp()
                    if hasattr(entry, "published")
                    else 0
                ) <= last_updated and last_updated != 0:
                    # continue
                    pass
                if i == 0:
                    newest_post_id = entry.id
                # safely handle the description/content
                summary = entry.get("summary", "")
                # check if content exists, otherwise default to empty string
                content_list = entry.get("content", [])
                content_body = (
                    md(content_list[0]["value"], strip=["img", "video"])
                    if content_list
                    else ""
                )
                # avoid duplicating summary if it's already in the content
                if summary in content_body:
                    full_description = content_body
                else:
                    full_description = f"{summary}\n----------------------------------\n{content_body}"
                # embeds have 4096 character limit
                if len(full_description) > 4000:
                    full_description = full_description[:3997] + "..."
                # set up the embed
                embed = discord.Embed(
                    title=entry.get("title", "No Title"),
                    url=entry.get("link", ""),
                    description=full_description,
                    timestamp=parsedate_to_datetime(entry.published)
                    if hasattr(entry, "published")
                    else datetime.now(),
                )
                # the author is set to the name of the website of the feed
                if "title" in data.feed:
                    embed.set_author(name=data.feed.title)
                # add an image if there is one
                for link in entry.get("links", []):
                    if "image" in link.get("type", "") or "jpeg" in link.get("type", ""):
                        embed.set_image(url=link["href"])
                        break
                # send the created embed to the subscribed channels
                for channel_id in configuration["feeds"][f"{feed}"]["subscribed_channels"]:
                    if not channels[channel_id]["muted"]:
                        channel = bot.get_channel(int(channel_id))
                        if channel:
                            try:
                                await channel.send(embed=embed)
                            except Exception as e:
                                logger.error(f"Error sending to {channel_id}: {e}")
            # update the feed values
            configuration["feeds"][f"{feed}"]["last_post_id"] = newest_post_id
            configuration["feeds"][f"{feed}"]["last_updated"] = current_time
        # save the config
        with open(CONFIG_FILE, "w") as file:
            json.dump(configuration, file, indent=4)
    except Exception as e:
        logger.error(f"Error somewhere {e}")
        import traceback
        traceback.print_exc()

@bot.tree.command(name="set_poll_time", description="Change how often the bot checks feeds and posts updates")
async def set_poll_time(interaction: discord.Interaction, unit: Literal["minute", "hour"], quantity: int):
    # Logic to convert everything to minutes for the task loop
    if unit == "hour":
        total_minutes = quantity * 60
    else:
        total_minutes = quantity

    if total_minutes < 0:
        embed = discord.Embed(
            title="Too small!",
            description=f"Poll interval must be at least 10 minutes!"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # update saved configuration
    with open(CONFIG_FILE, "r") as file: config = json.load(file)
    config["settings"]["poll_unit"] = unit
    config["settings"]["poll_interval"] = quantity
    with open(CONFIG_FILE, "w") as file: json.dump(config, file, indent=4)
    # update the bot's poll time
    poll_feed.change_interval(minutes=float(total_minutes))

    embed = discord.Embed(
        title="Success!",
        description=f"Poll interval has been set to {quantity} {unit}s!" if quantity > 1 else f"Poll interval has been set to {quantity} {unit}!"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

#############################################################################################
# main stuff
#############################################################################################

@bot.event
async def on_ready():
    try:
        # load current configuration
        with open(CONFIG_FILE, "r") as file: config = json.load(file)
        # extract polling config data
        poll_unit = config["settings"].get("poll_unit", "hour")
        poll_interval = config["settings"].get("poll_interval", 1)
        total_minutes = poll_interval * 60 if poll_unit == "hour" else poll_interval
        # dynamically set the poll interval and start polling
        poll_feed.change_interval(minutes=float(total_minutes))
        if not poll_feed.is_running(): poll_feed.start()
        # the bot is ready to go
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} command(s). Bot is ready.")
    except Exception as e:
        logger.error(e)

if __name__ == "__main__":
    # generate the config file on start if it doesn't exist
    try:
        with open(CONFIG_FILE, "x") as file:
            default = {
                "settings": {
                    "poll_unit": "hour", 
                    "poll_interval": 1
                },
                "channels": {},
                "feeds": {},
            }
            json.dump(default, file, indent=4)
    except FileExistsError:
        pass
    # start the bot
    bot.run(token)
