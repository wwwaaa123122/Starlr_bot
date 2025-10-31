import os
import json
import asyncio
import schedule
import time
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any
import aiohttp
from playwright.async_api import async_playwright

TRIGGHT_KEYWORD = "Any"
HELP_MESSAGE = "#群总结状态 - 查看群总结功能状态"

class GroupSummaryPlugin:
    def __init__(self):
        self.cache_dir = Path("temp/group_summary_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.summary_sent_today = set()
        self.setup_schedule()
    
    def setup_schedule(self):
        """设置定时任务"""
        schedule.every().day.at("23:00").do(
            lambda: asyncio.create_task(self.send_daily_summaries())
        )
    
    def get_group_cache_file(self, group_id: str) -> Path:
        """获取群组缓存文件路径"""
        today = date.today().isoformat()
        return self.cache_dir / f"{group_id}_{today}.json"
    
    async def save_group_message(self, group_id: str, event, event_user: str):
        """保存群消息到缓存"""
        try:
            cache_file = self.get_group_cache_file(group_id)
            
            # 读取现有消息
            messages = []
            if cache_file.exists():
                with open(cache_file, 'r', encoding='utf-8') as f:
                    messages = json.load(f)
            
            # 添加新消息
            message_data = {
                'sender_id': str(event.user_id),
                'sender_name': event_user,
                'content': str(event.message),
                'timestamp': datetime.now().isoformat(),
                'message_id': getattr(event, 'message_id', 'unknown')
            }
            
            messages.append(message_data)
            
            # 只保留最近500条消息防止文件过大
            if len(messages) > 500:
                messages = messages[-500:]
            
            # 保存回文件
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"保存群消息失败: {e}")
    
    async def generate_ai_summary(self, group_id: str, messages: List[Dict], deepseek_key: str) -> str:
        """使用DeepSeek生成群聊总结"""
        if not messages:
            return "今天群内比较安静，没有太多讨论呢~"
        
        # 构建消息文本供AI分析
        recent_messages = messages[-500:]  # 只分析最近100条消息避免过长
        message_text = "\n".join([
            f"{msg['sender_name']}: {msg['content']}" 
            for msg in recent_messages
        ])
        
        # 使用DeepSeek生成总结
        try:
            import requests
            
            prompt = f"""请对以下群聊记录进行简洁明了的总结，要求：

1. 概括今天的主要讨论话题和热点
2. 提及活跃的成员和有趣的互动
3. 总结氛围和特点
4. 语言生动有趣，带点emoji表情
5. 控制在300字以内

群聊记录：
{message_text}

请生成一份温馨有趣的每日总结："""
            
            headers = {
                "Authorization": f"Bearer {deepseek_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是一个群聊总结助手，擅长从聊天记录中提取关键信息，生成生动有趣的每日总结。"
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                "stream": False,
                "max_tokens": 1024
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result["choices"][0]["message"]["content"]
                    else:
                        print(f"DeepSeek API请求失败: {response.status}")
                        return self.generate_basic_summary(messages)
                        
        except Exception as e:
            print(f"DeepSeek总结生成失败: {e}")
            # 如果AI失败，使用基础总结
            return self.generate_basic_summary(messages)
    
    def generate_basic_summary(self, messages: List[Dict]) -> str:
        """生成基础总结（AI失败时使用）"""
        total_messages = len(messages)
        active_members = len(set(msg['sender_id'] for msg in messages))
        
        # 统计时间段
        hour_count = {i: 0 for i in range(24)}
        for msg in messages:
            try:
                msg_time = datetime.fromisoformat(msg['timestamp'].replace('Z', '+00:00'))
                hour_count[msg_time.hour] += 1
            except:
                continue
        
        peak_hour = max(hour_count.items(), key=lambda x: x[1])
        
        # 提取热门关键词
        word_freq = {}
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, str):
                words = content.split()
                for word in words:
                    if len(word) > 1:  # 过滤单字
                        word_freq[word] = word_freq.get(word, 0) + 1
        
        top_topics = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:3]
        
        summary = f"""📊 今日群聊总结 ({date.today().strftime('%Y-%m-%d')})

🗣️ 活跃概况：
• 总消息数：{total_messages} 条
• 活跃成员：{active_members} 人
• 最活跃时段：{peak_hour[0]}:00-{peak_hour[0]+1}:00"""

        if top_topics:
            summary += f"\n\n🔥 热门话题："
            for topic, count in top_topics:
                summary += f"\n• #{topic} ({count}次提及)"

        summary += "\n\n💬 今日群内进行了热烈讨论，大家积极参与交流，氛围融洽！"
        summary += "\n\n明天继续精彩讨论！🎉"
        
        return summary
    
    async def text_to_image(self, text: str, group_id: str) -> str:
        """将文本转换为图片"""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                
                # 设置页面样式
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <style>
                        body {{
                            font-family: 'Microsoft YaHei', sans-serif;
                            padding: 30px;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            margin: 0;
                            min-height: 100vh;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        }}
                        .summary-card {{
                            background: white;
                            border-radius: 20px;
                            padding: 40px;
                            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                            max-width: 600px;
                            line-height: 1.6;
                        }}
                        .title {{
                            text-align: center;
                            color: #333;
                            font-size: 24px;
                            font-weight: bold;
                            margin-bottom: 30px;
                            border-bottom: 3px solid #667eea;
                            padding-bottom: 15px;
                        }}
                        .content {{
                            color: #555;
                            font-size: 16px;
                            white-space: pre-line;
                        }}
                        .footer {{
                            text-align: center;
                            margin-top: 30px;
                            color: #888;
                            font-size: 14px;
                            border-top: 1px solid #eee;
                            padding-top: 15px;
                        }}
                        .ai-brand {{
                            color: #667eea;
                            font-weight: bold;
                        }}
                    </style>
                </head>
                <body>
                    <div class="summary-card">
                        <div class="title">✨ 群聊每日总结 ✨</div>
                        <div class="content">{text}</div>
                        <div class="footer">
                            <div>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
                            <div style="margin-top: 8px;">Powered by <span class="ai-brand">DeepSeek AI</span></div>
                        </div>
                    </div>
                </body>
                </html>
                """
                
                await page.set_content(html_content)
                await page.wait_for_timeout(1000)  # 等待渲染完成
                
                # 截图保存
                image_path = f"temp/summary_{group_id}_{datetime.now().strftime('%H%M%S')}.png"
                await page.screenshot(path=image_path, full_page=True)
                await browser.close()
                
                return image_path
                
        except Exception as e:
            print(f"生成总结图片失败: {e}")
            return None
    
    async def send_daily_summaries(self, actions=None, Manager=None, Segments=None):
        """发送所有群的每日总结"""
        print("开始生成群聊每日总结...")
        
        # 获取所有有消息的群组
        today = date.today().isoformat()
        summary_files = list(self.cache_dir.glob(f"*_{today}.json"))
        
        sent_count = 0
        for cache_file in summary_files:
            try:
                group_id = cache_file.stem.split('_')[0]
                
                # 检查是否已经发送过总结
                if group_id in self.summary_sent_today:
                    continue
                
                # 读取消息
                with open(cache_file, 'r', encoding='utf-8') as f:
                    messages = json.load(f)
                
                if len(messages) < 10:  # 至少10条消息才生成总结
                    print(f"群 {group_id} 消息不足10条，跳过总结")
                    continue
                
                # 获取DeepSeek API Key
                from Hyper import Configurator
                config = Configurator.cm.get_cfg()
                deepseek_key = config.others.get("deepseek_key", "")
                
                if not deepseek_key:
                    print("未找到DeepSeek API Key，使用基础总结")
                    summary_text = self.generate_basic_summary(messages)
                else:
                    # 生成AI总结
                    summary_text = await self.generate_ai_summary(group_id, messages, deepseek_key)
                
                # 转换为图片
                image_path = await self.text_to_image(summary_text, group_id)
                
                if image_path and os.path.exists(image_path):
                    if actions and Manager and Segments:
                        # 发送图片到群组
                        await actions.send(
                            group_id=int(group_id),
                            message=Manager.Message(Segments.Image(image_path))
                        )
                        print(f"群 {group_id} 总结图片发送成功")
                    else:
                        print(f"群 {group_id} 总结图片已生成: {image_path}")
                    
                    # 标记为已发送
                    self.summary_sent_today.add(group_id)
                    sent_count += 1
                    
                    # 清理缓存文件
                    os.remove(cache_file)
                    
                    # 删除图片文件
                    try:
                        os.remove(image_path)
                    except:
                        pass
                    
                else:
                    print(f"群 {group_id} 总结图片生成失败")
                    
            except Exception as e:
                print(f"处理群 {cache_file.stem} 总结失败: {e}")
        
        # 重置发送状态
        self.summary_sent_today.clear()
        print(f"群聊每日总结完成，共发送 {sent_count} 个群的总结")
        
        return sent_count

# 创建插件实例
plugin = GroupSummaryPlugin()

async def on_message(event, actions, Manager, Segments, Events, reminder, bot_name, config):
    """处理消息事件"""
    
    # 只处理群消息
    if not isinstance(event, Events.GroupMessageEvent):
        return False
    
    # 处理状态查询命令
    user_message = str(event.message)
    if user_message.startswith(reminder) and "群总结状态" in user_message:
        today = date.today().isoformat()
        cache_file = plugin.get_group_cache_file(str(event.group_id))
        
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                messages = json.load(f)
            status = f"✅ 今日已收集 {len(messages)} 条消息，将在23:00生成AI总结图片"
        else:
            status = "❌ 今日尚未收集到消息"
        
        await actions.send(
            group_id=event.group_id,
            message=Manager.Message(Segments.Text(status))
        )
        return True
    
    # 保存群消息
    s, event_user = await get_user_info(event.user_id, Manager, actions)
    if s:
        event_user = event_user['nickname']
    else:
        event_user = str(event.user_id)
    
    await plugin.save_group_message(str(event.group_id), event, event_user)
    
    # 运行定时任务检查
    schedule.run_pending()
    
    return False

# 辅助函数（使用简儿已有的函数）
async def get_user_info(user_id, Manager, actions):
    """获取用户信息"""
    try:
        user_info = await actions.custom.get_stranger_info(user_id=user_id)
        result = Manager.Ret.fetch(user_info)
        return True, result.data.raw
    except:
        return False, {}

# 定时任务运行器
async def run_scheduler(actions=None, Manager=None, Segments=None):
    """运行定时任务检查"""
    while True:
        schedule.run_pending()
        
        # 检查是否是23:00，如果是则发送总结
        now = datetime.now()
        if now.hour == 23 and now.minute == 0 and now.second < 10:
            # 避免重复发送
            if not hasattr(run_scheduler, 'last_sent') or run_scheduler.last_sent != now.date():
                await plugin.send_daily_summaries(actions, Manager, Segments)
                run_scheduler.last_sent = now.date()
        
        await asyncio.sleep(5)

# 启动定时任务检查
async def start_scheduler(actions=None, Manager=None, Segments=None):
    """启动定时任务检查器"""
    asyncio.create_task(run_scheduler(actions, Manager, Segments))