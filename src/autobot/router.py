from fastapi import APIRouter, HTTPException
from autobot.schemas import BacktestRequest, BacktestResult
from autobot.ecommerce.kpis import get_kpis
from autobot.guardian import get_logs, get_metrics
from autobot.backtest_engine import run_backtest
from autobot.rl.train import start_training
from autobot.trading import execute_trade

from autobot.providers.alphavantage import get_intraday as get_alphavantage, get_time_series as get_alphavantage_ts, get_technical_indicators as get_alphavantage_ti
from autobot.providers.ccxt_provider import fetch_ticker as get_ccxt_provider
from autobot.providers.coingecko import get_intraday as get_coingecko
from autobot.providers.fred import get_time_series as get_fred
from autobot.providers.newsapi import get_time_series as get_newsapi
from autobot.providers.shopify import get_orders as get_shopify_orders
from autobot.providers.twelvedata import get_intraday as get_twelvedata

router = APIRouter()
from autobot.providers.alphavantage import get_alphavantage
@router.get('/provider/alphavantage/{param}')
def prov_alphavantage(param: str): return get_alphavantage(param)
from autobot.providers.ccxt_provider import get_ccxt_provider
@router.get('/provider/ccxt_provider/{param}')
def prov_ccxt_provider(param: str): return get_ccxt_provider(param)
from autobot.providers.newsapi import get_newsapi
@router.get('/provider/newsapi/{param}')
def prov_newsapi(param: str): return get_newsapi(param)
from autobot.providers.shopify import get_shopify
@router.get('/provider/shopify/{param}')
def prov_shopify(param: str): return get_shopify(param)
from autobot.providers.fred import get_fred
@router.get('/provider/fred/{param}')
def prov_fred(param: str): return get_fred(param)
from autobot.plugins.vairo import get_data as get_vairo
@router.get('/plugins/vairo')
def plug_vairo(): return get_vairo()
from autobot.plugins.digitalemployees_io import get_data as get_digitalemployees_io
@router.get('/plugins/digitalemployees_io')
def plug_digitalemployees_io(): return get_digitalemployees_io()
from autobot.plugins.vessium import get_data as get_vessium
@router.get('/plugins/vessium')
def plug_vessium(): return get_vessium()
from autobot.plugins.confident_ai import get_data as get_confident_ai
@router.get('/plugins/confident_ai')
def plug_confident_ai(): return get_confident_ai()
from autobot.plugins.thelibrarian_io import get_data as get_thelibrarian_io
@router.get('/plugins/thelibrarian_io')
def plug_thelibrarian_io(): return get_thelibrarian_io()
from autobot.plugins.doozerai import get_data as get_doozerai
@router.get('/plugins/doozerai')
def plug_doozerai(): return get_doozerai()
from autobot.plugins.agentverse import get_data as get_agentverse
@router.get('/plugins/agentverse')
def plug_agentverse(): return get_agentverse()
from autobot.plugins.nextvestment import get_data as get_nextvestment
@router.get('/plugins/nextvestment')
def plug_nextvestment(): return get_nextvestment()
from autobot.plugins.chatvolt import get_data as get_chatvolt
@router.get('/plugins/chatvolt')
def plug_chatvolt(): return get_chatvolt()
from autobot.plugins.playai import get_data as get_playai
@router.get('/plugins/playai')
def plug_playai(): return get_playai()
from autobot.plugins.octocomics import get_data as get_octocomics
@router.get('/plugins/octocomics')
def plug_octocomics(): return get_octocomics()
from autobot.plugins.crewai import get_data as get_crewai
@router.get('/plugins/crewai')
def plug_crewai(): return get_crewai()
from autobot.plugins.ppe_kit_detection_agents import get_data as get_ppe_kit_detection_agents
@router.get('/plugins/ppe_kit_detection_agents')
def plug_ppe_kit_detection_agents(): return get_ppe_kit_detection_agents()
from autobot.plugins.promptowl import get_data as get_promptowl
@router.get('/plugins/promptowl')
def plug_promptowl(): return get_promptowl()
from autobot.plugins.bee_agent_framework import get_data as get_bee_agent_framework
@router.get('/plugins/bee_agent_framework')
def plug_bee_agent_framework(): return get_bee_agent_framework()
from autobot.plugins.langbase import get_data as get_langbase
@router.get('/plugins/langbase')
def plug_langbase(): return get_langbase()
from autobot.plugins.supercog import get_data as get_supercog
@router.get('/plugins/supercog')
def plug_supercog(): return get_supercog()
from autobot.plugins.manus_ai import get_data as get_manus_ai
@router.get('/plugins/manus_ai')
def plug_manus_ai(): return get_manus_ai()
from autobot.plugins.twig import get_data as get_twig
@router.get('/plugins/twig')
def plug_twig(): return get_twig()
from autobot.plugins.xagent import get_data as get_xagent
@router.get('/plugins/xagent')
def plug_xagent(): return get_xagent()
from autobot.plugins.director import get_data as get_director
@router.get('/plugins/director')
def plug_director(): return get_director()
from autobot.plugins.tensorstax import get_data as get_tensorstax
@router.get('/plugins/tensorstax')
def plug_tensorstax(): return get_tensorstax()
from autobot.plugins.nurture import get_data as get_nurture
@router.get('/plugins/nurture')
def plug_nurture(): return get_nurture()
from autobot.plugins.teammates_ai import get_data as get_teammates_ai
@router.get('/plugins/teammates_ai')
def plug_teammates_ai(): return get_teammates_ai()
from autobot.plugins.bob import get_data as get_bob
@router.get('/plugins/bob')
def plug_bob(): return get_bob()
from autobot.plugins.shipstation import get_data as get_shipstation
@router.get('/plugins/shipstation')
def plug_shipstation(): return get_shipstation()
from autobot.plugins.chatgpt import get_data as get_chatgpt
@router.get('/plugins/chatgpt')
def plug_chatgpt(): return get_chatgpt()
from autobot.plugins.garnit import get_data as get_garnit
@router.get('/plugins/garnit')
def plug_garnit(): return get_garnit()
from autobot.plugins.will import get_data as get_will
@router.get('/plugins/will')
def plug_will(): return get_will()
from autobot.plugins.qwen_chat import get_data as get_qwen_chat
@router.get('/plugins/qwen_chat')
def plug_qwen_chat(): return get_qwen_chat()
@router.get('/backtest')
def backtest(symbol: str):
    from autobot.backtest_engine import run_backtest
    return run_backtest(symbol)

