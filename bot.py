#!/usr/bin/env python3
"""
Telegram Bot for VPS Exit Node Switching
带详细日志记录功能 - 增加 /check 批量检测功能
"""

import os
import time
import json
import logging
import traceback
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import paramiko
import re

# ==================== 日志配置 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== 配置信息 ====================
BOT_TOKEN = '你自己的'
VPS_HOST = '你自己的'
VPS_PORT = '你自己的'
VPS_USER = '你自己的'
VPS_PASSWORD = '你自己的'

# 授权用户ID列表
AUTHORIZED_USERS = [你自己的大号, 你自己的小号]

logger.info(f"配置加载完成 - VPS: {VPS_USER}@{VPS_HOST}:{VPS_PORT}")


# ==================== SSH 工具类 ====================
class SSHClient:
    def __init__(self, host, port, username, password):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        logger.info(f"初始化 SSH 客户端: {username}@{host}:{port}")

    def execute_command(self, command, timeout=30):
        """执行SSH命令并返回输出（用于简单命令）"""
        logger.info(f"执行 SSH 命令: {command}")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            logger.debug(f"正在连接到 {self.host}...")
            client.connect(self.host, port=self.port, username=self.username,
                           password=self.password, timeout=timeout)
            logger.debug("SSH 连接成功")

            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')

            logger.info(f"命令执行完成，输出长度: {len(output)}, 错误长度: {len(error)}")
            if error:
                logger.warning(f"命令错误输出: {error[:200]}")

            return output, error
        except Exception as e:
            logger.error(f"SSH 命令执行失败: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        finally:
            client.close()
            logger.debug("SSH 连接已关闭")

    def get_menu_output(self, timeout=10):
        """获取交互式菜单输出"""
        logger.info("获取菜单输出")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            logger.debug(f"正在连接到 {self.host}...")
            client.connect(self.host, port=self.port, username=self.username,
                           password=self.password, timeout=timeout)
            logger.debug("SSH 连接成功")

            channel = client.invoke_shell()
            channel.settimeout(5)
            logger.debug("Shell 会话已创建")

            # 清空初始输出
            time.sleep(0.5)
            if channel.recv_ready():
                channel.recv(4096)

            # 发送命令
            logger.debug("发送命令: /etc/uzmaru/out.sh")
            channel.send('/etc/uzmaru/out.sh\n')
            time.sleep(2)

            # 读取输出
            output = ''
            max_wait = 5
            start_time = time.time()

            while time.time() - start_time < max_wait:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode('utf-8', errors='ignore')
                    output += chunk
                    time.sleep(0.1)
                else:
                    if output:  # 如果已经有输出，等待一小段时间后退出
                        time.sleep(0.5)
                        if channel.recv_ready():
                            output += channel.recv(4096).decode('utf-8', errors='ignore')
                        break

            logger.debug(f"接收到输出: {len(output)} 字节")

            # 发送退出命令（0 或 Ctrl+C）
            channel.send('0\n')
            time.sleep(0.5)
            channel.close()

            logger.info("菜单输出获取完成")
            return output, None

        except Exception as e:
            logger.error(f"获取菜单输出失败: {str(e)}")
            logger.error(traceback.format_exc())
            return None, str(e)
        finally:
            client.close()
            logger.debug("SSH 连接已关闭")

    def execute_interactive_command(self, selections, timeout=30):
        """执行交互式命令（/etc/uzmaru/out.sh + 选择）"""
        logger.info(f"执行交互式命令，选项: {selections}")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            logger.debug(f"正在连接到 {self.host}...")
            client.connect(self.host, port=self.port, username=self.username,
                           password=self.password, timeout=timeout)
            logger.debug("SSH 连接成功")

            channel = client.invoke_shell()
            channel.settimeout(10)  # 增加超时时间
            logger.debug("Shell 会话已创建")

            # 清空初始输出
            time.sleep(0.5)
            if channel.recv_ready():
                channel.recv(4096)

            # 发送命令
            logger.debug("发送命令: /etc/uzmaru/out.sh")
            channel.send('/etc/uzmaru/out.sh\n')
            time.sleep(2)

            output = ''
            while channel.recv_ready():
                chunk = channel.recv(4096).decode('utf-8', errors='ignore')
                output += chunk
                time.sleep(0.1)
            logger.debug(f"接收到初始输出: {len(output)} 字节")

            # 发送选择
            for selection in selections:
                logger.debug(f"发送选择: {selection}")
                channel.send(f'{selection}\n')
                time.sleep(2)  # 等待切换生效

            # 读取最终输出
            final_output = ''
            max_wait = 5
            start_time = time.time()

            while time.time() - start_time < max_wait:
                if channel.recv_ready():
                    chunk = channel.recv(4096).decode('utf-8', errors='ignore')
                    final_output += chunk
                    time.sleep(0.1)
                else:
                    time.sleep(0.5)
                    if not channel.recv_ready():
                        break

            logger.debug(f"接收到最终输出: {len(final_output)} 字节")

            # 确保退出菜单 (发送 0)
            channel.send('0\n')
            time.sleep(0.5)
            channel.close()
            
            logger.info("交互式命令执行完成")
            return output, final_output
        except Exception as e:
            logger.error(f"交互式命令执行失败: {str(e)}")
            logger.error(traceback.format_exc())
            raise
        finally:
            client.close()
            logger.debug("SSH 连接已关闭")


# ==================== 工具函数 ====================
def parse_nm_output(output):
    """解析 /etc/uzmaru/out.sh 输出，提取国家/地区列表"""
    logger.info("开始解析输出")
    lines = output.strip().split('\n')
    options = []

    for line in lines:
        # 匹配格式: "1. 香港机房出口" 或 "101. 美国 AS6079"
        match = re.match(r'^\s*(\d+)\.\s+(.+)$', line.strip())
        if match:
            number = match.group(1)
            region = match.group(2).strip()
            # 过滤掉标题和分隔线
            if not any(keyword in region for keyword in ['===', '以下为', '不 保 证', '更新出口', '退出']):
                options.append({'number': number, 'region': region})
                logger.debug(f"解析到选项: {number}. {region}")

    logger.info(f"共解析到 {len(options)} 个选项")
    return options


def get_flag_emoji(country_code):
    """根据国家代码返回国旗 emoji"""
    if not country_code or len(country_code) != 2:
        return "🌍"

    country_code = country_code.upper()
    flag = ''.join(chr(127397 + ord(letter)) for letter in country_code)
    return flag


def escape_markdown(text):
    """转义 Markdown V2 特殊字符"""
    if not text:
        return '未知'

    text = str(text)
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


def format_ip_info(data):
    """格式化 IP 信息"""
    logger.info("格式化 IP 信息")

    ip = data.get('ip') or data.get('query') or '未知'
    country = data.get('country') or data.get('country_name') or '未知'
    region = data.get('region') or data.get('regionName') or data.get('region_name') or '未知'
    city = data.get('city') or '未知'
    isp = data.get('org') or data.get('isp') or data.get('as') or '未知'
    timezone = data.get('timezone') or '未知'

    # 转义所有文本
    ip = escape_markdown(ip)
    country = escape_markdown(country)
    region = escape_markdown(region)
    city = escape_markdown(city)
    isp = escape_markdown(isp)
    timezone = escape_markdown(timezone)

    country_code = data.get('country_code') or data.get('countryCode') or ''
    flag = get_flag_emoji(country_code)

    message = f"""
🌐 *当前出口 IP 信息*

{flag} *国家/地区:* {country}
📍 *省份/州:* {region}
🏙️ *城市:* {city}
🌍 *IP 地址:* {ip}
🏢 *ISP/组织:* {isp}
🕐 *时区:* {timezone}
"""
    return message


async def get_ip_info_from_vps():
    """从 VPS 获取当前出口 IP 信息"""
    logger.info("开始查询 VPS 出口 IP 信息")

    try:
        ssh = SSHClient(VPS_HOST, VPS_PORT, VPS_USER, VPS_PASSWORD)

        commands = [
            'curl -s --connect-timeout 5 https://ipapi.co/json/',
            'curl -s --connect-timeout 5 http://ip-api.com/json/',
            'curl -s --connect-timeout 5 https://ipinfo.io/json',
        ]

        for cmd in commands:
            try:
                logger.debug(f"尝试命令: {cmd}")
                output, error = ssh.execute_command(cmd, timeout=10)
                if output and not error:
                    data = json.loads(output)
                    logger.info(f"成功获取 IP 信息: {data.get('ip', 'unknown')}")
                    return data, None
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 解析失败: {str(e)}")
                continue
            except Exception as e:
                logger.warning(f"命令失败: {str(e)}")
                continue

        logger.error("所有 IP 查询服务都失败了")
        return None, "所有 IP 查询服务都失败了"
    except Exception as e:
        logger.error(f"获取 IP 信息时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return None, str(e)


def is_authorized(user_id):
    """检查用户是否有权限"""
    if not AUTHORIZED_USERS:
        logger.debug(f"未设置授权用户列表，允许用户 {user_id}")
        return True

    authorized = user_id in AUTHORIZED_USERS
    logger.info(f"用户 {user_id} 授权检查: {'通过' if authorized else '拒绝'}")
    return authorized


# ==================== 新增：节点检测逻辑 ====================

async def test_node_connectivity(ssh, node_number, node_name):
    """
    测试单个节点的连通性
    返回: (成功状态, IP地址/错误信息)
    """
    try:
        logger.info(f"开始测试节点: {node_number} - {node_name}")
        
        # 1. 切换到目标节点 (发送选择，然后发送 0 退出菜单确保 shell 干净)
        # 注意：execute_interactive_command 最后会发送 '0' 退出，这里 selections 只需要传节点ID
        # 但我们在 SSHClient 中修改了逻辑，确保最后退出。
        # 实际上 execute_interactive_command(selections) 会依次发送 selections 里的内容。
        # 切换节点逻辑：进入菜单 -> 输入ID -> (脚本自动切换或返回) -> 输入0退出
        
        # 调用交互式命令切换节点
        # 这里我们传入 [node_number, '0']，表示先选节点，再退出的意思（取决于脚本逻辑，通常是选了就切，然后我们要确保退出菜单）
        # 实际上你的脚本是选了就切，切完可能还在菜单里，所以要补一个0
        ssh.execute_interactive_command([str(node_number), '0'])
        
        # 给一点时间让路由生效
        time.sleep(2)
        
        # 2. 测试连通性 (curl ip.sb)
        test_cmd = "curl -s --connect-timeout 5 ip.sb"
        output, error = ssh.execute_command(test_cmd, timeout=10)
        
        ip = output.strip()
        
        # 简单校验是否是IP格式 (IPv4)
        ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if re.match(ipv4_pattern, ip):
            logger.info(f"节点 {node_number} 测试成功，IP: {ip}")
            return True, ip
        else:
            logger.warning(f"节点 {node_number} 测试失败，输出: {output}, 错误: {error}")
            return False, "连接超时或无效响应"

    except Exception as e:
        logger.error(f"测试节点 {node_number} 发生异常: {str(e)}")
        return False, str(e)

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /check 命令 - 批量检测出口可用性"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"用户 {username} (ID: {user_id}) 执行 /check 命令")

    if not is_authorized(user_id):
        await update.message.reply_text("❌ 你没有权限使用此机器人。")
        return

    status_msg = await update.message.reply_text("🔄 正在初始化检测环境，请稍候...")

    try:
        ssh = SSHClient(VPS_HOST, VPS_PORT, VPS_USER, VPS_PASSWORD)
        
        # 1. 获取当前 IP (作为原始 IP)
        await status_msg.edit_text("🔍 正在获取当前原始出口 IP...")
        original_data, _ = await get_ip_info_from_vps()
        original_ip = original_data.get('ip') if original_data else "未知"
        logger.info(f"原始出口 IP: {original_ip}")

        # 2. 获取节点列表
        await status_msg.edit_text("📋 正在获取出口节点列表...")
        output, error = ssh.get_menu_output()
        if error:
            await status_msg.edit_text(f"❌ 获取菜单失败: {error}")
            return
        
        options = parse_nm_output(output)
        if not options:
            await status_msg.edit_text("❌ 未解析到有效节点。")
            return

        total_nodes = len(options)
        await status_msg.edit_text(f"🔎 共发现 {total_nodes} 个节点，开始逐个检测...\n\n⚠️ 此过程可能需要较长时间，请耐心等待。")

        # 3. 开始循环检测
        results = []
        start_time = time.time()
        
        for i, opt in enumerate(options):
            # 更新进度
            progress = f"⏳ 正在检测 [{i+1}/{total_nodes}]: {opt['region']}..."
            await status_msg.edit_text(progress)
            
            # 执行检测
            is_ok, info = await test_node_connectivity(ssh, opt['number'], opt['region'])
            
            # 记录结果
            results.append({
                'number': opt['number'],
                'region': opt['region'],
                'status': is_ok,
                'info': info
            })

        # 4. 恢复原始节点
        await status_msg.edit_text("🔙 检测完成，正在恢复原始出口节点...")
        
        # 尝试寻找原始节点对应的选项
        original_node_number = None
        # 遍历刚才的检测结果，找到 IP 匹配的节点ID
        for res in results:
            if res['status'] and res['info'] == original_ip:
                original_node_number = res['number']
                break
        
        if original_node_number:
            logger.info(f"找到原始节点 ID: {original_node_number}，正在切回...")
            # 切回操作
            ssh.execute_interactive_command([str(original_node_number), '0'])
            restore_msg = f"已自动恢复至节点 {original_node_number}"
        else:
            logger.warning("未能自动匹配原始节点ID，保持当前状态。")
            restore_msg = "⚠️ 无法自动确定原始节点ID，请手动切回所需节点"

        # 5. 生成报告 (这里进行了修复，对所有动态内容进行转义)
        end_time = time.time()
        duration = round(end_time - start_time, 2)
        
        report_lines = [f"📊 *出口节点检测结果*", ""]
        for res in results:
            status_icon = "🟢" if res['status'] else "🔴"
            # 转义节点名和地区名
            line = f"{status_icon} `{escape_markdown(res['number'])}`\\. {escape_markdown(res['region'])}"
            
            # 关键修复：对 info (IP地址或错误信息) 进行转义，防止 . 导致报错
            safe_info = escape_markdown(str(res['info']))
            
            line += f" \\({safe_info}\\)"
            report_lines.append(line)
        
        report_lines.append("")
        # 关键修复：对耗时数字进行转义
        report_lines.append(f"⏱ 检测耗时: *{escape_markdown(str(duration))}* 秒")
        # 关键修复：对恢复信息进行转义
        report_lines.append(f"🔙 {escape_markdown(restore_msg)}")

        # 发送结果
        final_text = "\n".join(report_lines)
        if len(final_text) > 4000:
            await status_msg.edit_text("检测结果过长，请查看日志。")
        else:
            await status_msg.edit_text(final_text, parse_mode='MarkdownV2')

    except Exception as e:
        logger.error(f"/check 命令执行失败: {str(e)}")
        logger.error(traceback.format_exc())
        await status_msg.edit_text(f"❌ 检测过程出错: {str(e)}")


# ==================== 命令处理器 ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"用户 {username} (ID: {user_id}) 执行 /start 命令")

    if not is_authorized(user_id):
        await update.message.reply_text("❌ 你没有权限使用此机器人。")
        return

    welcome_message = """
🤖 *VPS 出口切换机器人*

欢迎使用！此机器人可以帮助你远程切换 VPS 的网络出口。

📋 *可用命令：*
/nm \\- 查看并切换 VPS 出口节点
/ip \\- 查看当前出口 IP 信息
/check \\- 批量检测所有出口可用性
/status \\- 查看当前连接状态
/help \\- 显示帮助信息

⚠️ *注意：*
• 同一时间只能激活一个出口节点
• 切换后网络出口将变更到所选区域
"""

    await update.message.reply_text(welcome_message, parse_mode='MarkdownV2')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"用户 {username} (ID: {user_id}) 执行 /help 命令")

    if not is_authorized(user_id):
        await update.message.reply_text("❌ 你没有权限使用此机器人。")
        return

    help_text = """
📖 *使用说明：*

*切换出口节点：*
1️⃣ 发送 /nm 命令
2️⃣ 机器人会获取可用的出口列表
3️⃣ 点击你想要切换的国家/地区按钮
4️⃣ 等待切换完成

*查看当前 IP：*
1️⃣ 发送 /ip 命令
2️⃣ 查看当前出口 IP 的详细信息

*批量检测出口：*
1️⃣ 发送 /check 命令
2️⃣ 机器人将逐个测试所有出口的连通性
3️⃣ 自动恢复到检测前的出口

💡 *提示：*
• 切换后使用 /ip 命令确认切换是否成功
• 如果遇到问题，请查看日志文件 bot\\.log
"""

    await update.message.reply_text(help_text, parse_mode='MarkdownV2')


async def ip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /ip 命令 - 查看当前出口 IP 信息"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"用户 {username} (ID: {user_id}) 执行 /ip 命令")

    if not is_authorized(user_id):
        await update.message.reply_text("❌ 你没有权限使用此机器人。")
        return

    status_msg = await update.message.reply_text("🔄 正在查询当前出口 IP 信息，请稍候...")

    try:
        data, error = await get_ip_info_from_vps()

        if error:
            logger.error(f"IP 查询失败: {error}")
            await status_msg.edit_text(f"❌ 查询失败：{error}")
            return

        if not data:
            logger.error("IP 查询返回空数据")
            await status_msg.edit_text("❌ 无法获取 IP 信息，请稍后重试。")
            return

        message = format_ip_info(data)
        await status_msg.edit_text(message, parse_mode='MarkdownV2')
        logger.info(f"IP 信息查询成功: {data.get('ip', 'unknown')}")

    except Exception as e:
        logger.error(f"IP 命令执行出错: {str(e)}")
        logger.error(traceback.format_exc())
        await status_msg.edit_text(f"❌ 查询出错：{str(e)}")


async def nm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /nm 命令 - 获取出口列表"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"用户 {username} (ID: {user_id}) 执行 /nm 命令")

    if not is_authorized(user_id):
        await update.message.reply_text("❌ 你没有权限使用此机器人。")
        return

    status_msg = await update.message.reply_text("🔄 正在连接到 VPS，请稍候...")

    try:
        ssh = SSHClient(VPS_HOST, VPS_PORT, VPS_USER, VPS_PASSWORD)

        await status_msg.edit_text("🔄 正在获取出口节点列表...")
        # 使用新方法获取菜单输出
        output, error = ssh.get_menu_output()

        if error:
            logger.error(f"获取菜单失败: {error}")
            await status_msg.edit_text(
                f"❌ 获取菜单失败\n\n"
                f"错误：{error}\n\n"
                f"请确认 VPS 上存在 /etc/uzmaru/out.sh 文件"
            )
            return

        logger.debug(f"菜单输出: {output[:500]}")

        options = parse_nm_output(output)

        if not options:
            logger.warning("未能解析到任何选项")
            # 显示原始输出供调试
            escaped_output = output.replace('`', '\\`').replace('*', '\\*').replace('_', '\\_')
            await status_msg.edit_text(
                f"⚠️ 无法解析输出\n\n原始输出：\n```\n{escaped_output[:800]}\n```",
                parse_mode='MarkdownV2'
            )
            return

        # 创建内联键盘（每行最多2个按钮，防止太长）
        keyboard = []
        row = []
        for i, option in enumerate(options):
            button = InlineKeyboardButton(
                f"{option['number']}. {option['region']}",
                callback_data=f"switch_{option['number']}"
            )
            row.append(button)

            # 每2个按钮换行，或者是最后一个选项
            if len(row) == 2 or i == len(options) - 1:
                keyboard.append(row)
                row = []

        # 添加取消按钮
        keyboard.append([InlineKeyboardButton("❌ 取消", callback_data="cancel")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await status_msg.edit_text(
            "🌍 *请选择要切换的出口节点：*\n\n"
            "⚠️ 切换后，你的网络出口将变更到所选区域。",
            reply_markup=reply_markup,
            parse_mode='MarkdownV2'
        )
        logger.info(f"成功显示 {len(options)} 个出口选项")

    except Exception as e:
        logger.error(f"/nm 命令执行失败: {str(e)}")
        logger.error(traceback.format_exc())

        error_msg = (
            f"❌ 连接失败\n\n"
            f"错误类型: {type(e).__name__}\n"
            f"错误信息: {str(e)}\n\n"
            f"详细日志已记录到 bot.log 文件"
        )
        await status_msg.edit_text(error_msg)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮点击回调"""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"用户 {username} (ID: {user_id}) 点击按钮: {query.data}")

    if not is_authorized(user_id):
        await query.edit_message_text("❌ 你没有权限使用此机器人。")
        return

    data = query.data

    if data == "cancel":
        logger.info("用户取消操作")
        await query.edit_message_text("✅ 操作已取消。")
        return

    if data.startswith("switch_"):
        selection = data.replace("switch_", "")
        logger.info(f"用户选择切换到节点: {selection}")

        await query.edit_message_text(
            f"🔄 正在切换到节点 {selection}，请稍候...\n\n⏳ 这可能需要几秒钟时间..."
        )

        try:
            ssh = SSHClient(VPS_HOST, VPS_PORT, VPS_USER, VPS_PASSWORD)

            # 切换节点 + 退出菜单
            initial_output, final_output = ssh.execute_interactive_command([selection, '0'])

            logger.info(f"节点切换完成: {selection}")
            logger.debug(f"切换输出: {final_output[:200]}")

            success_message = (
                f"✅ *切换完成！*\n\n"
                f"已切换到节点 *{selection}*\n\n"
                f"💡 使用 /ip 命令查看当前出口 IP 信息"
            )

            await query.edit_message_text(success_message, parse_mode='MarkdownV2')

        except Exception as e:
            logger.error(f"节点切换失败: {str(e)}")
            logger.error(traceback.format_exc())

            await query.edit_message_text(
                f"❌ 切换失败\n\n"
                f"错误: {str(e)}\n\n"
                f"详细日志已记录到 bot.log 文件"
            )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /status 命令"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"用户 {username} (ID: {user_id}) 执行 /status 命令")

    if not is_authorized(user_id):
        await update.message.reply_text("❌ 你没有权限使用此机器人。")
        return

    status_msg = await update.message.reply_text("🔄 正在检查状态...")

    try:
        ssh = SSHClient(VPS_HOST, VPS_PORT, VPS_USER, VPS_PASSWORD)
        output, error = ssh.execute_command('echo "Connection OK"')

        if "Connection OK" in output:
            logger.info("VPS 连接状态正常")
            # 转义特殊字符
            host = escape_markdown(VPS_HOST)
            user = escape_markdown(VPS_USER)
            port = escape_markdown(str(VPS_PORT))

            await status_msg.edit_text(
                f"✅ *VPS 连接正常*\n\n"
                f"🖥️ 主机：{host}\n"
                f"👤 用户：{user}\n"
                f"🔌 端口：{port}",
                parse_mode='MarkdownV2'
            )
        else:
            logger.warning("VPS 连接异常")
            await status_msg.edit_text("⚠️ VPS 连接异常，请检查配置。")

    except Exception as e:
        logger.error(f"状态检查失败: {str(e)}")
        logger.error(traceback.format_exc())
        await status_msg.edit_text(f"❌ 无法连接到 VPS：{str(e)}")


# ==================== 主程序 ====================
def main():
    """主函数"""
    logger.info("=" * 50)
    logger.info("机器人启动中...")
    logger.info(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 检查配置
    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("错误：未设置 BOT_TOKEN")
        print("❌ 错误：请设置 BOT_TOKEN")
        return

    if VPS_HOST == 'YOUR_VPS_IP_HERE':
        logger.error("错误：未设置 VPS_HOST")
        print("❌ 错误：请设置 VPS_HOST")
        return

    if not VPS_PASSWORD:
        logger.error("错误：未设置 VPS_PASSWORD")
        print("❌ 错误：请设置 VPS_PASSWORD")
        return

    logger.info(f"Bot Token: {BOT_TOKEN[:10]}...")
    logger.info(f"VPS 配置: {VPS_USER}@{VPS_HOST}:{VPS_PORT}")
    logger.info(f"授权用户: {AUTHORIZED_USERS if AUTHORIZED_USERS else '所有用户'}")

    # 创建应用
    application = Application.builder().token(BOT_TOKEN).build()

    # 添加命令处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("nm", nm_command))
    application.add_handler(CommandHandler("ip", ip_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("check", check_command))  # 注册新命令
    application.add_handler(CallbackQueryHandler(button_callback))

    logger.info("所有命令处理器已注册")
    logger.info("=" * 50)

    print("\n" + "=" * 50)
    print("🤖 VPS 出口切换机器人")
    print("=" * 50)
    print(f"📡 VPS: {VPS_USER}@{VPS_HOST}:{VPS_PORT}")
    print(f"📝 日志文件: bot.log")
    print(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    print("✅ 机器人已启动，按 Ctrl+C 停止")
    print("=" * 50 + "\n")

    # 启动机器人
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("收到停止信号，机器人正在关闭...")
        print("\n👋 机器人已停止")
    except Exception as e:
        logger.error(f"机器人运行时发生错误: {str(e)}")
        logger.error(traceback.format_exc())
        print(f"\n❌ 错误: {str(e)}")


if __name__ == '__main__':
    main()
