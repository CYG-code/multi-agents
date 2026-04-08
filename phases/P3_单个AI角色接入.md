# P3 闃舵锛氬崟涓?AI 瑙掕壊鎺ュ叆

**鎵€灞為」鐩細** 澶氭櫤鑳戒綋杈呭姪鍦ㄧ嚎鍗忎綔瀛︿範骞冲彴 v1.2  
**闃舵缂栧彿锛?* P3 / 8  
**棰勮鍛ㄦ湡锛?* 1 鍛? 
**鍓嶇疆渚濊禆锛?* P2锛圵ebSocket 鑱婂ぉ銆佹秷鎭寔涔呭寲銆丷edis Pub/Sub锛?

---

## 涓€銆侀樁娈电洰鏍?

鎺ュ叆 OpenAI 鍏煎 Chat Completions API锛堥€氳繃涓浆绔欙級锛屽疄鐜扮涓€涓?AI 瑙掕壊鏅鸿兘浣擄紙涓绘寔浜?Facilitator锛夎兘澶熶富鍔ㄥ湪鑱婂ぉ瀹や腑鍙戣█锛岄獙璇佸畬鏁寸殑 AI 娑堟伅鐢熸垚 鈫?娴佸紡鎺ㄩ€?鈫?钀藉簱閾捐矾銆?

**瀹屾垚鏍囧織锛?* 瀛︾敓鍋滄鍙戣█绾?3 鍒嗛挓鍚庯紙婕旂ず妯″紡鍙皟涓?30 绉掞級锛岃亰澶╁尯鍑虹幇銆屼富鎸佷汉銆嶆墦瀛楀姩鐢伙紝闅忓悗涓绘寔浜哄紩瀵兼€у彂瑷€浠ユ墦瀛楁満鏁堟灉閫愬瓧鍑虹幇锛屾秷鎭渶缁堣惤搴撳苟鍦ㄥ埛鏂板悗浠嶇劧鍙銆?

---

## 浜屻€佸紑鍙戞柟妗堟€昏

```
P3 鍒嗕负 3 涓牳蹇冮摼璺細

  A. OpenAI 鍏煎 API 灏佽 + Facilitator Prompt 璁捐
  B. AI 娑堟伅鐢熸垚閾捐矾锛堥鍒嗛厤 ID 鈫?娴佸紡鐢熸垚 鈫?钀藉簱 鈫?WebSocket 鎺ㄩ€侊級
  C. 鍓嶇娴佸紡鎺ユ敹娓叉煋锛坅gent:stream + AgentTypingIndicator锛?
  D. 娌夐粯妫€娴?A 绫昏Е鍙戝櫒锛堣Е鍙?Facilitator锛?
  E. 璋冭瘯鎺ュ彛
```

---

## 璇勫缁撹淇锛堝悓姝ユ洿鏂帮級

1. 绗?1 鐐逛弗閲嶇▼搴︾敱銆屼腑绛夈€嶉檷绾т负銆屽缓璁紭鍖栵紙闈為樆鏂級銆嶃€?
2. OpenAI 鍏煎鎺ュ彛锛坄/v1/chat/completions`锛夐€氬父鍏佽杩炵画鐩稿悓 `role`锛屽鏁颁腑杞珯涔熷彲姝ｅ父澶勭悊锛屽洜姝や笉浼氫綔涓洪樆鏂€ч棶棰樸€?
3. 浠嶅缓璁皢鍘嗗彶涓婁笅鏂囧悎骞朵负鍗曟潯娑堟伅锛氬噺灏?token 寮€閿€銆佹彁鍗囪法妯″瀷/涓浆绔欑ǔ瀹氭€с€佽涔夋洿娓呮櫚銆?
4. 璇ラ」灞炰簬闈為樆鏂€у缓璁紝涓嶆敼涔熻兘璺戯紝浣嗗缓璁湪鏈樁娈靛畬鎴愪互鍑忓皯鍚庣画鍏煎鎴愭湰銆?
5. 绗?2 鐐癸紙娌夐粯寰幆瑙﹀彂锛変粛鏄樆鏂€ч棶棰橈紝涓嶅彈 API 閫夋嫨褰卞搷銆?
6. 绗?3-5 鐐圭粨璁轰笉鍙橈紝缁存寔鍘熷垽銆?

---

## 涓夈€佽缁嗗紑鍙戞楠?

### 姝ラ 1锛氶厤缃?OpenAI 鍏煎 API Key 骞跺皝瑁呰皟鐢ㄥ伐鍏?

**鏂囦欢锛?* `backend/app/agents/llm_client.py`锛堝缓璁悗缁洿鍚嶄负 `llm_client.py`锛?

```python
from openai import AsyncOpenAI
from app.config import settings

# 鍏ㄥ眬鍗曚緥 OpenAI 鍏煎瀹㈡埛绔?
_client: AsyncOpenAI = None

