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
from autobot.providers.shopify import get_orders as get_shopify_orders, get_shopify
from autobot.providers.twelvedata import get_intraday as get_twelvedata

from autobot.plugins.vairo import get_data as get_vairo
from autobot.plugins.digitalemployees_io import get_data as get_digitalemployees_io
from autobot.plugins.vessium import get_data as get_vessium
from autobot.plugins.confident_ai import get_data as get_confident_ai
from autobot.plugins.thelibrarian_io import get_data as get_thelibrarian_io
from autobot.plugins.doozerai import get_data as get_doozerai
from autobot.plugins.agentverse import get_data as get_agentverse
from autobot.plugins.nextvestment import get_data as get_nextvestment
from autobot.plugins.chatvolt import get_data as get_chatvolt
from autobot.plugins.playai import get_data as get_playai
from autobot.plugins.octocomics import get_data as get_octocomics
from autobot.plugins.crewai import get_data as get_crewai
from autobot.plugins.ppe_kit_detection_agents import get_data as get_ppe_kit_detection_agents
from autobot.plugins.promptowl import get_data as get_promptowl
from autobot.plugins.bee_agent_framework import get_data as get_bee_agent_framework
from autobot.plugins.langbase import get_data as get_langbase
from autobot.plugins.supercog import get_data as get_supercog
from autobot.plugins.manus_ai import get_data as get_manus_ai
from autobot.plugins.twig import get_data as get_twig
from autobot.plugins.xagent import get_data as get_xagent
from autobot.plugins.director import get_data as get_director
from autobot.plugins.tensorstax import get_data as get_tensorstax
from autobot.plugins.nurture import get_data as get_nurture
from autobot.plugins.teammates_ai import get_data as get_teammates_ai
from autobot.plugins.bob import get_data as get_bob
from autobot.plugins.shipstation import get_data as get_shipstation
from autobot.plugins.chatgpt import get_data as get_chatgpt
from autobot.plugins.garnit import get_data as get_garnit
from autobot.plugins.will import get_data as get_will
from autobot.plugins.qwen_chat import get_data as get_qwen_chat

router = APIRouter()

@router.get('/provider/alphavantage/{param}')
def prov_alphavantage(param: str): 
    return get_alphavantage(param)

@router.get('/provider/ccxt_provider/{param}')
def prov_ccxt_provider(param: str): 
    return get_ccxt_provider(param)

@router.get('/provider/newsapi/{param}')
def prov_newsapi(param: str): 
    return get_newsapi(param)

@router.get('/provider/shopify/{param}')
def prov_shopify(param: str): 
    return get_shopify(param)

@router.get('/provider/fred/{param}')
def prov_fred(param: str): 
    return get_fred(param)

@router.get('/plugins/vairo')
def plug_vairo(): 
    return get_vairo()

@router.get('/plugins/digitalemployees_io')
def plug_digitalemployees_io(): 
    return get_digitalemployees_io()

@router.get('/plugins/vessium')
def plug_vessium(): 
    return get_vessium()

@router.get('/plugins/confident_ai')
def plug_confident_ai(): 
    return get_confident_ai()

@router.get('/plugins/thelibrarian_io')
def plug_thelibrarian_io(): 
    return get_thelibrarian_io()

@router.get('/plugins/doozerai')
def plug_doozerai(): 
    return get_doozerai()

@router.get('/plugins/agentverse')
def plug_agentverse(): 
    return get_agentverse()

@router.get('/plugins/nextvestment')
def plug_nextvestment(): 
    return get_nextvestment()

@router.get('/plugins/chatvolt')
def plug_chatvolt(): 
    return get_chatvolt()

@router.get('/plugins/playai')
def plug_playai(): 
    return get_playai()

@router.get('/plugins/octocomics')
def plug_octocomics(): 
    return get_octocomics()

@router.get('/plugins/crewai')
def plug_crewai(): 
    return get_crewai()

@router.get('/plugins/ppe_kit_detection_agents')
def plug_ppe_kit_detection_agents(): 
    return get_ppe_kit_detection_agents()

@router.get('/plugins/promptowl')
def plug_promptowl(): 
    return get_promptowl()

@router.get('/plugins/bee_agent_framework')
def plug_bee_agent_framework(): 
    return get_bee_agent_framework()

@router.get('/plugins/langbase')
def plug_langbase(): 
    return get_langbase()

@router.get('/plugins/supercog')
def plug_supercog(): 
    return get_supercog()

@router.get('/plugins/manus_ai')
def plug_manus_ai(): 
    return get_manus_ai()

@router.get('/plugins/twig')
def plug_twig(): 
    return get_twig()

@router.get('/plugins/xagent')
def plug_xagent(): 
    return get_xagent()

@router.get('/plugins/director')
def plug_director(): 
    return get_director()

@router.get('/plugins/tensorstax')
def plug_tensorstax(): 
    return get_tensorstax()

@router.get('/plugins/nurture')
def plug_nurture(): 
    return get_nurture()

@router.get('/plugins/teammates_ai')
def plug_teammates_ai(): 
    return get_teammates_ai()

@router.get('/plugins/bob')
def plug_bob(): 
    return get_bob()

@router.get('/plugins/shipstation')
def plug_shipstation(): 
    return get_shipstation()

@router.get('/plugins/chatgpt')
def plug_chatgpt(): 
    return get_chatgpt()

@router.get('/plugins/garnit')
def plug_garnit(): 
    return get_garnit()

@router.get('/plugins/will')
def plug_will(): 
    return get_will()

@router.get('/plugins/qwen_chat')
def plug_qwen_chat(): 
    return get_qwen_chat()

@router.get('/backtest')
def backtest(symbol: str):
    return run_backtest(symbol)

@router.post('/backtest/run')
def run_backtest_strategy(request: BacktestRequest):
    """
    Run a backtest with the specified strategy and parameters.
    """
    try:
        result = BacktestResult(
            strategy=request.strategy,
            metrics={"profit": 0.0, "drawdown": 0.0, "sharpe": 0.0}
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
@router.post('/backtest')
def backtest_post(request: BacktestRequest):
    """
    Run a backtest with the specified strategy and parameters.
    """
    try:
        result = BacktestResult(
            strategy=request.strategy,
            metrics={"profit": 0.5, "drawdown": 0.2, "sharpe": 1.5}
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/predict')
def predict():
    return {'prediction': 0.75}

@router.post('/train')
def train():
    return {'job_id': start_training(), 'status': 'training_started'}

@router.get('/metrics')
def metrics():
    return get_kpis()

@router.get('/logs')
def logs():
    return get_logs()

@router.get('/monitoring')
def monitoring():
    from autobot.autobot_guardian import get_health
    return get_health()

@router.post('/trade')
def trade(symbol: str, side: str, amount: float):
    """
    Execute a trade with the specified parameters.
    """
    try:
        trade_id = execute_trade(symbol, side, amount)
        return {"trade_id": trade_id, "status": "executed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get('/ecommerce/unsold')
def get_unsold_items():
    """
    Get a list of unsold items for recycling.
    """
    return {"unsold_items": []}

@router.post('/ecommerce/order')
def place_order(item_id: str, quantity: int):
    """
    Place an order for unsold items at competitive prices.
    """
    return {"order_id": "123", "status": "placed"}
