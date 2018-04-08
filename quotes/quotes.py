from pathlib import Path
from random import randint
from typing import Sequence

import discord
from discord.ext import commands

from redbot.core import RedContext, checks
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import warning, error

from cog_shared.odinair_libs.commands import fmt
from cog_shared.odinair_libs.formatting import tick, chunks, trim_to
from cog_shared.odinair_libs.menus import ReactMenu, PostMenuAction, prompt, ConfirmMenu, PaginateMenu

from quotes.quote import Quote, conf, _, QuoteRevision
from quotes.v2_import import import_v2_data


class Quotes:
    """Save and retrieve quotes"""

    __author__ = "odinair <odinair@odinair.xyz>"
    __version__ = "1.2.0"

    DELETE_WARNING = _(
        "\N{HEAVY EXCLAMATION MARK SYMBOL} Are you sure you want to delete this quote?\n\n"
        "Unless you have a time machine, this action **cannot be undone**."
    )

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = conf
        Quote.bot = self.bot

    @commands.group(name="quote", aliases=["quotes"], invoke_without_command=True)
    @commands.guild_only()
    async def quote(self, ctx: RedContext, quote: int = None):
        """Save and retrieve quotes

        If no quote is given, a random quote is retrieved instead.
        """
        if quote is None:
            quote = randint(1, len(await self.config.guild(ctx.guild).quotes()))
        quote = await Quote.get(ctx.guild, quote)
        if quote is None:
            await ctx.send(warning(_("That quote doesn't exist")))
            return
        await ctx.send(embed=quote.embed)

    @quote.command(hidden=True)
    @checks.is_owner()
    async def v2_import(self, ctx: RedContext, path: str):
        """Import quotes data from a Red v2 instance"""
        path = Path(path) / "data" / "quotes" / "quotes.json"
        if not path.is_file():
            await ctx.send(error(_("That file path doesn't seem to be valid")))
            return
        async with ctx.typing():
            await import_v2_data(config=self.config, path=path)
        await ctx.send(tick(_("Imported data successfully.")))

    @quote.command(name="add")
    async def _quote_add(self, ctx: RedContext, *, message: str):
        """Add a quote"""
        quote = await Quote.create(message, ctx.author, ctx.author)
        await ctx.send(tick(_("Quote added")), embed=quote.embed)

    @quote.command(name="message")
    async def _quote_message(self, ctx: RedContext, message: int):
        """Quote a message by it's ID

        The message specified must be in the same channel this command is executed in

        You can obtain a message's ID by enabling Developer Mode in your Appearance settings,
        and clicking Copy ID in the message's context menu
        """
        try:
            message = await ctx.get_message(message)
        except discord.NotFound:
            await ctx.send(warning(_("I couldn't find that message. (is it in a different channel?)")))
        except discord.Forbidden:
            await ctx.send(warning(_("I'm not allowed to retrieve that message")))
        else:
            quote = await Quote.create(message.content, ctx.author, message.author)
            await ctx.send(tick(_("Quote added")), embed=quote.embed)

    @quote.command(name="edit", aliases=["modify"])
    async def _quote_edit(self, ctx: RedContext, quote: int):
        """Interactive quote editor

        This requires you to be the quote creator, the attributed author
        or a guild moderator or administrator.
        """
        quote = await Quote.get(ctx.guild, quote)
        if quote is None:
            await ctx.send(warning(_("That quote doesn't exist")))
            return
        if not await quote.can_modify(ctx.author):
            await ctx.send(warning(_("You aren't authorized to modify that quote")))
            return

        embed = discord.Embed(title=_("Edit Quote"),
                              description=_("What action(s) would you like to take?\n\n"
                                            "\N{BUST IN SILHOUETTE} \N{EM DASH} Attribute quote\n"
                                            "\N{BUSTS IN SILHOUETTE} \N{EM DASH} Change quote creator\n"
                                            "\N{MEMO} \N{EM DASH} Edit content\n"
                                            "\N{WASTEBASKET} \N{EM DASH} Delete quote\n"
                                            "\N{CROSS MARK} \N{EM DASH} Cancel"))

        actions = {
            "attribute": "\N{BUST IN SILHOUETTE}",
            "creator": "\N{BUSTS IN SILHOUETTE}",
            "edit_content": "\N{MEMO}",
            "delete": "\N{WASTEBASKET}",
            "cancel": "\N{CROSS MARK}"
        }

        async def prompt_member():
            msg_ = await prompt(ctx, content=_("Who would you like to attribute this quote to?"), timeout=30.0,
                                delete_messages=True)
            if not msg_:
                return None
            try:
                member = await commands.MemberConverter().convert(ctx, msg_.content)
            except commands.BadArgument:
                await ctx.send(warning(_("Failed to convert `{}` into a member - try again?")
                                       .format(msg_.content)),
                               delete_after=30.0)
                return None
            else:
                return member

        menu = ReactMenu(ctx=ctx, actions=actions, embed=embed, post_action=PostMenuAction.DELETE)
        while True:
            async with menu as result:
                if result.timed_out or result == "cancel":
                    break

                elif result == "attribute":
                    attribute_to = await prompt_member()
                    if not attribute_to:
                        continue
                    quote.edited = True
                    quote.message_author = attribute_to
                    await quote.save()
                    await ctx.send(tick(_("Attributed quote to **{}**.").format(str(attribute_to))))

                elif result == "creator":
                    can_change_creator = any([
                        ctx.author == quote.creator,
                        await self.bot.is_mod(ctx.author),
                        await self.bot.is_owner(ctx.author)
                    ])
                    if not can_change_creator:
                        await ctx.send(error(_("You are not authorized to change the quote creator")),
                                       delete_after=30.0)
                        continue
                    attribute_to = await prompt_member()
                    if not attribute_to:
                        continue
                    quote.creator = attribute_to
                    await quote.save()
                    await ctx.send(tick(_("Changed quote creator to **{}**.").format(attribute_to)))

                elif result == "edit_content":
                    msg = await prompt(ctx, content=_("Please enter the new content for the quote"), timeout=120.0,
                                       delete_messages=True)
                    if not msg:
                        continue

                    quote.edited = True
                    quote.text = msg.content
                    await quote.save()
                    await ctx.send(tick(_("Modified quote contents successfully.")))

                elif result == "delete":
                    if await ConfirmMenu(ctx, content=self.DELETE_WARNING).prompt():
                        await quote.delete()
                        await ctx.send(tick(_("Quote successfully deleted.")), delete_after=30.0)
                        break

        try:
            await result.message.delete()
        except (discord.HTTPException, AttributeError):
            pass

    @quote.command(name="revisions", aliases=["history"])
    async def quote_history(self, ctx: RedContext, quote: int):
        """Retrieve the revision history for a quote"""
        quote = await Quote.get(ctx.guild, quote)
        if quote is None:
            await ctx.send(warning(_("That quote doesn't exist")))
            return
        if not quote.revisions:
            await ctx.send(warning(_("That quote has no recorded modifications")))
            return

        def convert(revs: Sequence[QuoteRevision], page_id: int, total_pages: int):
            embed = discord.Embed(colour=ctx.me.colour, title=_("Quote #{}").format(int(quote)))
            embed.set_footer(text=_("Page {}/{}").format(page_id + 1, total_pages))

            for rev in revs:
                embed.add_field(name=rev.title, value=str(rev), inline=False)

            return embed

        async with PaginateMenu(ctx, pages=list(chunks(quote.revisions, 3)), converter=convert, actions={}):
            pass

    @quote.command(name="list")
    async def quote_list(self, ctx: RedContext):
        """List the quotes in the current guild"""
        quotes = await Quote.all_quotes(ctx.guild)

        if not quotes:
            return await fmt(ctx, warning(_("This guild has no quotes! Use `{prefix}quote add` to add some!")))

        per_page = 8

        def convert(pg: Sequence[Quote], page_id, total_pages):
            embed = discord.Embed(colour=ctx.me.colour, title=_("Guild Quotes"),
                                  description=_("Displaying {} out of {} quotes").format(len(pg), len(quotes)))
            embed.set_footer(text=_("Page {}/{}").format(page_id + 1, total_pages))
            for q in pg:
                embed.add_field(name=_("Quote #{}").format(q.id), value=trim_to(q.text, 4000 // per_page), inline=False)
            return embed

        async with PaginateMenu(ctx, pages=list(chunks(quotes, per_page)), converter=convert, actions={}):
            pass

    @quote.command(name="attribute", aliases=["author"])
    async def _quote_attribute(self, ctx: RedContext, quote: int, *, author: discord.Member):
        """Attribute a quote to the specified user

        This requires you to be the quote creator, an administrator or moderator
        """
        quote = await Quote.get(ctx.guild, quote)
        if quote is None:
            await ctx.send(warning(_("That quote doesn't exist")))
            return
        if not await quote.can_modify(ctx.author):
            await ctx.send(warning(_("You aren't authorized to modify that quote")))
            return

        quote.edited = True
        quote.message_author = author
        await quote.save()
        await ctx.send(tick(_("Attributed quote #{} to **{}**.").format(int(quote), str(author))))

    @quote.command(name="remove", aliases=["rm", "delete"])
    async def _quote_remove(self, ctx: RedContext, quote: int):
        """Remove a quote by it's ID

        This requires you to either be the quote's creator, an administrator, moderator, or the quoted message author
        """
        quote = await Quote.get(ctx.guild, quote)
        if not quote:
            await ctx.send(warning(_("That quote doesn't exist")))
            return
        if not await quote.can_modify(ctx.author):
            await ctx.send(warning(_("You aren't authorized to remove that quote")))
            return

        if await ConfirmMenu(ctx, content=self.DELETE_WARNING).prompt():
            await quote.delete()
            await ctx.send(tick(_("Quote successfully deleted.")))
        else:
            await ctx.send(_("Ok then."))
