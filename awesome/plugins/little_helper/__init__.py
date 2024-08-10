import time

from aiocache import cached
from aiocache.serializers import PickleSerializer
from nonebot import on_command, get_bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from nonebot.internal.matcher import Matcher
from nonebot.log import logger
from nonebot.params import CommandArg

from Services.util.common_util import HttpxHelperClient, markdown_to_image
from Services.util.ctx_utility import get_nickname, get_group_id
from awesome.Constants.function_key import HHSH_FUNCTION
from awesome.Constants.plugins_command_constants import PROMPT_FOR_KEYWORD
from awesome.adminControl import setu_function_control

markdown_cmd = on_command('markdown', aliases={'md'})


@markdown_cmd.handle()
async def markdown_text_to_image(_event: GroupMessageEvent, matcher: Matcher, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        return

    result, success = markdown_to_image(arg)
    if success:
        await matcher.finish(MessageSegment.image(result))

    await matcher.finish(result)


search_deprecated_cmd = on_command('搜索')


@search_deprecated_cmd.handle()
async def search_command(_event: GroupMessageEvent, matcher: Matcher):
    await matcher.finish('改功能已被废弃，请使用！灵夜。')


global_help_cmd = on_command('help')


@global_help_cmd.handle()
async def send_help(_event: GroupMessageEvent, matcher: Matcher):
    await matcher.send(
        '请移步\n'
        'https://github.com/remiliacn/Lingye-Bot/blob/master/README.md\n'
        '如果有新功能想要添加，请提交issue!'
    )


reverse_cq_cmd = on_command('反码')


@reverse_cq_cmd.handle()
async def reverse_code(event: GroupMessageEvent, matcher: Matcher):
    key_word = event.raw_text.strip()
    message_list = key_word.split()
    if len(message_list) == 1:
        await matcher.send('没有可反码内容！')
        return

    key_word = message_list[1]
    if_group = False

    id_num = get_group_id(event)

    bot = get_bot()

    if if_group:
        await bot.send_msg(message_type='group', group_id=id_num, message=key_word, auto_escape=True)
    else:
        await bot.send_msg(message_type='private', user_id=id_num, message=key_word, auto_escape=True)


hhsh_cmd = on_command('好好说话')


@hhsh_cmd.handle()
async def can_you_be_fucking_normal(event: GroupMessageEvent, matcher: Matcher, args: Message = CommandArg()):
    if not (key_word := args.extract_plain_text().strip()):
        await matcher.finish(PROMPT_FOR_KEYWORD)

    start_time = time.time()
    nickname = get_nickname(event)
    try:
        await matcher.send(await hhsh(key_word) + '\n本次查询耗时： %.2fs' % (time.time() - start_time))
        setu_function_control.set_user_data(event.get_user_id(), HHSH_FUNCTION, nickname)

    except Exception as e:
        logger.debug('Something went wrong %s' % e)


@cached(ttl=86400, serializer=PickleSerializer())
async def hhsh(entry: str) -> str:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/81.0.4044.138 Safari/537.36',
        'Origin': 'https://lab.magiconch.com',
        'referer': 'https://lab.magiconch.com/nbnhhsh/'
    }

    guess_url = 'https://lab.magiconch.com/api/nbnhhsh/guess'

    try:
        client = HttpxHelperClient()
        page = await client.post(guess_url, json={"text": entry}, headers=headers)
        json_data = page.json()

    except Exception as e:
        print(e)
        return ''

    result = ''
    if json_data:
        result = '这个缩写可能的意味有：\n'
        try:
            for element in json_data:
                result += f'当缩写为{element["name"]}时，其意味可以是：\n{"，".join(element["trans"])}\n'

        except KeyError:
            try:
                return result + json_data[0]['inputting'][0]
            except KeyError:
                return '这……我也不懂啊草，能不能好好说话（'
        except Exception as err:
            logger.info(f'hhsh err: {err}')
            return ''

    return result.strip()