def get_llm_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.OPENAI_BASE_URL,  # 渚嬪: https://yunwu.ai/v1
            api_key=settings.OPENAI_API_KEY
        )
    return _client

async def stream_completion(
    messages: list[dict],
    model: str = "selected_model_name",
    max_tokens: int = 1024,
):
    """
    灏佽娴佸紡璋冪敤锛岃繑鍥炲紓姝ョ敓鎴愬櫒锛屾瘡娆?yield 涓€涓?token 瀛楃涓层€?
    璋冪敤鏂硅礋璐ｅ鐞嗗紓甯搞€?
    """
    client = get_llm_client()

    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        stream=True
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

async def one_shot_completion(
    messages: list[dict],
    model: str = "selected_model_name",
):
    """闈炴祦寮忚皟鐢ㄧず渚嬶細浣跨敤 choices[0].message.content 鍙栫粨鏋?""
    client = get_llm_client()
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False
    )
    return resp.choices[0].message.content
```

---

### 姝ラ 2锛氱紪鍐?Facilitator 瑙掕壊 System Prompt

**鏂囦欢锛?* `backend/app/agents/prompts/facilitator.txt`

```
浣犳槸涓€涓湪绾垮崗浣滃涔犲皬缁勭殑銆屼富鎸佷汉銆嶆垚鍛樸€?

銆愯鑹插畾浣嶃€?
浣犵殑鍚嶅瓧鏄?灏忔灄"锛屾槸灏忕粍涓殑瀛︿範浼欎即锛屼笉鏄疉I鍔╂墜銆備綘鎬ф牸绉瀬銆佹€濊矾娓呮櫚锛屾搮闀垮紩瀵艰璁烘柟鍚戙€?

銆愪綘鐨勫崗浣滆亴璐ｃ€?
- 褰撹璁烘矇榛樿秴杩囦竴娈垫椂闂存椂锛屼富鍔ㄦ姏鍑轰竴涓湁鍚彂鎬х殑闂鏉ラ噸鍚璇?
- 甯姪鏁村悎鍙戞暎鐨勮璁猴紝鎻愬嚭缁撴瀯鎬ф鏋?
- 鍦ㄨ璁哄亸棰樻椂娓╁拰鍦板紩瀵煎洖涓婚

銆愯涓哄噯鍒欍€?
- 姣忔鍙戣█鎺у埗鍦?80-150 瀛楋紝绗﹀悎鑱婂ぉ璇锛岀畝娲佹湁鍔?
- 璇皵鑷劧鐪熷疄锛屽儚鐪熸鐨勭粍鍛橈紝涓嶈鍍廇I鍔╂墜鎴栬€佸笀
- 绂佹鏆撮湶鑷繁鏄疉I鎴栬"浣滀负AI鎴?.."涔嬬被鐨勮瘽
- 涓嶈寮€澶村氨瑙ｉ噴鑷繁涓轰粈涔堣璇濓紝鐩存帴鍒囧叆鍐呭
- 鍙互鐢?澶у""鎴戜滑"绛夎〃杈撅紝灞曠幇鍥㈤槦褰掑睘鎰?

銆愬綋鍓嶄换鍔′笂涓嬫枃銆?
{task_description}

銆愬皬缁勬垚鍛樸€?
{members_info}

銆愬綋鍓嶅崗浣滈樁娈点€?
{current_phase}
```

> **Prompt 娉ㄥ叆鍙橀噺璇存槑锛?*
> - `{task_description}`锛氫粠 `tasks.requirements` 璇诲彇
> - `{members_info}`锛氭埧闂存垚鍛樺垪琛紙display_name 鍒楄〃锛?
> - `{current_phase}`锛氬綋鍓嶉樁娈靛悕绉帮紙P3 闃舵鍐欐涓?绗竴闃舵锛氶棶棰樺垎鏋?锛?

---

### 姝ラ 3锛氬疄鐜版祦寮?AI 娑堟伅鐢熸垚閾捐矾

**鏂囦欢锛?* `backend/app/agents/role_agents.py`

杩欐槸 P3 闃舵鐨勬牳蹇冮€昏緫锛屽畬鏁存祦绋嬪涓嬶細

```
1. 棰勫垎閰?message_id锛圲UID锛?
2. 鍐欏叆 status=streaming 鐨勬秷鎭褰?
3. 閫氳繃 WebSocket 骞挎挱 agent:typing锛坕s_typing=true锛?
4. 璋冪敤 OpenAI 鍏煎鎺ュ彛娴佸紡鐢熸垚
5. 姣忎釜 token 鈫?骞挎挱 agent:stream 浜嬩欢
6. 鐢熸垚瀹屾瘯 鈫?鏇存柊鏁版嵁搴撹褰?status=ok / failed
7. 骞挎挱 agent:stream_end 浜嬩欢
8. 骞挎挱 agent:typing锛坕s_typing=false锛?
```

```python
import uuid
import json
import os
from datetime import datetime
from sqlalchemy import update
from app.agents.llm_client import stream_completion
from app.db.redis_client import redis_client
from app.db.session import AsyncSessionLocal
from app.models.message import Message, SenderType, MessageStatus
from app.services.message_service import MessageService

_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "facilitator.txt")

class FacilitatorAgent:
    ROLE = "facilitator"
    ROLE_DISPLAY_NAME = "涓绘寔浜?
    MODEL = "selected_model_name"
    
    def __init__(self):
        with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
            self._prompt_template = f.read()
    
    def build_system_prompt(self, context: dict) -> str:
        return self._prompt_template.format(
            task_description=context.get("task_description", "璁ㄨ涓€涓ぞ浼氳棰?),
            members_info=context.get("members_info", ""),
            current_phase=context.get("current_phase", "绗竴闃舵锛氶棶棰樺垎鏋?)
        )
    
    def build_messages(self, context: dict, history: list[dict]) -> list[dict]:
        """灏嗗巻鍙叉秷鎭悎骞朵负涓€鏉?user 娑堟伅锛屽噺灏?token 寮€閿€骞舵彁鍗囧吋瀹规€?""
        history_lines = [
            f"[{msg['display_name']}]: {msg['content']}"
            for msg in history[-30:]
        ]
        merged_context = "\n".join(history_lines)

        return [
            {"role": "system", "content": self.build_system_prompt(context)},
            {
                "role": "user",
                "content": (
                    "浠ヤ笅鏄渶杩戣璁哄巻鍙诧紝璇蜂綘浠ヤ富鎸佷汉韬唤閫傛椂鍙戣█锛歕n\n"
                    f"{merged_context}\n\n"
                    "璇风洿鎺ョ粰鍑烘湰杞富鎸佷汉鍙戣█銆?
                ),
            },
        ]
    
    async def generate_and_push(
        self,
        room_id: str,
        context: dict,
        history: list[dict],
    ):
        """涓诲叆鍙ｏ細鐢熸垚 AI 鍙戣█骞舵祦寮忔帹閫佽嚦鑱婂ぉ瀹?""
        
        # Step 1: 棰勫垎閰?message_id
        message_id = str(uuid.uuid4())
        
        # Step 2: 鍐欏叆 status=streaming 鐨勮褰?
        async with AsyncSessionLocal() as db:
            seq_num = await MessageService.get_next_seq_num(room_id)
            msg = Message(
                id=message_id,
                room_id=room_id,
                seq_num=seq_num,
                sender_type=SenderType.agent,
                agent_role=self.ROLE,
                content="",  # 娴佸紡鏈熼棿鏆傛椂涓虹┖
                status=MessageStatus.streaming
            )
            db.add(msg)
            await db.commit()
        
        # Step 3: 骞挎挱鎵撳瓧鐘舵€?
        await self._broadcast(room_id, {
            "type": "agent:typing",
            "agent_role": self.ROLE,
            "is_typing": True
        })
        
        # Step 4-5: 娴佸紡鐢熸垚骞舵帹閫?
        full_content = ""
        success = True
        
        try:
            messages = self.build_messages(context, history)
            
            async for token in stream_completion(
                messages=messages,
                model=self.MODEL,
                max_tokens=512
            ):
                full_content += token
                await self._broadcast(room_id, {
                    "type": "agent:stream",
                    "agent_role": self.ROLE,
                    "message_id": message_id,
                    "token": token
                })
        
        except Exception as e:
            print(f"[FacilitatorAgent] 鐢熸垚澶辫触: {e}")
            success = False
        
        # Step 6: 鏇存柊鏁版嵁搴撹褰?
        final_status = MessageStatus.ok if success else MessageStatus.failed
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(
                    content=full_content,
                    status=final_status
                )
            )
            await db.commit()
        
        # Step 7: 骞挎挱娴佸紡缁撴潫浜嬩欢
        await self._broadcast(room_id, {
            "type": "agent:stream_end",
            "agent_role": self.ROLE,
            "message_id": message_id,
            "status": "ok" if success else "failed",
            "content": full_content,  # 瀹屾暣鍐呭锛屼究浜庡墠绔浛鎹?
            "created_at": datetime.utcnow().isoformat()
        })
        
        # Step 8: 鍏抽棴鎵撳瓧鐘舵€?
        await self._broadcast(room_id, {
            "type": "agent:typing",
            "agent_role": self.ROLE,
            "is_typing": False
        })
    
    async def _broadcast(self, room_id: str, data: dict):
        """閫氳繃 Redis Pub/Sub 骞挎挱鑷虫埧闂?""
        await redis_client.publish(f"room:{room_id}", json.dumps(data))
