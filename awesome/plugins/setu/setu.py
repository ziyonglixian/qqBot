import random
import re
import time
from datetime import datetime
from os import getcwd
from os.path import exists

import aiohttp
import nonebot
import pixivpy3
from aiocqhttp import MessageSegment
from loguru import logger

from awesome.adminControl import permission as perm
from awesome.plugins.util.helper_util import anime_reverse_search_response, set_group_permission
from config import SUPER_USER, SAUCE_API_KEY, PIXIV_REFRESH_TOKEN
from qq_bot_core import setu_control, user_control_module, admin_control, cangku_api

get_privilege = lambda x, y: user_control_module.get_user_privilege(x, y)
pixiv_api = pixivpy3.ByPassSniApi()
pixiv_api.require_appapi_hosts(hostname='public-api.secure.pixiv.net')
pixiv_api.set_accept_language('en_us')


@nonebot.on_command('色图数据', only_to_me=False)
async def get_setu_stat(session: nonebot.CommandSession):
    setu_stat = setu_control.get_setu_usage()
    await session.finish(f'色图功能共被使用了{setu_stat}次')


@nonebot.on_command('理智查询', only_to_me=False)
async def sanity_checker(session: nonebot.CommandSession):
    ctx = session.ctx.copy()
    if 'group_id' in ctx:
        id_num = ctx['group_id']
    else:
        id_num = ctx['user_id']

    if id_num in setu_control.get_sanity_dict():
        sanity = setu_control.get_sanity(id_num)
    else:
        sanity = setu_control.get_max_sanity()
        setu_control.set_sanity(id_num, setu_control.get_max_sanity())

    await session.send(f'本群剩余理智为：{sanity}')


@nonebot.on_command('理智补充', only_to_me=False)
async def sanity_refill(session: nonebot.CommandSession):
    ctx = session.ctx.copy()
    if not get_privilege(ctx['user_id'], perm.ADMIN):
        await session.finish('您没有权限补充理智')

    id_num = 0
    sanity_add = 0
    try:
        id_num = int(session.get('id_num', prompt='请输入要补充的ID'))
        sanity_add = int(session.get('sanity_add', prompt='那要补充多少理智呢？'))
    except ValueError:
        await session.finish('未找到能够补充的对象')

    try:
        setu_control.fill_sanity(id_num, sanity=sanity_add)
    except KeyError:
        await session.finish('未找到能够补充的对象')

    await session.finish('补充理智成功！')


@nonebot.on_command('设置色图禁用', only_to_me=False)
async def set_black_list_group(session: nonebot.CommandSession):
    ctx = session.ctx.copy()
    user_id = ctx['user_id']
    if not user_control_module.get_user_privilege(user_id, perm.ADMIN):
        await session.finish('无权限')

    message = session.current_arg
    if 'group_id' not in ctx:
        args = message.split()
        if len(args) != 2:
            await session.finish('参数错误，应为！设置色图禁用 群号 设置，或在本群内做出设置')

        group_id = args[0]
        if not str(group_id).isdigit():
            await session.finish('提供的参数非qq群号')

        message = args[1]

    else:
        group_id = ctx['group_id']

    setting = set_group_permission(message, group_id, 'banned')
    await session.finish(f'Done! {setting}')


