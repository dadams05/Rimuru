import os
import json
import time
from datetime import datetime
from email.utils import parsedate_to_datetime

import discord
import feedparser
import requests
from discord.ext import commands
from dotenv import load_dotenv
from markdownify import markdownify as md

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
        print(f"Synced {len(synced)} command(s). Bot is ready.")
    except Exception as e:
        print(e)


@bot.tree.command(name="add_feed")
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
            "last_post_id": "",
            "last_updated": "",
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


@bot.tree.command(name="remove_feed")
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


@bot.tree.command(name="poll_feed")
async def poll_feed(interaction: discord.Interaction):
    # load current configuration
    with open(CONFIG_FILE, "r") as file:
        configuration = json.load(file)
    # make sure there are any feeds
    if "feeds" not in configuration.keys():
        return
    current_time = time.time()
    # start polling feeds
    for feed in configuration["feeds"]:
        data = feedparser.parse(feed)
        last_post_id = configuration["feeds"][f"{feed}"]["last_post_id"]
        last_updated = float(configuration["feeds"][f"{feed}"].get("last_updated", 0))
        newest_post_id = ""
        # sort through entries retrieved
        for i, entry in enumerate(data.entries):
            if entry.id == last_post_id:
                break
            if (
                parsedate_to_datetime(entry.published).timestamp()
                if hasattr(entry, "published")
                else 0
            ) <= last_updated and last_updated != 0:
                continue
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
                full_description = f"{summary}\n\n{content_body}"
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
                channel = bot.get_channel(int(channel_id))
                if channel:
                    await channel.send(embed=embed)
    # update the feed values
    configuration["feeds"][f"{feed}"]["last_post_id"] = newest_post_id
    configuration["feeds"][f"{feed}"]["last_updated"] = current_time
    # save the config
    with open(CONFIG_FILE, "w") as file:
        json.dump(configuration, file, indent=4)


# generate the config file on start if it doesn't exist
try:
    with open(CONFIG_FILE, "x") as file:
        default = {
            "settings": {"poll_interval": "1hr", "global_muted_feeds": []},
            "channels": {},
            "feeds": {},
        }
        json.dump(default, file, indent=4)
except FileExistsError:
    pass  # file already exists

# start the bot
bot.run(token)