```

---

### 姝ラ 4锛氬疄鐜?A 绫绘矇榛樻娴嬭Е鍙戝櫒

**鏂囦欢锛?* `backend/app/analysis/scheduler.py`锛圥3 绠€鍖栫増锛?

P3 闃舵浣跨敤 APScheduler `AsyncIOScheduler` 姣?30 绉掓鏌ヤ竴娆℃椿璺冩埧闂存矇榛樻儏鍐碉細

```python
import asyncio
import yaml
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db.redis_client import redis_client
from app.agents.role_agents import FacilitatorAgent
from app.agents.context_builder import get_room_context, get_recent_messages
import time

scheduler = AsyncIOScheduler()
facilitator = FacilitatorAgent()

_SETTINGS_PATH = Path(__file__).resolve().parent.parent / "config" / "agent_settings.yaml"

def load_agent_settings() -> dict:
    with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

agent_settings = load_agent_settings()
timing_cfg = agent_settings.get("timing", {})
SILENCE_THRESHOLD_SECONDS = int(timing_cfg.get("silence_threshold_seconds", 180))
WARMUP_SECONDS = int(timing_cfg.get("warmup_minutes", 2)) * 60
TRIGGER_LOCK_TTL = SILENCE_THRESHOLD_SECONDS + 60