@nonebot.on_command('色图', aliases='来张色图', only_to_me=False)
async def pixiv_send(session: nonebot.CommandSession):
    ctx = session.ctx.copy()
    message_id = ctx['message_id']

    group_id = ctx['group_id'] if 'group_id' in ctx else -1
    allow_r18 = admin_control.get_group_permission(group_id, 'R18')
    user_id = ctx['user_id']

    if 'group_id' in ctx and not get_privilege(user_id, perm.OWNER):
        if admin_control.get_group_permission(group_id, 'banned'):
            await session.finish('管理员已设置禁止该群接收色图。如果确认这是错误的话，请联系bot制作者')

    sanity = -1
    monitored = False
    multiplier = 1
    do_multiply = False

    if group_id in setu_control.get_sanity_dict():
        sanity = setu_control.get_sanity(group_id)

    elif 'group_id' not in ctx and not get_privilege(user_id, perm.WHITELIST):
        await session.finish('我主人还没有添加你到信任名单哦。请找BOT制作者要私聊使用权限~')

    else:
        sanity = setu_control.get_max_sanity()
        setu_control.set_sanity(group_id=group_id, sanity=setu_control.get_max_sanity())

    if sanity <= 0:
        if group_id not in setu_control.remind_dict or not setu_control.remind_dict[group_id]:
            setu_control.set_remid_dict(group_id, True)
            await session.finish(
                '差不多得了嗷'
            )

    if not admin_control.get_if_authed():
        pixiv_api.set_auth(
            access_token=admin_control.get_access_token(),
            refresh_token='iL51azZw7BWWJmGysAurE3qfOsOhGW-xOZP41FPhG-s'
        )
        admin_control.set_if_authed(True)

    is_exempt = admin_control.get_group_permission(group_id, 'exempt') if group_id != -1 else False

    key_word = str(session.get('key_word', prompt='请输入一个关键字进行查询')).lower()

    if key_word in setu_control.get_bad_word_dict():
        multiplier = setu_control.get_bad_word_dict()[key_word]
        do_multiply = True
        if multiplier > 0:
            if multiplier * 2 > 400:
                setu_control.set_user_data(user_id, 'ban_count')
                if setu_control.get_user_data_by_tag(user_id, 'ban_count') >= 3:
                    user_control_module.set_user_privilege(user_id, 'BANNED', True)
                    await session.send(f'用户{user_id}已被封停机器人使用权限')
                    bot = nonebot.get_bot()
                    await bot.send_private_msg(
                        user_id=SUPER_USER,
                        message=f'User {user_id} has been banned for triggering prtection. Keyword = {key_word}'
                    )

                else:
                    await session.send('本次黑名单搜索已触发群保护机制，下次触发将会导致所有功能禁用。')
                    bot = nonebot.get_bot()
                    await bot.send_private_msg(
                        user_id=SUPER_USER,
                        message=f'User {user_id} triggered protection mechanism. Keyword = {key_word}'
                    )

                return
        else:
            await session.send(
                f'该查询关键词在白名单中，支援合约已开启：本次色图搜索将{abs(multiplier)}倍补充理智'
            )

    if key_word in setu_control.get_monitored_keywords():
        await session.send('该关键词在主人的监控下，本次搜索不消耗理智，且会转发主人一份√')
        monitored = True
        if 'group_id' in ctx:
            setu_control.set_user_data(user_id, 'hit_xp')
            setu_control.set_xp_data(key_word)

    elif '色图' in key_word:
        await session.finish(
            MessageSegment.image(
                f'file:///{getcwd()}/data/dl/others/QQ图片20191013212223.jpg'
            )
        )

    elif '屑bot' in key_word:
        await session.finish('你屑你🐴呢')

    json_result = {}

    try:
        if '最新' in key_word:
            json_result = pixiv_api.illust_ranking('week')
        else:
            json_result = pixiv_api.search_illust(
                word=key_word,
                sort="popular_desc"
            )

    except pixivpy3.PixivError:
        await session.finish('pixiv连接出错了！')

    except Exception as err:
        logger.warning(f'pixiv search error: {err}')
        await session.send(f'发现未知错误')

    # 看一下access token是否过期
    if 'error' in json_result:
        admin_control.set_if_authed(False)
        try:
            pixiv_api.auth(refresh_token=PIXIV_REFRESH_TOKEN)
            admin_control.set_if_authed(True)

        except pixivpy3.PixivError as err:
            print(err)
            return

    if '{user=' in key_word:
        return_result = _get_image_data_from_username(key_word)
        if isinstance(return_result, str):
            await session.finish(return_result)

    else:
        json_result = pixiv_api.search_illust(word=key_word, sort="popular_desc")

    if not json_result.illusts or len(json_result.illusts) < 4:
        logger.warning(f"未找到图片, keyword = {key_word}")
        await session.send(f"{key_word}无搜索结果或图片过少……")
        return

    setu_control.track_keyword(key_word)
    illust = random.choice(json_result.illusts)
    is_r18 = illust.sanity_level == 6
    if not allow_r18:
        # Try 10 times to find a SFW image.
        for i in range(10):
            illust = random.choice(json_result.illusts)
            is_r18 = illust.sanity_level == 6
            if not is_r18:
                break

    if not monitored:
        if is_r18:
            setu_control.drain_sanity(
                group_id=group_id,
                sanity=3 if not do_multiply else 3 * multiplier
            )
        else:
            setu_control.drain_sanity(
                group_id=group_id,
                sanity=1 if not do_multiply else 1 * multiplier
            )

    start_time = time.time()
    path = await download_image(illust)
    try:
        nickname = ctx['sender']['nickname']
    except TypeError:
        nickname = 'null'

    bot = nonebot.get_bot()
    if not is_r18:
        try:
            await session.send(
                f'[CQ:reply,id={message_id}]'
                f'Pixiv ID: {illust.id}\n'
                f'查询关键词：{key_word}\n'
                f'画师：{illust["user"]["name"]}\n' +
                f'{MessageSegment.image(f"file:///{path}")}\n' +
                f'Download Time: {(time.time() - start_time):.2f}s'
            )

            nonebot.logger.info("sent image on path: " + path)

        except Exception as e:
            nonebot.logger.info('Something went wrong %s' % e)
            await session.send('悲，屑TX不收我图。')
            return

    elif is_r18 and (group_id == -1 or allow_r18):
        await session.send(
            f'[CQ:reply,id={message_id}]'
            f'芜湖~好图来了ww\n'
            f'Pixiv ID: {illust.id}\n'
            f'关键词：{key_word}\n'
            f'画师：{illust["user"]["name"]}\n'
            f'[CQ:image,file=file:///{path}{",type=flash" if not is_exempt else ""}]' +
            f'Download Time: {(time.time() - start_time):.2f}s'
        )

    else:
        await session.send(
            f'[CQ:reply,id={message_id}]'
            '由于图片不太健全，所以只能发给主人了。'
        )
        await bot.send_private_msg(
            user_id=SUPER_USER,
            message=f"图片来自：{nickname}\n"
                    f"来自群：{group_id}\n"
                    f"查询关键词：{key_word}\n" +
                    f'Pixiv ID: {illust.id}\n' +
                    f'{MessageSegment.image(f"file:///{path}")}\n' +
                    f'Download Time: {(time.time() - start_time):.2f}s'
        )

    if 'group_id' in ctx:
        setu_control.set_usage(group_id, 'setu')

    setu_control.set_user_data(user_id, 'setu')

    if monitored and not get_privilege(user_id, perm.OWNER):
        await bot.send_private_msg(
            user_id=SUPER_USER,
            message=f'图片来自：{nickname}\n'
                    f'查询关键词:{key_word}\n'
                    f'Pixiv ID: {illust.id}\n'
                    '关键字在监控中' + f'[CQ:image,file=file:///{path}]'
        )


