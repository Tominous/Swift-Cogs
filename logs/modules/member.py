from datetime import datetime

import discord

from redbot.core.utils.chat_formatting import inline

from logs.core import Module, LogEntry, _

from cog_shared.odinair_libs import td_format


class MemberModule(Module):
    name = "member"
    friendly_name = _("Member")
    description = _("Member joining, leaving, and update logging")
    settings = {
        "join": _("Member joining"),
        "leave": _("Member leaving"),
        "update": {
            "name": _("Member username changes"),
            "discriminator": _("Member discriminator changes"),
            "nickname": _("Member nickname changes"),
            "roles": _("Member role changes")
        }
    }

    async def join(self, member: discord.Member):
        return (
            LogEntry(self, colour=discord.Color.green(), require_fields=False,
                     description=_("Member {} joined\n\nAccount was created {}").format(
                         member.mention, td_format(member.created_at - datetime.utcnow(), append_str=True)))
            .set_author(name=_("Member Joined"), icon_url=self.icon_uri(member))
            .set_footer(text=_("Member ID: {}").format(member.id))
        ) if await self.is_opt_enabled("join") else None

    async def leave(self, member: discord.Member):
        return (
            LogEntry(self, colour=discord.Color.red(), require_fields=False,
                     description=_("Member {} left").format(member.mention))
            .set_author(name=_("Member Left"), icon_url=self.icon_uri(member))
            .set_footer(text=_("Member ID: {}").format(member.id))
        ) if await self.is_opt_enabled("leave") else None

    async def update(self, before: discord.Member, after: discord.Member):
        embed = LogEntry(self, colour=discord.Color.blurple(), description=_("Member: {}").format(after.mention))
        embed.set_author(name=_("Member Updated"), icon_url=self.icon_uri(after))
        embed.set_footer(text=_("Member ID: {}").format(after.id))

        await embed.add_if_changed(name=_("Username"), before=before.name, after=after.name,
                                   config_opt=('update', 'name'))

        await embed.add_if_changed(name=_("Discriminator"), before=before.discriminator, after=after.discriminator,
                                   config_opt=('update', 'discriminator'))

        await embed.add_if_changed(name=_("Nickname"), before=before.nick, after=after.nick,
                                   config_opt=('update', 'nickname'), converter=lambda x: x or inline(_("None")))

        await embed.add_if_changed(name=_("Roles"), diff=True, config_opt=('update', 'roles'),
                                   before=[str(x) for x in before.roles if not x.is_default()],
                                   after=[str(x) for x in after.roles if not x.is_default()])

        return embed