@router.get('/predict')
def predict():
    return {'prediction': None}

@router.post('/train')
def train():
    from autobot.rl.train import start_training
    return {'job_id': start_training()}

@router.get('/metrics')
def metrics():
    from autobot.ecommerce.kpis import get_kpis
    return get_kpis()

@router.get('/logs')
def logs():
    from autobot.autobot_guardian import get_logs
    return get_logs()

@router.get('/monitoring')
def monitoring():
    from autobot.autobot_guardian import get_health
    return get_health()
from autobot.providers.alphavantage import get_alphavantage
@router.get('/provider/alphavantage/{param}')
def prov_alphavantage(param: str): return get_alphavantage(param)
from autobot.providers.ccxt_provider import get_ccxt_provider
@router.get('/provider/ccxt_provider/{param}')
def prov_ccxt_provider(param: str): return get_ccxt_provider(param)
from autobot.providers.newsapi import get_newsapi
@router.get('/provider/newsapi/{param}')
def prov_newsapi(param: str): return get_newsapi(param)
from autobot.providers.shopify import get_shopify
@router.get('/provider/shopify/{param}')
def prov_shopify(param: str): return get_shopify(param)
from autobot.providers.fred import get_fred
@router.get('/provider/fred/{param}')
def prov_fred(param: str): return get_fred(param)
from autobot.plugins.vairo import get_data as get_vairo
@router.get('/plugins/vairo')
def plug_vairo(): return get_vairo()
from autobot.plugins.digitalemployees_io import get_data as get_digitalemployees_io
@router.get('/plugins/digitalemployees_io')
def plug_digitalemployees_io(): return get_digitalemployees_io()
from autobot.plugins.vessium import get_data as get_vessium
@router.get('/plugins/vessium')
def plug_vessium(): return get_vessium()
from autobot.plugins.confident_ai import get_data as get_confident_ai
@router.get('/plugins/confident_ai')
def plug_confident_ai(): return get_confident_ai()
from autobot.plugins.thelibrarian_io import get_data as get_thelibrarian_io
@router.get('/plugins/thelibrarian_io')
def plug_thelibrarian_io(): return get_thelibrarian_io()
from autobot.plugins.doozerai import get_data as get_doozerai
@router.get('/plugins/doozerai')
def plug_doozerai(): return get_doozerai()
from autobot.plugins.agentverse import get_data as get_agentverse
@router.get('/plugins/agentverse')
def plug_agentverse(): return get_agentverse()
from autobot.plugins.nextvestment import get_data as get_nextvestment
@router.get('/plugins/nextvestment')
def plug_nextvestment(): return get_nextvestment()
from autobot.plugins.chatvolt import get_data as get_chatvolt
@router.get('/plugins/chatvolt')
def plug_chatvolt(): return get_chatvolt()
from autobot.plugins.playai import get_data as get_playai
@router.get('/plugins/playai')
def plug_playai(): return get_playai()
from autobot.plugins.octocomics import get_data as get_octocomics
@router.get('/plugins/octocomics')
def plug_octocomics(): return get_octocomics()
from autobot.plugins.crewai import get_data as get_crewai
@router.get('/plugins/crewai')
def plug_crewai(): return get_crewai()
from autobot.plugins.ppe_kit_detection_agents import get_data as get_ppe_kit_detection_agents
@router.get('/plugins/ppe_kit_detection_agents')
def plug_ppe_kit_detection_agents(): return get_ppe_kit_detection_agents()
from autobot.plugins.promptowl import get_data as get_promptowl
@router.get('/plugins/promptowl')
def plug_promptowl(): return get_promptowl()
from autobot.plugins.bee_agent_framework import get_data as get_bee_agent_framework
@router.get('/plugins/bee_agent_framework')
def plug_bee_agent_framework(): return get_bee_agent_framework()
from autobot.plugins.langbase import get_data as get_langbase
@router.get('/plugins/langbase')
def plug_langbase(): return get_langbase()
from autobot.plugins.supercog import get_data as get_supercog
@router.get('/plugins/supercog')
def plug_supercog(): return get_supercog()
from autobot.plugins.manus_ai import get_data as get_manus_ai
@router.get('/plugins/manus_ai')
def plug_manus_ai(): return get_manus_ai()
from autobot.plugins.twig import get_data as get_twig
@router.get('/plugins/twig')
def plug_twig(): return get_twig()
from autobot.plugins.xagent import get_data as get_xagent
@router.get('/plugins/xagent')
def plug_xagent(): return get_xagent()
from autobot.plugins.director import get_data as get_director
@router.get('/plugins/director')
def plug_director(): return get_director()
from autobot.plugins.tensorstax import get_data as get_tensorstax
@router.get('/plugins/tensorstax')
def plug_tensorstax(): return get_tensorstax()
from autobot.plugins.nurture import get_data as get_nurture
@router.get('/plugins/nurture')
def plug_nurture(): return get_nurture()
from autobot.plugins.teammates_ai import get_data as get_teammates_ai
@router.get('/plugins/teammates_ai')
def plug_teammates_ai(): return get_teammates_ai()
from autobot.plugins.bob import get_data as get_bob
@router.get('/plugins/bob')
def plug_bob(): return get_bob()
from autobot.plugins.shipstation import get_data as get_shipstation
@router.get('/plugins/shipstation')
def plug_shipstation(): return get_shipstation()
from autobot.plugins.chatgpt import get_data as get_chatgpt
@router.get('/plugins/chatgpt')
def plug_chatgpt(): return get_chatgpt()
from autobot.plugins.garnit import get_data as get_garnit
@router.get('/plugins/garnit')
def plug_garnit(): return get_garnit()
from autobot.plugins.will import get_data as get_will
@router.get('/plugins/will')
def plug_will(): return get_will()
from autobot.plugins.qwen_chat import get_data as get_qwen_chat
@router.get('/plugins/qwen_chat')
def plug_qwen_chat(): return get_qwen_chat()
@router.get('/backtest')
def backtest(symbol: str):
    from autobot.backtest_engine import run_backtest
    return run_backtest(symbol)

