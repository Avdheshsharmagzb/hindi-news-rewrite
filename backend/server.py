from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks, Header
from fastapi.responses import FileResponse
import hmac
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage
from news_fetcher import collect_candidates, normalize_title
from image_service import create_watermarked_image, MEDIA_DIR


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
WEBHOOK_CRON_SECRET = os.environ.get('WEBHOOK_CRON_SECRET', '')

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

STATUS_PENDING = "Pending_Review"
STATUS_REWRITTEN = "Rewritten_Pending_Publish"
STATUS_PUBLISHED = "Published"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------- Models ----------------
class NewsItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    headline: str
    content: str
    category: str = "National"
    source: str = ""
    source_url: str = ""
    source_language: str = "en"
    status: str = STATUS_PENDING
    rewritten_headline: Optional[str] = None
    rewritten_content: Optional[str] = None
    image_source_url: str = ""
    image_url: str = ""
    image_status: str = "none"
    publisher_brand: str = "गाजियाबाद टाइम्स"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class NewsCreate(BaseModel):
    headline: str
    content: str
    category: str = "National"
    source: str = ""
    source_language: str = "en"


# ---------------- AI Rewrite ----------------
REWRITE_SYSTEM_PROMPT = (
    "आप एक वरिष्ठ हिंदी समाचार संपादक हैं जो भारत के अग्रणी समाचार संस्थान के लिए कार्य करते हैं। "
    "आपका कार्य दिए गए समाचार को उच्चतम पत्रकारिता श्रेणी (High-Standard Journalistic Hindi) में पुनर्लिखित करना है।\n\n"
    "अनिवार्य नियम:\n"
    "1. भाषा शुद्ध, प्रवाहमयी और व्याकरणिक रूप से त्रुटिरहित होनी चाहिए — मात्राओं, वर्तनी और वाक्य-रचना में शून्य त्रुटि।\n"
    "2. मूल समाचार के सभी तथ्य, नाम, संख्याएँ, तिथियाँ, स्थान और उद्धरण 100% यथावत रहें — किसी भी तथ्य में कोई विकृति, जोड़ या घटाव न हो।\n"
    "3. कॉपीराइट से बचने हेतु शब्दावली और वाक्य-संरचना को पूर्णतः बदलें, परंतु अर्थ अपरिवर्तित रखें। मूल वाक्यों की नकल न करें।\n"
    "4. शैली वस्तुनिष्ठ, संतुलित और समाचारोचित हो — कोई राय, अतिशयोक्ति या अनौपचारिक भाषा नहीं।\n"
    "5. अंग्रेज़ी स्रोत होने पर भी आउटपुट पूर्णतः शुद्ध हिंदी (देवनागरी) में हो। तकनीकी नामों को उपयुक्त रूप में लिप्यंतरित करें।\n\n"
    "आउटपुट केवल एक वैध JSON ऑब्जेक्ट के रूप में दें, बिना किसी अतिरिक्त टिप्पणी या markdown के:\n"
    '{"headline": "पुनर्लिखित शीर्षक", "content": "पुनर्लिखित समाचार सामग्री"}'
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences if present
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


async def rewrite_to_hindi(headline: str, content: str, source_language: str) -> dict:
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"rewrite-{uuid.uuid4()}",
        system_message=REWRITE_SYSTEM_PROMPT,
    ).with_model("gemini", "gemini-3-flash-preview")

    user_prompt = (
        f"मूल स्रोत भाषा: {source_language}\n\n"
        f"मूल शीर्षक:\n{headline}\n\n"
        f"मूल समाचार सामग्री:\n{content}\n\n"
        "उपरोक्त समाचार को उच्च पत्रकारिता श्रेणी की शुद्ध हिंदी में पुनर्लिखित करें और केवल JSON लौटाएँ।"
    )

    response = await chat.send_message(UserMessage(text=user_prompt))
    data = _extract_json(response)
    return {
        "headline": data["headline"].strip(),
        "content": data["content"].strip(),
    }


