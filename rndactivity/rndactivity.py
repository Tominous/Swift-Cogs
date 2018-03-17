from asyncio import sleep
from typing import List, Union

import discord
from discord.ext import commands

from redbot.core.bot import Red, RedContext
from redbot.core import Config, checks
from redbot.core.i18n import CogI18n
from redbot.core.utils.chat_formatting import pagify, info, warning, escape

from random import choice

from odinair_libs.menus import confirm
from odinair_libs.converters import FutureTime
from odinair_libs.formatting import tick

_ = CogI18n("RNDActivity", __file__)


class RNDActivity:
    """Random bot playing statuses"""

    __author__ = "odinair <odinair@odinair.xyz>"
    __version__ = "0.1.0"

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=2042511098, force_registration=True)
        self.config.register_global(statuses=[], delay=600)
        self._status_task = self.bot.loop.create_task(self.timer())

    def __unload(self):
        self._status_task.cancel()

    @commands.group()
    @checks.is_owner()
    async def rndactivity(self, ctx: RedContext):
        """Manage random statuses"""
        if not ctx.invoked_subcommand:
            await ctx.send_help()

    _min_duration = FutureTime.get_seconds("5 minutes")

    @rndactivity.command(name="delay")
    async def rndactivity_delay(self, ctx: RedContext, *,
                                duration: FutureTime.converter(min_duration=_min_duration, strict=True,
                                                               max_duration=None)):
        """Set the amount of time required to pass in seconds to change the bot's playing status

        Duration can be formatted like `5m`, `1h3.5m`, `5 minutes`, or `1 hour 3.5 minutes`

        Minimum duration between changes is 5 minutes.
        Default delay is 10 minutes, or every 600 seconds
        """
        await self.config.delay.set(duration.total_seconds())
        await ctx.send(tick(_("Set time between status changes to {}.\n"
                              f"This will take effect after the next status change.").format(duration.format())))

    async def _add_status(self, ctx: RedContext, game: str, *, game_type: int = 0):
        try:
            self.format_status({"type": game_type, "game": game})
        except KeyError as e:
            await ctx.send(warning(_("Parsing that status failed - {} is not a valid placeholder").format(str(e))))
            return

        async with self.config.statuses() as statuses:
            statuses.append({"type": game_type, "game": game})
            await ctx.send(tick(_("Status **#{}** added.").format(len(statuses))))

    @rndactivity.command(name="add", aliases=["playing"])
    async def rndactivity_add(self, ctx: RedContext, *, status: str):
        """Add a playing status

        Available placeholders:

        **{GUILDS}**  Replaced with the amount of guilds the bot is in
        **{MEMBERS}**  Replaced with the amount of members in all guilds the bot is in
        **{UNIQUE_MEMBERS}**  Replaced with the amount of unique users the bot can see
        **{CHANNELS}**  Replaced with the amount of channels that are in all the guilds the bot is in
        **{SHARD}**  Replaced with the bot's shard ID
        **{SHARDS}**  Replaced with the total amount of shards the bot has loaded
        **{COMMANDS}**  Replaced with the amount of commands loaded
        **{COGS}**  Replaced with the amount of cogs loaded

        The guilds that a shard contains will be used to parse a status, instead of every guild the bot is in.

        You can use `[p]rndactivity parse` to test your status strings

        Any invalid placeholders will cause the status to be ignored when switching statuses
        """
        await self._add_status(ctx, status)

    @rndactivity.command(name="watching")
    async def rndactivity_add_watching(self, ctx: RedContext, *, status: str):
        """Add a watching status

        See `[p]help rndactivity add` for help on placeholders
        """
        await self._add_status(ctx, status, game_type=3)

    @rndactivity.command(name="listening")
    async def rndactivity_add_listening(self, ctx: RedContext, *, status: str):
        """Add a listening status

        See `[p]help rndactivity add` for help on placeholders
        """
        await self._add_status(ctx, status, game_type=2)

    @rndactivity.command(name="parse")
    async def rndactivity_parse(self, ctx: RedContext, *, status: str):
        """Attempt to parse a given status string

        See `[p]help rndactivity add` for the list of available placeholders
        """
        shard = getattr(ctx.guild, "shard_id", 0)

        try:
            result, result_type = self.format_status(status, shard=shard)
        except KeyError as e:
            await ctx.send(warning(_("Placeholder {} does not exist\n\n"
                                     "See `{}help rndactivity add` for the list of placeholder strings")
                                   .format(escape(str(e), mass_mentions=True), ctx.prefix)))
            return

        status = escape(status, mass_mentions=True)
        result = escape(result, mass_mentions=True)
        await ctx.send(content=_("\N{INBOX TRAY} **Input:**\n{status}\n\n"
                                 "\N{OUTBOX TRAY} **Result:**\n{result}").format(status=status, result=result))

    @rndactivity.command(name="remove", aliases=["delete"])
    async def rndactivity_remove(self, ctx: RedContext, *statuses: int):
        """Remove one or more statuses by their IDs

        You can retrieve the ID for a status with [p]rndactivity list
        """
        statuses = [x for x in statuses if x > 0]
        if not statuses:
            await ctx.send_help()
            return

        bot_statuses = list(await self.config.statuses())
        for status in statuses:
            if len(bot_statuses) < status:
                await ctx.send(warning(_("The status {} doesn't exist").format(status)))
                return
            bot_statuses[status - 1] = None

        bot_statuses = [x for x in bot_statuses if x is not None]  # Clear out None entries
        await self.config.statuses.set(bot_statuses)
        if len(bot_statuses) == 0:
            await self.bot.change_presence(activity=None, status=self.bot.guilds[0].me.status)
        await ctx.send(info(_("Removed {amnt} status{plural}.").format(amnt=len(statuses),
                                                                       plural='es' if len(statuses) != 1 else '')))

    @rndactivity.command(name="list")
    async def rndactivity_list(self, ctx: RedContext, parse: bool=False):
        """Lists all set statuses

        If parse is passed, all status strings are shown as their parsed output, similarly to `[p]rndactivity parse`
        Invalid placeholders will still be identified and marked without enabling parse mode
        """
        orig_statuses = list(await self.config.statuses())
        if not len(orig_statuses):
            await ctx.send(warning(_("I have no random statuses setup! Use `{}rndactivity add` to add some!")
                                   .format(ctx.prefix)))
            return
        statuses = []
        shard = getattr(ctx.guild, "shard_id", 0)
        for item in orig_statuses:
            try:
                parsed, game_type = self.format_status(item, shard=shard, return_formatted=parse)
                statuses.append(f"{orig_statuses.index(item) + 1} \N{EM DASH} {parsed!r}")
            except KeyError as e:
                if isinstance(item, str):
                    status = item
                else:
                    status = item["game"]
                statuses.append(f"{orig_statuses.index(item) + 1} \N{EM DASH} {status!r}  # " +
                                _("Placeholder {} doesn't exist").format(str(e)))

        await ctx.send_interactive(messages=pagify("\n".join(statuses), escape_mass_mentions=True, shorten_by=10),
                                   box_lang="py")

    @rndactivity.command(name="clear")
    async def rndactivity_clear(self, ctx: RedContext):
        """Clears all set statuses"""
        amnt = len(await self.config.statuses())
        if await confirm(ctx, _("Are you sure you want to clear {amnt} statuses?\n\n"
                                "This action is irreversible!").format(amnt=amnt),
                         colour=discord.Colour.red()):
            await self.config.statuses.set([])
            await self.bot.change_presence(activity=None, status=self.bot.guilds[0].me.status)
            await ctx.send(tick(_("Successfully cleared {amnt} status strings.").format(amnt=amnt)), delete_after=15.0)
        else:
            await ctx.send(_("Okay then."), delete_after=15.0)

    def format_status(self, status: Union[str, dict], shard: int = None, return_formatted=True):
        game_type = 0
        if isinstance(status, dict):
            game_type = status.get("type", 0)
            status: str = status.get("game")
        formatted = status.format(
            GUILDS=len(self.bot.guilds),
            SHARDS=self.bot.shard_count,
            SHARD="{SHARD}" if shard is None else shard + 1,
            COGS=len(self.bot.cogs),
            COMMANDS=len(self.bot.all_commands),
            MEMBERS=sum([x.member_count for x in self.bot.guilds]),
            UNIQUE_MEMBERS=len(self.bot.users),
            CHANNELS=sum([len(x.channels) for x in self.bot.guilds])
        )
        return status if not return_formatted else formatted, game_type

    async def update_status(self, statuses: List[str]):
        if not statuses:
            return
        status = choice(statuses)
        for shard in self.bot.shards.keys():
            try:
                game, game_type = self.format_status(status, shard=shard)
            except KeyError:
                return
            game = discord.Activity(name=game, type=discord.ActivityType(game_type))
            await self.bot.change_presence(activity=game, status=self.bot.guilds[0].me.status, shard_id=shard)

    async def timer(self):
        while self == self.bot.get_cog(self.__class__.__name__):
            await self.update_status(list(await self.config.statuses()))
            await sleep(int(await self.config.delay()))