@router.get('/predict')
def predict():
    return {'prediction': None}

@router.post('/train')
def train():
    from autobot.rl.train import start_training
    return {'job_id': start_training()}

@router.get('/metrics')
def metrics():
    from autobot.ecommerce.kpis import get_kpis
    return get_kpis()

@router.get('/logs')
def logs():
    from autobot.autobot_guardian import get_logs
    return get_logs()

@router.get('/monitoring')
def monitoring():
    from autobot.autobot_guardian import get_health
    return get_health()
from autobot.providers.alphavantage import get_alphavantage
@router.get('/provider/alphavantage/{param}')
def prov_alphavantage(param: str): return get_alphavantage(param)
from autobot.providers.ccxt_provider import get_ccxt_provider
@router.get('/provider/ccxt_provider/{param}')
def prov_ccxt_provider(param: str): return get_ccxt_provider(param)
from autobot.providers.newsapi import get_newsapi
@router.get('/provider/newsapi/{param}')
def prov_newsapi(param: str): return get_newsapi(param)
from autobot.providers.shopify import get_shopify
@router.get('/provider/shopify/{param}')
def prov_shopify(param: str): return get_shopify(param)
from autobot.providers.fred import get_fred
@router.get('/provider/fred/{param}')
def prov_fred(param: str): return get_fred(param)
from autobot.plugins.vairo import get_data as get_vairo
@router.get('/plugins/vairo')
def plug_vairo(): return get_vairo()
from autobot.plugins.digitalemployees_io import get_data as get_digitalemployees_io
@router.get('/plugins/digitalemployees_io')
def plug_digitalemployees_io(): return get_digitalemployees_io()
from autobot.plugins.vessium import get_data as get_vessium
@router.get('/plugins/vessium')
def plug_vessium(): return get_vessium()
from autobot.plugins.confident_ai import get_data as get_confident_ai
@router.get('/plugins/confident_ai')
def plug_confident_ai(): return get_confident_ai()
from autobot.plugins.thelibrarian_io import get_data as get_thelibrarian_io
@router.get('/plugins/thelibrarian_io')
def plug_thelibrarian_io(): return get_thelibrarian_io()
from autobot.plugins.doozerai import get_data as get_doozerai
@router.get('/plugins/doozerai')
def plug_doozerai(): return get_doozerai()
from autobot.plugins.agentverse import get_data as get_agentverse
@router.get('/plugins/agentverse')
def plug_agentverse(): return get_agentverse()
from autobot.plugins.nextvestment import get_data as get_nextvestment
@router.get('/plugins/nextvestment')
def plug_nextvestment(): return get_nextvestment()
from autobot.plugins.chatvolt import get_data as get_chatvolt
@router.get('/plugins/chatvolt')
def plug_chatvolt(): return get_chatvolt()
from autobot.plugins.playai import get_data as get_playai
@router.get('/plugins/playai')
def plug_playai(): return get_playai()
from autobot.plugins.octocomics import get_data as get_octocomics
@router.get('/plugins/octocomics')
def plug_octocomics(): return get_octocomics()
from autobot.plugins.crewai import get_data as get_crewai
@router.get('/plugins/crewai')
def plug_crewai(): return get_crewai()
from autobot.plugins.ppe_kit_detection_agents import get_data as get_ppe_kit_detection_agents
@router.get('/plugins/ppe_kit_detection_agents')
def plug_ppe_kit_detection_agents(): return get_ppe_kit_detection_agents()
from autobot.plugins.promptowl import get_data as get_promptowl
@router.get('/plugins/promptowl')
def plug_promptowl(): return get_promptowl()
from autobot.plugins.bee_agent_framework import get_data as get_bee_agent_framework
@router.get('/plugins/bee_agent_framework')
def plug_bee_agent_framework(): return get_bee_agent_framework()
from autobot.plugins.langbase import get_data as get_langbase
@router.get('/plugins/langbase')
def plug_langbase(): return get_langbase()
from autobot.plugins.supercog import get_data as get_supercog
@router.get('/plugins/supercog')
def plug_supercog(): return get_supercog()
from autobot.plugins.manus_ai import get_data as get_manus_ai
@router.get('/plugins/manus_ai')
def plug_manus_ai(): return get_manus_ai()
from autobot.plugins.twig import get_data as get_twig
@router.get('/plugins/twig')
def plug_twig(): return get_twig()
from autobot.plugins.xagent import get_data as get_xagent
@router.get('/plugins/xagent')
def plug_xagent(): return get_xagent()
from autobot.plugins.director import get_data as get_director
@router.get('/plugins/director')
def plug_director(): return get_director()
from autobot.plugins.tensorstax import get_data as get_tensorstax
@router.get('/plugins/tensorstax')
def plug_tensorstax(): return get_tensorstax()
from autobot.plugins.nurture import get_data as get_nurture
@router.get('/plugins/nurture')
def plug_nurture(): return get_nurture()
from autobot.plugins.teammates_ai import get_data as get_teammates_ai
@router.get('/plugins/teammates_ai')
def plug_teammates_ai(): return get_teammates_ai()
from autobot.plugins.bob import get_data as get_bob
@router.get('/plugins/bob')
def plug_bob(): return get_bob()
from autobot.plugins.shipstation import get_data as get_shipstation
@router.get('/plugins/shipstation')
def plug_shipstation(): return get_shipstation()
from autobot.plugins.chatgpt import get_data as get_chatgpt
@router.get('/plugins/chatgpt')
def plug_chatgpt(): return get_chatgpt()
from autobot.plugins.garnit import get_data as get_garnit
@router.get('/plugins/garnit')
def plug_garnit(): return get_garnit()
from autobot.plugins.will import get_data as get_will
@router.get('/plugins/will')
def plug_will(): return get_will()
from autobot.plugins.qwen_chat import get_data as get_qwen_chat
@router.get('/plugins/qwen_chat')
def plug_qwen_chat(): return get_qwen_chat()
@router.get('/backtest')
def backtest(symbol: str):
    from autobot.backtest_engine import run_backtest
    return run_backtest(symbol)