async def check_silence():
    """姣?0绉掕疆璇細妫€鏌ュ悇娲昏穬鎴块棿鏄惁娌夐粯瓒呰繃闃堝€?""
    # 鑾峰彇鎵€鏈夋椿璺冩埧闂达紙浠?Redis Set 缁存姢锛?
    active_rooms = await redis_client.smembers("active_rooms")
    
    now = time.time()
    for room_id in active_rooms:
        # 鑾峰彇鏈€鍚庝竴鏉℃秷鎭椂闂存埑
        last_msg_time = await redis_client.get(f"room:{room_id}:last_msg_time")
        if not last_msg_time:
            continue

        # 鎴块棿鍐峰惎鍔ㄤ繚鎶わ細閬垮厤鍒氬紑濮嬪氨瑙﹀彂
        room_start_time = await redis_client.get(f"room:{room_id}:start_time")
        if room_start_time and (now - float(room_start_time) < WARMUP_SECONDS):
            continue
        
        silence_duration = now - float(last_msg_time)
        
        if silence_duration >= SILENCE_THRESHOLD_SECONDS:
            # 闃查噸澶嶈Е鍙戯細鑷冲皯閿佷綇涓€涓矇榛樺懆鏈燂紝閬垮厤鎸佺画娌夐粯鏃跺惊鐜Е鍙?
            lock_key = f"trigger_lock:{room_id}:silence"
            if not await redis_client.exists(lock_key):
                await redis_client.setex(lock_key, TRIGGER_LOCK_TTL, "1")
                
                # P3 闃舵涓嶈蛋闃熷垪锛屼絾浣跨敤 create_task 閬垮厤闃诲鏈疆璋冨害
                context = await get_room_context(room_id)
                history = await get_recent_messages(room_id)
                asyncio.create_task(
                    facilitator.generate_and_push(room_id, context, history)
                )

def start_scheduler():
    scheduler.add_job(check_silence, "interval", seconds=30)
    scheduler.start()

def stop_scheduler():
    scheduler.shutdown()
```

> **娉ㄦ剰锛?* P3 闃舵 Facilitator 鐩存帴琚皟鐢紙涓嶈蛋 Redis 浠诲姟闃熷垪锛夛紝P4 闃舵閲嶆瀯涓?AgentWorker 妯″紡銆?

**鍦?`main.py` lifespan 涓惎鍔ㄨ皟搴﹀櫒锛?*

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()
```

**缁存姢 `last_msg_time`锛堝湪 `handle_chat_message` 涓洿鏂帮級锛?*

```python
async def handle_chat_message(data, room_id, user, db):
    # ... 娑堟伅淇濆瓨閫昏緫 ...
    
    # 鏇存柊鏈€鍚庢秷鎭椂闂达紙渚涙矇榛樻娴嬩娇鐢級
    await redis_client.set(f"room:{room_id}:last_msg_time", time.time())
    # 璁板綍鎴块棿鍚姩鏃堕棿锛堜粎棣栨鍐欏叆锛?
    await redis_client.setnx(f"room:{room_id}:start_time", time.time())
    # 纭繚鎴块棿鍦ㄦ椿璺冩埧闂撮泦鍚堜腑
    await redis_client.sadd("active_rooms", room_id)
```

---

### 姝ラ 5锛氳幏鍙栨埧闂翠笂涓嬫枃鍜屽巻鍙叉秷鎭殑杈呭姪鍑芥暟

**鏂囦欢锛?* `backend/app/agents/context_builder.py`

```python
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.message import Message, MessageStatus
from app.models.room import Room
from app.models.room_member import RoomMember
from app.models.task import Task
from app.models.user import User

async def get_room_context(room_id: str) -> dict:
    """鏋勫缓 Agent 鎵€闇€鐨勬埧闂翠笂涓嬫枃锛堜换鍔℃弿杩般€佹垚鍛樺垪琛ㄣ€佸綋鍓嶉樁娈碉級"""
    async with AsyncSessionLocal() as db:
        room = await db.get(Room, room_id)
        task = await db.get(Task, room.task_id) if room.task_id else None
        
        # 鑾峰彇鎴块棿鎴愬憳鏄剧ず鍚嶇О
        result = await db.execute(
            select(User.display_name)
            .join(RoomMember, User.id == RoomMember.user_id)
            .where(RoomMember.room_id == room_id)
        )
        members = [r[0] for r in result.fetchall()]
        
        return {
            "task_description": task.requirements if task else "璁ㄨ涓€涓ぞ浼氳棰?,
            "members_info": "銆?.join(members),
            "current_phase": "绗竴闃舵锛氶棶棰樺垎鏋?,  # P3 鏆傛椂鍐欐
        }

async def get_recent_messages(room_id: str, limit: int = 30) -> list[dict]:
    """鑾峰彇鏈€杩?N 鏉″凡瀹屾垚鐨勬秷鎭紙status=ok锛?""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message, User.display_name)
            .outerjoin(User, Message.sender_id == User.id)
            .where(
                Message.room_id == room_id,
                Message.status == MessageStatus.ok
            )
            .order_by(Message.seq_num.desc())
            .limit(limit)
        )
        rows = result.fetchall()
        rows.reverse()
        
        return [
            {
                "content": row.Message.content,
                "display_name": row.display_name or f"[{row.Message.agent_role}]",
                "sender_type": row.Message.sender_type.value
            }
            for row in rows
        ]