def _get_image_data_from_username(key_word: str):
    key_word = re.findall(r'{user=(.*?)}', key_word)
    if key_word:
        key_word = key_word[0]
    else:
        return '未找到该用户。'

    json_user = pixiv_api.search_user(word=key_word, sort="popular_desc")
    if json_user.user_previews:
        user_id = json_user.user_previews[0].user.id
        json_result = pixiv_api.user_illusts(user_id)
        return json_result
    else:
        return f"{key_word}无搜索结果或图片过少……"


async def download_image(illust):
    if illust['meta_single_page']:
        if 'original_image_url' in illust['meta_single_page']:
            image_url = illust.meta_single_page['original_image_url']
        else:
            image_url = illust.image_urls['medium']
    else:
        if 'meta_pages' in illust:
            image_url_list = illust.meta_pages
            illust = random.choice(image_url_list)

        image_url = illust.image_urls['medium']

    nonebot.logger.info(f"{illust.title}: {image_url}, {illust.id}")
    image_file_name = image_url.split('/')[-1].replace('_', '')
    path = f'{getcwd()}/data/pixivPic/' + image_file_name

    if not exists(path):
        try:
            async with aiohttp.ClientSession(headers={'Referer': 'https://app-api.pixiv.net/'}) as session:
                async with session.get(image_url) as response:
                    with open(path, 'wb') as out_file:
                        while True:
                            chunk = await response.content.read(1024 ** 4)
                            if not chunk:
                                break
                            out_file.write(chunk)

        except Exception as err:
            nonebot.logger.info(f'Download image error: {err}')

    nonebot.logger.info("PATH = " + path)
    return path


@nonebot.on_command('搜图', only_to_me=False)
async def reverse_image_search(session: nonebot.CommandSession):
    ctx = session.ctx.copy()
    args = ctx['raw_message'].split()
    if len(args) != 2:
        await session.finish('¿')

    bot = nonebot.get_bot()
    has_image = re.findall(r'.*?\[CQ:image,file=(.*?\.image)]', args[1])
    if has_image:
        image = await bot.get_image(file=has_image[0])
        url = image['url']
        nonebot.logger.info(f'URL extracted: {url}')
        try:
            response_data = await sauce_helper(url)
            if not response_data:
                await session.finish('阿这~图片辨别率低，请换一张图试试！')
                return

            response = anime_reverse_search_response(response_data)
            await session.send(response)
            return

        except Exception as err:
            await session.send(f'啊这~出错了！报错信息已发送主人debug~')
            await bot.send_private_msg(
                user_id=SUPER_USER,
                message=f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] '
                        f'搜图功能出错：\n'
                        f'Error：{err}\n'
                        f'出错URL：{url}'
            )