@router.get('/predict')
def predict():
    return {'prediction': None}

@router.post('/train')
def train():
    from autobot.rl.train import start_training
    return {'job_id': start_training()}

@router.get('/metrics')
def metrics():
    from autobot.ecommerce.kpis import get_kpis
    return get_kpis()

@router.get('/logs')
def logs():
    from autobot.autobot_guardian import get_logs
    return get_logs()

@router.get('/monitoring')
def monitoring():
    from autobot.autobot_guardian import get_health
    return get_health()



@router.post("/backtest", response_model=BacktestResult, tags=["backtest"])
async def backtest_endpoint(req: BacktestRequest):
    metrics = run_backtest(req.strategy, req.parameters)
    return BacktestResult(strategy=req.strategy, metrics=metrics)

@router.get("/metrics", tags=["metrics"])
async def metrics_endpoint():
    return get_kpis()

@router.post("/train", tags=["train"])
async def train_endpoint():
    job_id = start_training()
    return {"status": "training_started", "job_id": job_id}

@router.get("/logs", tags=["logs"])
async def logs_endpoint():
    return get_logs()

@router.get("/monitoring", tags=["monitoring"])
async def monitoring_endpoint():
    return get_metrics()

@router.post("/trade", tags=["trade"])
async def trade_endpoint(order: dict):
    symbol = order.get("symbol")
    side = order.get("side")
    amount = order.get("amount")
    if not all([symbol, side, amount]):
        raise HTTPException(status_code=400, detail="Missing trade parameters")
    order_id = execute_trade(symbol, side, amount)
    return {"status": "order_placed", "order_id": order_id}