# ---------------- Routes ----------------
@api_router.get("/")
async def root():
    return {"message": "Hindi Editorial Newsroom CMS API"}


@api_router.get("/stats")
async def get_stats():
    total = await db.news.count_documents({})
    pending = await db.news.count_documents({"status": STATUS_PENDING})
    rewritten = await db.news.count_documents({"status": STATUS_REWRITTEN})
    published = await db.news.count_documents({"status": STATUS_PUBLISHED})
    return {
        "total": total,
        "pending": pending,
        "rewritten": rewritten,
        "published": published,
    }


@api_router.get("/news", response_model=List[NewsItem])
async def list_news(status: Optional[str] = None, category: Optional[str] = None):
    query = {}
    if status and status != "All":
        query["status"] = status
    if category and category != "All":
        query["category"] = category
    docs = await db.news.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [NewsItem(**d) for d in docs]


@api_router.post("/news", response_model=NewsItem)
async def create_news(payload: NewsCreate):
    item = NewsItem(**payload.model_dump())
    await db.news.insert_one(item.model_dump())
    return item


@api_router.post("/news/{item_id}/rewrite", response_model=NewsItem)
async def rewrite_news(item_id: str):
    doc = await db.news.find_one({"id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="News item not found")

    try:
        result = await rewrite_to_hindi(
            doc["headline"], doc["content"], doc.get("source_language", "en")
        )
    except Exception as e:
        logger.exception("AI rewrite failed")
        raise HTTPException(status_code=502, detail=f"AI rewrite failed: {e}")

    update = {
        "rewritten_headline": result["headline"],
        "rewritten_content": result["content"],
        "status": STATUS_REWRITTEN,
        "updated_at": now_iso(),
    }

    # Image policy: if the source news carried a photo, auto re-generate it (AI-modified)
    # with watermark. If no source photo, wait for admin approval to generate one.
    if doc.get("image_source_url"):
        try:
            update["image_url"] = await create_watermarked_image(
                result["headline"], doc.get("category", ""), doc["image_source_url"]
            )
            update["image_status"] = "generated"
        except Exception:
            logger.exception("Auto image generation failed")
            update["image_status"] = "failed"
    else:
        update["image_status"] = "awaiting_approval"

    await db.news.update_one({"id": item_id}, {"$set": update})
    doc.update(update)
    return NewsItem(**doc)


@api_router.post("/news/{item_id}/generate-image", response_model=NewsItem)
async def generate_image_for_news(item_id: str):
    doc = await db.news.find_one({"id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="News item not found")
    if doc.get("status") not in (STATUS_REWRITTEN, STATUS_PUBLISHED):
        raise HTTPException(status_code=400, detail="Image can be generated only after rewrite approval")

    headline = doc.get("rewritten_headline") or doc.get("headline")
    try:
        image_url = await create_watermarked_image(
            headline, doc.get("category", ""), doc.get("image_source_url") or None
        )
    except Exception as e:
        logger.exception("Image generation failed")
        await db.news.update_one({"id": item_id}, {"$set": {"image_status": "failed"}})
        raise HTTPException(status_code=502, detail=f"Image generation failed: {e}")

    update = {"image_url": image_url, "image_status": "generated", "updated_at": now_iso()}
    await db.news.update_one({"id": item_id}, {"$set": update})
    doc.update(update)
    return NewsItem(**doc)


@api_router.post("/news/{item_id}/publish", response_model=NewsItem)
async def publish_news(item_id: str):
    doc = await db.news.find_one({"id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="News item not found")
    if doc.get("status") != STATUS_REWRITTEN:
        raise HTTPException(status_code=400, detail="Only rewritten items can be published")
    update = {"status": STATUS_PUBLISHED, "updated_at": now_iso()}
    await db.news.update_one({"id": item_id}, {"$set": update})
    doc.update(update)
    return NewsItem(**doc)


@api_router.delete("/news/{item_id}")
async def delete_news(item_id: str):
    res = await db.news.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="News item not found")
    return {"deleted": True}


@api_router.get("/media/{name}")
async def get_media(name: str):
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="Invalid name")
    path = MEDIA_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(path), media_type="image/jpeg")


async def fetch_and_store():
    """Fetch fresh (<=4h) news from all sources and store new unique items as Pending_Review."""
    candidates = await collect_candidates()

    existing_urls = set()
    existing_titles = set()
    async for d in db.news.find({}, {"source_url": 1, "headline": 1, "_id": 0}):
        if d.get("source_url"):
            existing_urls.add(d["source_url"])
        existing_titles.add(normalize_title(d.get("headline", "")))

    seen_titles = set()
    docs = []
    by_category = {}
    for c in candidates:
        if c["source_url"] and c["source_url"] in existing_urls:
            continue
        nt = normalize_title(c["headline"])
        if nt and (nt in existing_titles or nt in seen_titles):
            continue
        seen_titles.add(nt)
        docs.append(NewsItem(**c).model_dump())
        by_category[c["category"]] = by_category.get(c["category"], 0) + 1

    if docs:
        await db.news.insert_many(docs)

    return {"fetched": len(docs), "by_category": by_category}


@api_router.post("/news/fetch")
async def fetch_news_now():
    return await fetch_and_store()


async def _run_fetch_bg():
    try:
        result = await fetch_and_store()
        logger.info(f"Cron news fetch stored: {result}")
    except Exception:
        logger.exception("Cron news fetch failed")


@api_router.post("/cron/fetch-news")
async def cron_fetch_news(background_tasks: BackgroundTasks, authorization: str = Header(default="")):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not WEBHOOK_CRON_SECRET or not hmac.compare_digest(token, WEBHOOK_CRON_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")
    background_tasks.add_task(_run_fetch_bg)
    return {"accepted": True}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


SEED_ITEMS = [
    {
        "headline": "Reserve Bank keeps repo rate unchanged at 6.5% for eighth straight time",
        "content": "The Reserve Bank of India on Friday kept the benchmark repo rate unchanged at 6.5 per cent for the eighth consecutive time, citing persistent concerns over food inflation. RBI Governor said the Monetary Policy Committee voted 4 to 2 in favour of the status quo. The central bank retained its GDP growth forecast for the current fiscal year at 7.2 per cent and projected retail inflation at 4.5 per cent.",
        "category": "Business",
        "source": "Wire Agency",
        "source_language": "en",
    },
    {
        "headline": "ISRO successfully places advanced weather satellite into orbit",
        "content": "The Indian Space Research Organisation on Saturday successfully launched its latest meteorological satellite aboard a GSLV rocket from the Satish Dhawan Space Centre in Sriharikota. The 2,274-kg satellite will provide enhanced imaging of cyclones and weather systems. Officials said the satellite carries a 19-channel sounder and will operate for a mission life of at least ten years.",
        "category": "Technology",
        "source": "PTI",
        "source_language": "en",
    },
    {
        "headline": "मुंबई में भारी बारिश से जनजीवन अस्त-व्यस्त, कई इलाकों में जलभराव",
        "content": "मुंबई और आसपास के इलाकों में बीते चौबीस घंटों में हुई भारी बारिश से आम जनजीवन बुरी तरह प्रभावित हुआ। मौसम विभाग ने अगले दो दिनों के लिए रेड अलर्ट जारी किया है। कई निचले इलाकों में पानी भर जाने से यातायात ठप रहा और लोकल ट्रेन सेवाएं देरी से चलीं। नगर निगम ने राहत दलों को तैनात कर दिया है।",
        "category": "National",
        "source": "संवाददाता",
        "source_language": "hi",
    },
    {
        "headline": "India defeat Australia by six wickets to clinch series",
        "content": "India chased down a target of 287 with six wickets in hand to win the deciding one-day international against Australia in Chennai on Sunday. The opener scored a fluent century while the captain remained unbeaten on 84. With this win, India sealed the three-match series 2 to 1. The player of the match award went to the young pacer who took four wickets.",
        "category": "Sports",
        "source": "Reuters",
        "source_language": "en",
    },
    {
        "headline": "संसद के शीतकालीन सत्र में पेश होंगे कई अहम विधेयक",
        "content": "संसद का शीतकालीन सत्र अगले सप्ताह से शुरू होने जा रहा है, जिसमें सरकार कई महत्वपूर्ण विधेयक पेश करने की तैयारी में है। सूत्रों के अनुसार सत्र के दौरान लगभग पंद्रह विधेयकों पर चर्चा होगी। विपक्षी दलों ने महंगाई और बेरोज़गारी के मुद्दों पर सरकार को घेरने की योजना बनाई है। सत्र कुल अठारह बैठकों तक चलेगा।",
        "category": "Politics",
        "source": "समाचार एजेंसी",
        "source_language": "hi",
    },
]

SEED_REWRITTEN = {
    "headline": "Global tech majors announce major investment in Indian data centres",
    "content": "Several leading global technology companies have announced plans to invest a combined 15 billion dollars in building data centre infrastructure across India over the next five years. The investments are expected to create thousands of jobs and strengthen the country's digital backbone. Industry experts said the move reflects growing confidence in India's cloud computing market.",
    "category": "Technology",
    "source": "Bloomberg",
    "source_language": "en",
    "rewritten_headline": "भारत के डेटा सेंटरों में वैश्विक प्रौद्योगिकी कंपनियों का बड़ा निवेश",
    "rewritten_content": "अग्रणी वैश्विक प्रौद्योगिकी कंपनियों ने आगामी पाँच वर्षों में भारत में डेटा सेंटर अवसंरचना के निर्माण हेतु सम्मिलित रूप से पंद्रह अरब डॉलर के निवेश की घोषणा की है। इस निवेश से हज़ारों रोज़गार सृजित होने तथा देश की डिजिटल आधारभूत संरचना के सुदृढ़ होने की संभावना है। उद्योग विशेषज्ञों के अनुसार यह निर्णय भारत के क्लाउड कंप्यूटिंग बाज़ार में बढ़ते विश्वास को दर्शाता है।",
}

SEED_PUBLISHED = {
    "headline": "New expressway to cut travel time between two major cities by half",
    "content": "A newly inaugurated six-lane expressway is set to reduce travel time between the two cities from six hours to just three hours. The project, built at a cost of 22,000 crore rupees, spans 380 kilometres and features multiple interchanges and rest stops. Authorities said the corridor will boost trade and tourism in the region.",
    "category": "National",
    "source": "PTI",
    "source_language": "en",
    "rewritten_headline": "नया एक्सप्रेसवे दो प्रमुख शहरों के बीच यात्रा समय को आधा करेगा",
    "rewritten_content": "हाल ही में शुरू किया गया छह-लेन का एक्सप्रेसवे दोनों शहरों के बीच यात्रा के समय को छह घंटे से घटाकर मात्र तीन घंटे कर देगा। बाईस हज़ार करोड़ रुपये की लागत से निर्मित यह परियोजना तीन सौ अस्सी किलोमीटर लंबी है तथा इसमें अनेक इंटरचेंज और विश्राम स्थल बनाए गए हैं। अधिकारियों के अनुसार यह गलियारा क्षेत्र में व्यापार एवं पर्यटन को बढ़ावा देगा।",
}


@app.on_event("startup")
async def seed_data():
    count = await db.news.count_documents({})
    if count > 0:
        return
    logger.info("Seeding sample news items...")
    items = []
    for s in SEED_ITEMS:
        items.append(NewsItem(**s).model_dump())
    rw = NewsItem(**SEED_REWRITTEN, status=STATUS_REWRITTEN).model_dump()
    items.append(rw)
    pub = NewsItem(**SEED_PUBLISHED, status=STATUS_PUBLISHED).model_dump()
    items.append(pub)
    await db.news.insert_many(items)
    logger.info(f"Seeded {len(items)} news items.")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
