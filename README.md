# Rimuru

This is a self-hostable Discord bot for posting RSS feed in your Discord server

## Commands

```
/add_feed <url(s)> <channel(s)>
```
- adds urls(s) to channel(s)
- if no channels specified, add the url(s) to all channels

```
/remove_feed <url(s)> <channel(s)>
```
- delete url(s) from channel(s)
- if no channels specified, remove the url(s) from all channels

```
/strip_feed <channels>
```
- removes all feeds from the channels specified

```
/update_poll_time <time>
```
- set when the bot should poll for more feed
- several options
    - 5 min, 10 min, 15 min, ... , 55 min
    - 1 hr, 2 hr, 3 hr, ... , 23 hr
    - specific days
    - specific times