async def sauce_helper(url):
    params = {
        'output_type': 2,
        'api_key': SAUCE_API_KEY,
        'testmode': 0,
        'db': 999,
        'numres': 6,
        'url': url
    }

    response = {}

    async with aiohttp.ClientSession() as client:
        async with client.get(
                'https://saucenao.com/search.php',
                params=params
        ) as page:
            json_data = await page.json()

        if json_data['results']:
            json_data = json_data['results'][0]
            nonebot.logger.info(f'Json data: \n'
                                f'{json_data}')
            response = ''
            if json_data:
                simlarity = json_data['header']['similarity'] + '%'
                thumbnail = json_data['header']['thumbnail']
                async with client.get(thumbnail) as page:
                    file_name = thumbnail.split('/')[-1]
                    file_name = re.sub(r'\?auth=.*?$', '', file_name)
                    if len(file_name) > 10:
                        file_name = f'{int(time.time())}.jpg'

                    path = f'{getcwd()}/data/pixivPic/{file_name}'
                    if not exists(path):
                        try:
                            with open(path, 'wb') as file:
                                while True:
                                    chunk = await page.content.read(1024 ** 2)
                                    if not chunk:
                                        break

                                    file.write(chunk)
                        except IOError:
                            return {}

                image_content = MessageSegment.image(f'file:///{path}')

                json_data = json_data['data']
                if 'ext_urls' not in json_data:
                    return {}

                pixiv_id = 'Undefined'
                title = 'Undefined'
                author = 'Undefined'

                ext_url = json_data['ext_urls'][0]
                if 'title' not in json_data:
                    if 'creator' in json_data:
                        author = json_data['creator']
                    elif 'author' in json_data:
                        author = json_data['author']
                    else:
                        if 'source' and 'est_time' in json_data:
                            year = json_data['year']
                            part = json_data['part']
                            est_time = json_data['est_time']

                            return {
                                'simlarity': simlarity,
                                'year': year,
                                'part': part,
                                'est_time': est_time,
                                'source': json_data['source'],
                                'thumbnail': image_content
                            }

                        if 'artist' not in json_data:
                            return {}

                        author = json_data['artist']

                elif 'title' in json_data:
                    title = json_data['title']
                    if 'author_name' in json_data:
                        author = json_data['author_name']
                    elif 'member_name' in json_data:
                        author = json_data['member_name']
                        if 'pixiv_id' in json_data:
                            pixiv_id = json_data['pixiv_id']

                response = {
                    'data': image_content,
                    'simlarity': simlarity,
                    'title': title,
                    'author': author,
                    'pixiv_id': pixiv_id,
                    'ext_url': ext_url,
                    'thumbnail': thumbnail
                }

                """
                response += f'{image_content}' \
                            f'图片相似度：{simlarity}\n' \
                            f'图片标题：{title}\n' \
                            f'图片画师：{author}\n' \
                            f'Pixiv ID：{pixiv_id}\n' \
                            f'直链：{ext_url}'
                """

    return response


@nonebot.on_command('仓库搜索', only_to_me=False)
async def cangku_search(session: nonebot.CommandSession):
    key_word = str(session.get('key_word', prompt='请输入关键字进行查询')).lower()
    ctx = session.ctx.copy()
    if 'group_id' not in ctx:
        allow_r18 = True
    else:
        group_id = ctx['group_id']
        allow_r18 = admin_control.get_group_permission(group_id, 'R18')

    user_id = ctx['user_id']
    user_id = str(user_id)

    search_result = cangku_api.get_search_string(
        key_word,
        user_id=user_id,
        is_r18=allow_r18
    )
    index = session.get(
        'index_name',
        prompt=search_result + '\n'
                               '请输入序号进行查询~'
    )
    search_by_index = cangku_api.get_info_by_index(user_id, index)
    dissect_to_string = cangku_api.anaylze_dissected_data(search_by_index)
    await session.finish(dissect_to_string)


@pixiv_send.args_parser
@cangku_search.args_parser
async def _(session: nonebot.CommandSession):
    stripped_arg = session.current_arg_text
    if session.is_first_run:
        if stripped_arg:
            session.state['key_word'] = stripped_arg
        return

    if not stripped_arg:
        session.pause('要查询的关键词不能为空')

    session.state[session.current_key] = stripped_arg


@set_black_list_group.args_parser
async def _set_group_property(session: nonebot.CommandSession):
    stripped_arg = session.current_arg_text
    if session.is_first_run:
        if stripped_arg:
            session.state['group_id'] = stripped_arg
        return

    if not stripped_arg:
        ctx = session.ctx.copy()
        if 'group_id' not in ctx:
            session.pause('qq组号不能为空')
        else:
            session.state['group_id'] = ctx['group_id']

    session.state[session.current_key] = stripped_arg