```

---

### 姝ラ 6锛氬疄鐜拌皟璇曟帴鍙?

**鏂囦欢锛?* `backend/app/routers/debug.py`锛堜粎寮€鍙戠幆澧冨惎鐢級

```python
from fastapi import APIRouter, BackgroundTasks
from app.agents.role_agents import FacilitatorAgent
from app.agents.context_builder import get_room_context, get_recent_messages

debug_router = APIRouter(prefix="/api/debug", tags=["璋冭瘯"])
facilitator = FacilitatorAgent()

@debug_router.post("/trigger-agent")
async def trigger_agent(
    room_id: str,
    background_tasks: BackgroundTasks
):
    """鎵嬪姩瑙﹀彂 Facilitator 鍙戣█锛堣皟璇曠敤锛?""
    context = await get_room_context(room_id)
    history = await get_recent_messages(room_id)
    
    background_tasks.add_task(
        facilitator.generate_and_push,
        room_id=room_id,
        context=context,
        history=history
    )
    
    return {"status": "triggered", "room_id": room_id, "role": "facilitator"}
```

```python
# main.py 涓粎鍦ㄥ紑鍙戞ā寮忎笅娉ㄥ唽
if settings.DEBUG:
    from app.routers.debug import debug_router
    app.include_router(debug_router)
```

---

### 姝ラ 7锛氬墠绔?useAgentStream Composable

**鏂囦欢锛?* `frontend/src/composables/useAgentStream.js`

```javascript
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useAgentStore } from '@/stores/agent'

export function useAgentStream() {
  const chatStore = useChatStore()
  const agentStore = useAgentStore()
  // 娴佸紡娑堟伅缂撳啿鍖猴細message_id 鈫?绱Н鍐呭
  const streamBuffers = ref(new Map())
  
  // 澶勭悊 agent:typing 浜嬩欢
  function handleTyping({ agent_role, is_typing }) {
    agentStore.setTyping(agent_role, is_typing)
  }
  
  // 澶勭悊 agent:stream 浜嬩欢锛堥€?token 杩藉姞锛?
  function handleStream({ agent_role, message_id, token }) {
    if (!streamBuffers.value.has(message_id)) {
      // 棣栦釜 token锛氬湪娑堟伅鍒楄〃涓垱寤烘祦寮忓崰浣嶆秷鎭?
      streamBuffers.value.set(message_id, '')
      chatStore.addMessage({
        id: message_id,
        sender_type: 'agent',
        agent_role,
        content: '',
        status: 'streaming',
        created_at: new Date().toISOString()
      })
    }
    
    // 杩藉姞 token
    const current = streamBuffers.value.get(message_id) + token
    streamBuffers.value.set(message_id, current)
    
    // 鏇存柊娑堟伅鍒楄〃涓殑鍗犱綅娑堟伅
    chatStore.updateMessageContent(message_id, current)
  }
  
  // 澶勭悊 agent:stream_end 浜嬩欢
  function handleStreamEnd({ message_id, status, content, created_at }) {
    streamBuffers.value.delete(message_id)
    
    // 灏嗘祦寮忓崰浣嶆秷鎭浛鎹负鏈€缁堢増鏈?
    chatStore.finalizeMessage(message_id, {
      content,
      status,
      created_at
    })
  }
  
  return { handleTyping, handleStream, handleStreamEnd }
}
```

**鎵╁睍 `chat store` 鏀寔娴佸紡鎿嶄綔锛?*

```javascript
// stores/chat.js 鏂板 actions
updateMessageContent(messageId, content) {
  const msg = this.messages.find(m => m.id === messageId)
  if (msg) msg.content = content
},

finalizeMessage(messageId, updates) {
  const msg = this.messages.find(m => m.id === messageId)
  if (msg) Object.assign(msg, updates)
},
```

---

### 姝ラ 8锛欰gentTypingIndicator 缁勪欢

**鏂囦欢锛?* `frontend/src/components/chat/AgentTypingIndicator.vue`

```vue
<script setup>
import { computed } from 'vue'
import { useAgentStore } from '@/stores/agent'

const agentStore = useAgentStore()

const ROLE_NAMES = {
  facilitator: '涓绘寔浜?,
  devil_advocate: '鎵瑰垽鑰?,
  summarizer: '鎬荤粨鑰?,
  resource_finder: '璧勬簮鑰?,
  encourager: '婵€鍔辫€?
}

const typingRoles = computed(() => {
  return Object.entries(agentStore.typingStatus)
    .filter(([_, isTyping]) => isTyping)
    .map(([role]) => ROLE_NAMES[role] || role)
})
</script>

<template>
  <Transition name="fade">
    <div v-if="typingRoles.length > 0"
         class="flex items-center gap-2 px-4 py-2 text-sm text-gray-500">
      <!-- 涓夌偣鍔ㄧ敾 -->
      <div class="flex gap-1">
        <span v-for="i in 3" :key="i"
              class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
              :style="{ animationDelay: `${i * 0.15}s` }" />
      </div>
      <span>{{ typingRoles.join('銆?) }} 姝ｅ湪杈撳叆...</span>
    </div>
  </Transition>
</template>
```

**Agent Store锛?*

```javascript
// stores/agent.js
export const useAgentStore = defineStore('agent', {
  state: () => ({
    typingStatus: {
      facilitator: false,
      devil_advocate: false,
      summarizer: false,
      resource_finder: false,
      encourager: false
    }
  }),
  actions: {
    setTyping(role, isTyping) {
      if (role in this.typingStatus) {
        this.typingStatus[role] = isTyping
      }
    }
  }
})
```

---

### 姝ラ 9锛氭洿鏂?ChatPanel 鎺ュ叆 Agent 娴佸紡浜嬩欢

**鏂囦欢锛?* `frontend/src/components/chat/ChatPanel.vue`锛堟墿灞曪級

```javascript
import { useAgentStream } from '@/composables/useAgentStream'

const { handleTyping, handleStream, handleStreamEnd } = useAgentStream()

onMounted(() => {
  // ... 宸叉湁鐨勪簨浠剁洃鍚?...
  
  // 鏂板 Agent 鐩稿叧浜嬩欢
  on('agent:typing', handleTyping)
  on('agent:stream', handleStream)
  on('agent:stream_end', handleStreamEnd)
})
```

---

### 姝ラ 10锛歁essageItem 鎵╁睍 AI 娑堟伅鏍峰紡

**鏂囦欢锛?* `frontend/src/components/chat/MessageItem.vue`锛堟墿灞曪級

```vue
<script setup>
const AGENT_COLORS = {
  facilitator: { bg: 'bg-purple-100', text: 'text-purple-700', label: '涓绘寔浜? },
  devil_advocate: { bg: 'bg-red-100', text: 'text-red-700', label: '鎵瑰垽鑰? },
  summarizer: { bg: 'bg-blue-100', text: 'text-blue-700', label: '鎬荤粨鑰? },
  resource_finder: { bg: 'bg-green-100', text: 'text-green-700', label: '璧勬簮鑰? },
  encourager: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: '婵€鍔辫€? }
}

const isAgent = computed(() => props.message.sender_type === 'agent')
const agentStyle = computed(() => 
  AGENT_COLORS[props.message.agent_role] || { bg: 'bg-gray-100', text: 'text-gray-700', label: 'AI' }
)
</script>

<template>
  <!-- AI 娑堟伅鏍峰紡 -->
  <div v-if="isAgent" class="flex gap-2">
    <!-- AI 瑙掕壊澶村儚 -->
    <div :class="['w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0',
                  agentStyle.bg, agentStyle.text]">
      {{ agentStyle.label[0] }}
    </div>
    
    <div class="max-w-[80%]">
      <!-- 瑙掕壊鏍囩 -->
      <div class="flex items-center gap-2 mb-1">
        <span :class="['text-xs font-medium px-2 py-0.5 rounded-full', agentStyle.bg, agentStyle.text]">
          {{ agentStyle.label }}
        </span>
        <span class="text-xs text-gray-400">{{ formatTime(message.created_at) }}</span>
      </div>
      
      <!-- 娑堟伅鍐呭锛堟祦寮忕姸鎬佹樉绀哄厜鏍囷級 -->
      <div class="bg-gray-50 border border-gray-200 rounded-2xl rounded-tl-sm px-3 py-2 text-sm text-gray-800">
        {{ message.content }}
        <span v-if="message.status === 'streaming'"
              class="inline-block w-0.5 h-4 bg-gray-600 animate-pulse ml-0.5" />
      </div>
    </div>
  </div>
  
  <!-- 瀛︾敓娑堟伅鏍峰紡锛堝師鏈変唬鐮侊級 -->
  <div v-else>
    <!-- ... 宸叉湁瀹炵幇 ... -->
  </div>
</template>
```

---

## 鍥涖€乤gent_settings.yaml 鍒濆鍖栵紙P3 寮曞叆锛?

**鏂囦欢锛?* `backend/app/config/agent_settings.yaml`

P3 闃舵浠呴厤缃笌娌夐粯妫€娴嬬浉鍏崇殑鍙傛暟锛?
骞跺湪 `scheduler.py` 鍚姩鏃堕€氳繃 `yaml.safe_load` 璇诲彇鐢熸晥锛堝惈 `silence_threshold_seconds` 涓?`warmup_minutes`锛夈€?

```yaml
timing:
  silence_threshold_seconds: 180   # 娌夐粯妫€娴嬮槇鍊硷紙婕旂ず鏃舵敼涓?0锛?
  warmup_minutes: 2                 # 鎴块棿寮€濮嬪悗涓嶈Е鍙戠殑绛夊緟鏃堕棿

models:
  role_agents:
    model_version: "selected_model_name"
    history_token_budget: 6000
```

---

## 浜斻€乄ebSocket 浜嬩欢鍗忚锛圥3 鏂板锛?

| 浜嬩欢鍚?| 鏂瑰悜 | 鏁版嵁缁撴瀯 | 璇存槑 |
|--------|------|----------|------|
| `agent:typing` | 鏈嶁啋瀹?| `{type, agent_role, is_typing: bool}` | AI 鎵撳瓧鐘舵€佹寚绀?|
| `agent:stream` | 鏈嶁啋瀹?| `{type, agent_role, message_id, token}` | 娴佸紡 token 鎺ㄩ€?|
| `agent:stream_end` | 鏈嶁啋瀹?| `{type, agent_role, message_id, status, content, created_at}` | 娴佸紡缁撴潫锛屾惡甯﹀畬鏁村唴瀹?|

---

## 鍏€佸叧閿妧鏈粏鑺?

### 6.1 message_id 棰勫垎閰嶇殑蹇呰鎬?

娴佸紡杈撳嚭鏈熼棿瀹㈡埛绔渶瑕?*鑱氬悎澶氫釜 `agent:stream` 浜嬩欢**鍒板悓涓€鏉℃秷鎭场锛屽繀椤诲湪绗竴涓?token 鍓嶅氨纭畾 `message_id`銆傞鍒嗛厤娴佺▼锛?

```
棰勫垎閰?message_id (UUID)
  鈫?鍐欏叆 DB (status=streaming, content="")
  鈫?骞挎挱 agent:typing = true
  鈫?娴佸紡鐢熸垚锛堟瘡涓?token 鎼哄甫 message_id 骞挎挱锛?
  鈫?鏇存柊 DB (status=ok, content=瀹屾暣鍐呭)
  鈫?骞挎挱 agent:stream_end
  鈫?骞挎挱 agent:typing = false
```

### 6.2 娴佸紡杈撳嚭鍓嶇娓叉煋绛栫暐

- 鏀跺埌绗竴涓?`agent:stream` 鏃跺湪娑堟伅鍒楄〃灏鹃儴**鎻掑叆鍗犱綅娑堟伅**锛坕d=message_id, status=streaming锛?
- 鍚庣画姣忎釜 token 杩藉姞鍒板崰浣嶆秷鎭殑 `content` 瀛楁锛堝搷搴斿紡鏇存柊锛孷ue 鑷姩瑙﹀彂閲嶆柊娓叉煋锛?
- 鏀跺埌 `agent:stream_end` 鏃剁敤 `content` 瀛楁鏇挎崲鍗犱綅娑堟伅鍐呭锛宍status` 鏀逛负 `ok`
- 娴佸紡鏈熼棿娑堟伅灏鹃儴鏄剧ず闂儊鍏夋爣锛圕SS `animate-pulse`锛?

### 6.3 闃叉 Streaming 鏈熼棿鐢ㄦ埛鐪嬪埌绌烘秷鎭?

- 鍓嶇鍦ㄦ敹鍒扮涓€涓?`agent:stream` token 鏃舵墠鍒涘缓鍗犱綅娑堟伅锛堣€屼笉鏄湪 `agent:typing` 鏃讹級
- `agent:typing` 浠呯敤浜庢樉绀?姝ｅ湪杈撳叆..."鎸囩ず鏉★紝涓嶅垱寤烘秷鎭皵娉?

### 6.4 澶辫触澶勭悊

- OpenAI 鍏煎 API 璋冪敤澶辫触鏃讹細`status` 鏇存柊涓?`failed`锛屽箍鎾?`agent:stream_end` 鎼哄甫 `status: "failed"`
- 鍓嶇鏀跺埌 `status: "failed"` 鏃讹細娑堟伅姘旀场鏄剧ず涓烘祬鐏拌壊锛屽唴瀹规樉绀?锛圓I 鏆傛椂鏃犳硶鍥炲锛?
- 鑻ョ敓鎴愯繃绋嬩腑浜х敓浜嗛儴鍒嗗唴瀹癸紝`content` 瀛楁浠嶄繚瀛樺凡鐢熸垚鐨勯儴鍒?

---

## 涓冦€佹紨绀轰氦浠樼墿

**P3 婕旂ず鐗堟湰 鈥?AI 瑙掕壊棣栨鍙戣█ Demo**

**婕旂ず姝ラ锛堟甯告紨绀猴級锛?*
1. 瀛︾敓璐﹀彿杩涘叆鎴块棿锛屽彂閫佸嚑鏉℃秷鎭?
2. 鍋滄鍙戣█绛夊緟 3 鍒嗛挓锛堟紨绀虹幆澧冩敼涓?30 绉掞級
3. 鑱婂ぉ鍖洪《閮ㄥ嚭鐜?涓绘寔浜?姝ｅ湪杈撳叆..."鎸囩ず
4. 闅忓悗涓绘寔浜虹殑寮曞鎬ч棶棰樹互鎵撳瓧鏈烘晥鏋滈€愬瓧鍑虹幇
5. 鍒锋柊椤甸潰锛屼富鎸佷汉鍙戣█鐨勫巻鍙茶褰曚粛鐒跺瓨鍦?

**婕旂ず姝ラ锛堝揩閫熸紨绀猴紝浣跨敤璋冭瘯鎺ュ彛锛夛細**
1. 浣跨敤 API 瀹㈡埛绔皟鐢?`POST /api/debug/trigger-agent?room_id={id}`
2. 鍗冲埢鐪嬪埌娴佸紡杈撳嚭鏁堟灉

**楠屾敹鎸囨爣锛?*
- [ ] AI 鍙戣█浠ユ祦寮忔墦瀛楁満鏁堟灉閫愬瓧鍛堢幇
- [ ] `agent:typing` 鎸囩ず鏉″湪鐢熸垚鍓嶅悗姝ｇ‘鏄剧ず/闅愯棌
- [ ] AI 娑堟伅钀藉簱锛堝埛鏂板悗鍘嗗彶璁板綍鏈?AI 娑堟伅锛宻tatus=ok锛?
- [ ] 鐢熸垚澶辫触鏃舵秷鎭姸鎬佷负 failed锛屽墠绔檷绾у睍绀?
- [ ] 娴佸紡娑堟伅涓嶅嚭鐜颁贡搴忥紙token 鎸夐『搴忔嫾鎺ワ級
- [ ] AI 鍙戣█涓庣湡瀹炲鐢熸秷鎭瑙夋牱寮忓尯鍒嗘竻鏅帮紙瑙掕壊鏍囩棰滆壊锛?

---

## 鍏€丳3 鈫?P4 浜ゆ帴璇存槑

P3 缁撴潫鍚庯紝浠ヤ笅鑳藉姏宸插氨缁細

- 鉁?`FacilitatorAgent.generate_and_push()` 瀹屾暣娴佺▼宸查獙璇?
- 鉁?娴佸紡 WebSocket 浜嬩欢璺緞宸叉墦閫氾紙`agent:stream` 鈫?鍓嶇娓叉煋锛?
- 鉁?`agent_settings.yaml` 鍒濆妗嗘灦宸插缓绔?
- 鉁?`context_builder.py` 鍙緵鍏朵粬 4 涓鑹?Agent 澶嶇敤

P4 闃舵闇€瑕侊細
- 鎵╁睍鍙﹀ 4 涓鑹茬殑 Prompt 鍜?Agent 绫?
- 灏嗙洿鎺ヨ皟鐢ㄦ敼涓?Redis 浠诲姟闃熷垪 + AgentWorker 妯″紡
- 瀹炵幇鍒嗗竷寮忛攣闃叉澶氳鑹插悓鏃跺彂瑷€
