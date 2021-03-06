import asyncio
import importlib
import random
import re
import time
import inspect
from datetime import datetime

import discord
from discord.ext import commands

import server
import storage_manager_v2 as storage
from cogs import responses, sense, help
from util import global_util
import util.scheduler as scheduler
from util import command_util

"""
Breaking Changes:
 nvm
"""

"""
ToDo
----
fix all self references
"""

replace_chars = [('“', '"'), ('”', '"'), ('‘', "'"), ('’', "'")]  # need to put this in utils

# things for eggy
banner_channel = '607765058692448276'
icon_channel = '607765350167216134'
emote_channel = '607765472439697418'
vote_channel_switch = datetime.strptime('2019-8-19 00:00:00', '%Y-%m-%d %H:%M:%S').replace(tzinfo=None)


class DiscordBot(commands.Bot):
    def __init__(self, formatter=None, pm_help=False, **options):
        self.name = options.get('name', 'Default')
        self.local_servers = options.get('local_servers', [])
        self.token = options.get('token', '')
        self.desc = options.get('desc', 'No desc')
        self.prefix = options.get('prefix', '.')
        self.playing_message = options.get('playing_message', '{}help [command]'.format(self.prefix))
        self.admins = options.get('admins', [])
        self.bot_list = options.get('bot_list', [])

        super().__init__(self.prefix, formatter, self.desc, pm_help, **options)

        self.remove_command('help')
        self.music_loading = False  # for use in youtube-dl loading
        self.print_log = ""  # For use with prints

        self.debug_timer = None

        self._cogs = []  # hold cog instances

        self.help_all, self.help_mod = help.build_menus(self)

        async def check_birthdays():
            print('Checking birthdays for bot {}'.format(self.name))
            now = datetime.now()
            for s in self.local_servers:  # type: server.Server
                for birthday in s.birthdays:
                    if birthday == now:
                        await self.send_message(discord.Object(id=s.join_channel),
                                                content='Happy Birthday to {}!'.format(birthday.user.mention))
            print('Completed check.')

        self.check_birthdays = check_birthdays

        scheduler.register_hour_event(7, check_birthdays, delete=False)

        @self.event  # ---------------------- Main Message Entry ---------------------- #
        async def on_message(message):

            global_util.exit_timer = 0

            # bot should not read own or other bot messages
            if message.author == self.user or message.author.bot:
                return

            if message.channel.id == '498444135615692820':
                if message.attachments or message.embeds:
                    await self.add_reaction(message, '👍')
                    await self.add_reaction(message, '👎')

            if message.channel.id == emote_channel:
                if message.attachments or message.embeds:
                    await self.add_reaction(message, '👍🏿')
                    await self.add_reaction(message, '👎🏿')

            if message.channel.id == banner_channel:
                if message.attachments or message.embeds:
                    await self.add_reaction(message, '⬆')
                    await self.add_reaction(message, '⬇')

            if message.channel.id == icon_channel:
                if message.attachments or message.embeds:
                    await self.add_reaction(message, '⬆')
                    await self.add_reaction(message, '⬇')

            # cant have a command without content ¯\_(ツ)_/¯
            if not message.content:
                return

            if '@everyone' in message.content:  # update with perms later
                return

            if message.author.id == '340747290849312768':  # eggy
                if message.content.find('{}fren'.format(self.command_prefix)) == 0:
                    await self.send_message(message.channel, '{} is always my fren'.format(message.author.mention))
                    return

            if message.author.id == '238038532369678336':  # cake
                if message.content.find('{}fren'.format(self.command_prefix)) == 0:
                    cake_choice = ['{} is ***always*** by fren',
                                   '{} might ***always*** be my fren',
                                   '{} is never not my fren']
                    await self.send_message(message.channel,
                                            random.choice(cake_choice).format(message.author.mention))
                    return

            # last minute fix so .command list works
            # because why work more and do it right
            if message.content.find(self.command_prefix) == 0:
                message.content = re.sub(r'( list)\b', ' listall', message.content)  # type:str

            # |------------[ Direct Message Branching ]------------|
            if not message.server:

                message.content = self.char_swaps(message.content)

                await help.intercept_help(message, self)

                # treat all commands as first-word lowercase
                message.content = self.command_lowercase(message.content)

                await self.process_commands(message)

                if message.author.id in global_util.bypass_perm:
                    global_util.bypass_perm.remove(message.author.id)

                return

            # |------------[ Server Command Processing ]------------|

            await self.handle_manage_servers(message)  # update old server name and auto-add new

            in_server = self.get_server(server=message.server)
            high_perm = self.has_high_permissions(message.author, in_server)

            # |------------[ Special Admin Command Prefixes ]------------|
            await self.handle_tag_prefixes(message, perms=high_perm)

            # |------------[ Command Blocking ]------------|
            if await self.handle_blocked(message, in_server, perms=high_perm):  # return if this is blocked cmd
                return

            # |------------[ Content Operations ]------------|
            message.content = self.char_swaps(message.content)  # swap common chars like unicode quotes

            content_lower = message.content.lower()  # type: str

            # if message.server.id == '447183016998076418':
            #     if not high_perm:
            #         if any([x in content_lower for x in ['creeper', 'aww man', 'aw man', 'kreeper', 'creper', ]]):
            #             await asyncio.sleep(0.2)
            #             await self.delete_message(message)

            # |------------[ Command Interceptions / Alt Systems ]------------|
            if await help.intercept_help(message, self):  # intercept help
                return

            await responses.execute_responses(message, self, in_server, content_lower=content_lower)

            await self.find_reee(content_lower, message, in_server)

            await self.handle_default_reactions(content_lower, message)

            await sense.sense(self, message)

            if self.debug_timer:
                self.debug_timer = self.get_micros()

            # treat all commands as first-word lowercase
            message.content = self.command_lowercase(message.content)

            await self.process_commands(message)

            if self.debug_timer:
                self.debug_timer = self.get_micros() - self.debug_timer
                await self.send_message(message.channel,
                                        'processing took {} microseconds'.format(self.debug_timer))
                self.debug_timer = None

            if message.author.id in global_util.bypass_perm:
                global_util.bypass_perm.remove(message.author.id)

        @self.event
        async def on_ready():
            print('Logged in as')
            print(self.user.name)
            print(self.user.id)
            print('---------------')
            await self.change_presence(game=discord.Game(name=self.playing_message, type=0))
            self.id = self.user.id

        @self.event
        async def on_member_join(member):
            in_server = self.get_server(member.server)

            out_msg = in_server.join_message.replace('@u', member.mention)

            print('Join event on {}'.format(in_server.name))

            if in_server.join_channel:
                await self.send_message(discord.Object(id=in_server.join_channel), out_msg)
            else:
                await self.send_message(discord.Server(id=in_server.id), out_msg)

            if in_server.default_role:
                role = global_util.iterfind(member.server.roles, lambda x: x.id == in_server.default_role)
                if role:
                    try:
                        await self.add_roles(member, role)
                    except discord.Forbidden:
                        print('Role adding disallowed for server {}'.format(in_server.name))
                else:
                    in_server.default_role = None
                    storage.write_server_data(in_server)

        @self.event
        async def on_member_remove(member):
            in_server = self.get_server(member.server)

            if not in_server.leave_channel:
                return

            print('Leave event on {}'.format(in_server.name))

            if in_server.id == '313841769441787907':
                out_msg = '**{}** has left the server.'.format(member.name)

                em = discord.Embed(title=global_util.CHAR_ZWS, description=out_msg, color=random.randint(0, 0xffffff))
                em.set_image(url='https://cdn.discordapp.com/attachments/338528501005287426/593219534765293572/156150448871837104.png')
                await self.send_message(discord.Object(id=in_server.leave_channel), embed=em)
            else:
                out_msg = '**{}** has left the server. Goodbye! <:pinguwave:415782912278003713>'.format(member.name)

                await self.send_message(discord.Object(id=in_server.leave_channel), out_msg)

        @self.event
        async def on_message_delete(message):
            if message.author.id == self.user.id:
                return

            server = self.get_server(message.server)

            if not server.message_changes:
                return

            if self.has_high_permissions(message.author, server=server):
                if message.content:
                    if not message.content.startswith('-i'):
                        return
                    # else continue
                else:
                    return

            # cover pictures
            if not message.content:
                alt_content = None

                if message.embeds:
                    try:
                        alt_content = message.embeds[0]['url']
                    except:
                        pass
                elif message.attachments:
                    try:
                        alt_content = message.attachments[0]['url']
                    except:
                        pass

                if not alt_content:
                    em = discord.Embed(title='Deleted Message',
                                       color=0xff5000,
                                       description='**No content detected**')
                else:
                    em = discord.Embed(title='Deleted Message',
                                       color=0xff5000,
                                       description=global_util.CHAR_ZWS)
                    em.set_image(url=alt_content)

            else:
                em = discord.Embed(title='Deleted Message',
                                   color=0xff5000,
                                   description=message.content[:2000])

            em.set_author(name=message.author.name, icon_url=message.author.avatar_url)
            em.set_footer(text='Channel: {}'.format(message.channel.name))

            await self.send_message(discord.Object(id=server.message_changes), embed=em)

        @self.event
        async def on_message_edit(before, after):
            if before.author.id == self.user.id or after.author.id == self.user.id:
                return
            
            server = self.get_server(before.server)

            if not server.message_changes:
                return

            if self.has_high_permissions(before.author, server=server):
                if before.content:
                    if not before.content.startswith('-i'):
                        return
                    # else continue
                else:
                    return

            if before.content == after.content:
                return

            message_url = 'https://discordapp.com/channels/{}/{}/{}'.format(after.server.id,
                                                                            after.channel.id,
                                                                            after.id)

            # cover pictures
            if not before.content:
                alt_content = None

                if before.embeds:
                    try:
                        alt_content = before.embeds[0]['url']
                    except:
                        pass
                elif before.attachments:
                    try:
                        alt_content = before.attachments[0]['url']
                    except:
                        pass

                if not alt_content:
                    em = discord.Embed(title='Edited Message',
                                       color=0xffd000,
                                       description='[Link to new]({})\n\nOriginal: **No content detected**'
                                                   ''.format(message_url))
                else:
                    em = discord.Embed(title='Edited Message',
                                       color=0xffd000,
                                       description='[Link to new]({})'.format(message_url))
                    em.set_image(url=alt_content)
            else:
                em = discord.Embed(title='Edited Message',
                                   color=0xffd000,
                                   description='[Link to new]({})\n\nOriginal:\n{}'.format(message_url,
                                                                                           before.content[:2000]))

            em.set_author(name=before.author.name, icon_url=before.author.avatar_url)
            em.set_footer(text='Channel: {}'.format(before.channel.name))

            await self.send_message(discord.Object(id=server.message_changes), embed=em)

    def get_server(self, server: discord.Server = None, name: str = None, id: str = None) -> server.Server:
        test_id = None
        if server:
            test_id = server.id
        elif id:
            test_id = id
        if test_id:
            for s in self.local_servers:
                if s.id == test_id:
                    return s
        if name:
            for s in self.local_servers:
                if s.name == name:
                    return s

    async def handle_blocked(self, message, in_server, perms):
        # skip blocked and spam timed commands
        if len(message.content) > 0:
            if message.content[0] == self.prefix:
                if not perms:
                    root_cmd = message.content.split(' ')[0]
                    root_cmd = root_cmd.replace(self.command_prefix, '')

                    if len(in_server.block_list) > 0:
                        for com in in_server.block_list:  # type: BlockItem
                            if com.name == root_cmd:
                                if com.channel == 'all':
                                    m = await self.send_message(message.channel,
                                                                '`{}` is blocked in all channels'.format(root_cmd))
                                    global_util.schedule_delete(self, m, 3)
                                    return True
                                elif com.channel == message.channel.id:
                                    m = await self.send_message(message.channel,
                                                                '`{}` is blocked in this channel'.format(root_cmd))
                                    global_util.schedule_delete(self, m, 3)
                                    return True

                    if root_cmd in in_server.spam_timers:
                        if in_server.spam_timers[root_cmd] > 0:
                            return True
                        else:
                            in_server.spam_timers[root_cmd] = in_server.command_delay * 60
        return False

    async def find_reee(self, content, message, in_server):
        if not in_server.reee_message:
            return

        match = re.match(r'(reee+)\b', content, flags=re.IGNORECASE)
        if match:
            await self.send_message(message.channel, '{} {}'.format(message.author.mention, in_server.reee_message))

    async def handle_tag_prefixes(self, message, perms):
        if message.content.find('-p') == 0:
            if perms:
                message.content = message.content.replace('-p', '', 1)
                global_util.bypass_perm.append(message.author.id)

        if message.content.find('-d') == 0:
            await asyncio.sleep(0.2)
            await self.delete_message(message)
            message.content = message.content.replace('-d', '', 1)

        if message.content.find('-t') == 0 and perms:  # initiate timer!
            message.content = message.content.replace('-t', '', 1)
            self.debug_timer = True

    def check_admin(self, user: discord.User):
        return user.id in self.admins

    def has_high_permissions(self, user: discord.User, server: server.Server = None):  # check for mod OR admin
        if user.id in global_util.bypass_perm:
            return False

        if self.check_admin(user):
            return True

        if isinstance(user, discord.Member):
            server_perm = user.server_permissions  # type:discord.Permissions
            if server_perm.administrator:
                return True

        check_servers = []

        if server:
            check_servers.append(server)
        else:
            check_servers.extend(self.local_servers)

        for s in check_servers:
            if s.is_mod(user):
                return True

            if isinstance(user, discord.Member):
                for r in s.rolemods:
                    for sr in user.roles:
                        if sr.id == r:
                            return True
        return False

    async def handle_default_reactions(self, content, message):
        if content == 'f':
            await self.add_reaction(message, '🇫')

        if content == '<:owo:392462319617179659>':
            owo = discord.Emoji(name='owo', id='392462319617179659', server=message.server, require_colons=True)
            await self.add_reaction(message, owo)

        if '🅱' in content and len(message.content) < 2:
            await self.add_reaction(message, '🐝')

        if '🐝' in content and len(message.content) < 2:
            await self.add_reaction(message, '💛')
            await self.add_reaction(message, '🖤')
            await self.add_reaction(message, '🐝')

    async def handle_manage_servers(self, message):
        """Updates server info and adds new servers"""
        if not self.get_server(name=message.server.name):
            real_server = self.get_server(server=message.server)  # retrieve client copy by id
            if real_server:
                real_server.name = message.server.name  # handle server name changes
                storage.write_server_data(real_server)
            else:
                new_server = server.Server(name=message.server.name,
                                           id=message.server.id,
                                           mods=[message.server.owner.id])
                self.local_servers.append(new_server)
                storage.write_server(new_server)

    def load_cogs(self, extensions):
        for ext in extensions:
            m = importlib.import_module(ext)
            self._cogs.append(m.setup(self))

    def test_high_perm(self, func):
        """Decorator for generic server-based high permission test

        Passes found :class:`Server` object as first arg, expects a :class:`Context`
        from above

        """

        async def decorator(ctx, *args, **kwargs):
            if not ctx.message.server:
                await self.send_message(ctx.message.author,
                                        'Sorry, but this command is only accessible from a server')
                return

            in_server = self.get_server(server=ctx.message.server)
            if not self.has_high_permissions(ctx.message.author, in_server):
                await self.send_message(ctx.message.channel,
                                        'Sorry, but you don\'t have access to this command')
                return
            await func(in_server, ctx, *args, **kwargs)

        decorator.__name__ = func.__name__
        sig = inspect.signature(func)
        decorator.__signature__ = sig.replace(parameters=tuple(sig.parameters.values())[1:])  # from ctx onward
        return decorator

    def test_server(self, func):
        """Decorator for testing for server

        Passes found :class:`Server` object as second arg

        """

        async def decorator(ctx, *args, **kwargs):
            if not ctx.message.server:
                await self.send_message(ctx.message.author,
                                        'Sorry, but this command is only accessible from a server')
                return

            in_server = self.get_server(server=ctx.message.server)
            await func(in_server, ctx, *args, **kwargs)

        decorator.__name__ = func.__name__
        sig = inspect.signature(func)
        decorator.__signature__ = sig.replace(parameters=tuple(sig.parameters.values())[1:])  # from ctx onward
        return decorator

    def test_admin(self, func):
        """Decorator for testing for server

        Passes found :class:`Server` object as second arg

        """

        async def decorator(ctx, *args, **kwargs):
            if not ctx.message.server:
                if not self.check_admin(ctx.message.author):
                    return
                await self.send_message(ctx.message.channel,
                                        'Sorry, but this command is only accessible from a server')
                return

            in_server = self.get_server(server=ctx.message.server)
            await func(in_server, ctx, *args, **kwargs)

        decorator.__name__ = func.__name__
        sig = inspect.signature(func)
        decorator.__signature__ = sig.replace(parameters=tuple(sig.parameters.values())[1:])  # from ctx onward
        return decorator

    @staticmethod
    def extract_id(text: str):
        if not (text[0] == '<' and text[len(text) - 1] == '>'):
            return None
        begin = text.find('@') + 1
        if text[begin] == '!':
            begin += 1
        end = len(text) - 1
        try:
            num = text[begin:end]
            int(num)
            return num
        except ValueError:
            return None

    @staticmethod
    def get_micros():
        return int(round(time.time() * 1000000))

    @staticmethod
    def char_swaps(content: str) -> str:
        for swap in replace_chars:
            if swap[0] in content:
                content = content.replace(swap[0], swap[1])
        return content

    def command_lowercase(self, content: str) -> str:
        if content[0] == self.command_prefix:
            command = content[:content.find(' ')]
            if not command.islower():
                return command.lower() + content[content.find(' '):]
        return content
